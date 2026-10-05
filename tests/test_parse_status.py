"""Unit tests for VestelAcApi._parse_status and the AC code builders.

These are the pure, side-effect-free parts of api.py. The status decoder
must keep working for real AC payloads (regression guard - the upstream
maintainer has a real AC) and must no longer crash on non-AC appliances
like fridges (the bug this change fixes: KeyError 'ACGENSI' broke the
whole integration when any non-AC device was on the account).
"""

import pytest

from custom_components.vestel_ac.api import VestelAcApi

TEMP_OFFSET = 32736


def _ac_payload(**overrides) -> dict:
    """A realistic AC status payload, values matching the README's
    reverse-engineered examples."""
    payload = {
        "ACGENSI": "00017",  # cool (1) + fan2 (2 << 3)
        "ACTEMOT": str(TEMP_OFFSET + 22),
        "ACROOTE": "24",
        "ACFANPO": "00050",  # "normal" baseline from the README
        "ACOFFTV": "02047",  # timer disabled
    }
    payload.update(overrides)
    return payload


class TestAcPayloads:
    def test_full_ac_payload_is_fully_decoded(self):
        status = VestelAcApi._parse_status(_ac_payload())
        assert status["is_ac"] is True
        assert status["on"] is True
        assert status["mode"] == "cool"
        assert status["fan"] == "fan2"
        assert status["temp"] == 22
        assert status["room_temp"] == 24
        assert status["fanpo_raw"] == 50
        assert status["turbo"] is False
        assert status["sleep"] is False
        assert status["ionizer"] is False
        assert status["eco"] is False
        assert status["auto_off_enabled"] is False
        assert status["raw"] == _ac_payload()

    def test_off_mode(self):
        status = VestelAcApi._parse_status(_ac_payload(ACGENSI="00005"))
        assert status["is_ac"] is True
        assert status["on"] is False
        assert status["mode"] == "off"

    def test_heat_mode_and_fan_speeds(self):
        status = VestelAcApi._parse_status(_ac_payload(ACGENSI="00028"))  # heat(4) + fan3(3<<3=24)
        assert status["mode"] == "heat"
        assert status["fan"] == "fan3"

    def test_fanpo_special_modes(self):
        # README "verified special modes": baseline 00050 + one flag bit.
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00178"))["sleep"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00306"))["ionizer"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00562"))["eco"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00051"))["turbo"] is True

    def test_louver_positions(self):
        status = VestelAcApi._parse_status(_ac_payload(ACFANPO="00060"))  # swing
        assert status["vertical"] == 6
        assert status["horizontal"] == 3

    def test_auto_off_time(self):
        # README example: 14:18 -> 00590.
        status = VestelAcApi._parse_status(_ac_payload(ACOFFTV="00590"))
        assert status["auto_off_enabled"] is True
        assert status["auto_off_hour"] == 14
        assert status["auto_off_minute"] == 18


class TestNonAcPayloads:
    def test_fridge_payload_returns_raw_only(self):
        # Made-up fridge-style fields: the point is that no AC* fields
        # are present, which used to crash the coordinator.
        payload = {"RFTEMPF": "004", "RFTEMPR": "007", "DOOROPEN": "00000"}
        status = VestelAcApi._parse_status(payload)
        assert status["is_ac"] is False
        assert status["raw"] is payload
        assert "mode" not in status

    def test_empty_payload(self):
        status = VestelAcApi._parse_status({})
        assert status["is_ac"] is False

    def test_acgeni_without_required_fields_does_not_crash(self):
        status = VestelAcApi._parse_status({"ACGENSI": "00017"})
        assert status["is_ac"] is False
        assert status["raw"] == {"ACGENSI": "00017"}

    def test_malformed_values_do_not_crash(self):
        status = VestelAcApi._parse_status(
            _ac_payload(ACGENSI="not-a-number", ACTEMOT="x")
        )
        assert status["is_ac"] is False


class TestAcCodeBuilders:
    """Guard the AC command encoding - the upstream maintainer's real AC
    must keep receiving exactly the codes it receives today."""

    def test_build_gensi(self):
        assert VestelAcApi._build_gensi("cool", "fan2") == "ACGENSI00017"
        assert VestelAcApi._build_gensi("heat", "auto") == "ACGENSI00004"
        assert VestelAcApi._build_gensi("off", "auto") == "ACGENSI00005"

    def test_build_gensi_rejects_bad_input(self):
        with pytest.raises(ValueError):
            VestelAcApi._build_gensi("nope")

    def test_build_temot(self):
        assert VestelAcApi._build_temot(22) == f"ACTEMOT{TEMP_OFFSET + 22}"
        with pytest.raises(ValueError):
            VestelAcApi._build_temot(17)
        with pytest.raises(ValueError):
            VestelAcApi._build_temot(31)

    def test_build_field_pads_to_five_digits(self):
        assert VestelAcApi._build_field("ACFANPO", 562) == "ACFANPO00562"
        assert VestelAcApi._build_field("ACOFFTV", 590) == "ACOFFTV00590"

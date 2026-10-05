"""Binary sensors for Vestel appliances that are not air conditioners.

Right now this is just the fridge door (``RFDOORA``). The value semantics
were reverse engineered from a real device: ``00003`` with the door closed
and ``00001`` while the door was open (the fridge started alarming a
couple of minutes later). See ``api.fridge_door_is_open`` for the decode
rule and how to extend it once more states show up.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator, filter_fridge_devices
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]

    # Fridges carry the RF* fields; an AC never does. Gating on the fridge
    # filter keeps this platform inert for accounts with only air
    # conditioners.
    entities: list[BinarySensorEntity] = [
        _VestelFridgeDoorSensor(coordinator, entry.entry_id, device)
        for device in filter_fridge_devices(stored)
    ]

    async_add_entities(entities)


class _VestelFridgeDoorSensor(
    CoordinatorEntity[VestelAcCoordinator], BinarySensorEntity
):
    """Door state of a Vestel fridge (open when RFDOORA's closed bit is clear)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        entry_id: str,
        device: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device["device_id"]
        self._attr_name = "Kapı"
        self._attr_unique_id = f"{entry_id}_{self._device_id}_fridge_door"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Vestel",
            name=device.get("device_name", self._device_id),
            model="Buzdolabı",
        )
        self._entry_id = entry_id

    @property
    def _fridge(self) -> dict[str, Any]:
        status = self.coordinator.data.get(self._device_id, {})
        fridge = status.get("fridge")
        return fridge if isinstance(fridge, dict) else {}

    @property
    def is_on(self) -> bool | None:
        return self._fridge.get("door_open")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Keep the undecoded value visible so further states (once more of
        # them are observed) can be interpreted without guessing.
        return {"ham_deger": self._fridge.get("door_raw")}

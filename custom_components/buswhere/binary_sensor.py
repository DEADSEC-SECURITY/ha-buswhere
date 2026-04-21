"""Binary sensor platform for BusWhere shuttle."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ORG, CONF_ROUTE_ID, DOMAIN
from .coordinator import BusWhereCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BusWhere binary sensor."""
    coordinator: BusWhereCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([BusWhereActiveSensor(coordinator, entry)])


class BusWhereActiveSensor(CoordinatorEntity[BusWhereCoordinator], BinarySensorEntity):
    """Binary sensor indicating whether the shuttle is currently active."""

    _attr_has_entity_name = True
    _attr_name = "Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:bus-clock"

    def __init__(
        self,
        coordinator: BusWhereCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        org = entry.data[CONF_ORG]
        route_id = entry.data[CONF_ROUTE_ID]
        self._attr_unique_id = f"{org}_{route_id}_active"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{org}_{route_id}")},
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the bus is active."""
        if not self.coordinator.data:
            return None
        data = self.coordinator.data
        if data.get("suspended"):
            return False
        return data.get("active", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        attrs: dict[str, Any] = {}
        if data.get("started_at"):
            attrs["started_at"] = data["started_at"]
        if data.get("suspended") is not None:
            attrs["suspended"] = data["suspended"]
        # Vehicle ID from params or top-level
        params = data.get("params")
        if isinstance(params, dict) and params.get("vehicle_id"):
            attrs["vehicle_id"] = params["vehicle_id"]
        elif data.get("vehicle_id"):
            attrs["vehicle_id"] = data["vehicle_id"]
        return attrs

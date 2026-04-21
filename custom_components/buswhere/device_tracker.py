"""Device tracker platform for BusWhere shuttle."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ORG, CONF_ROUTE_ID, DOMAIN
from .coordinator import BusWhereCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BusWhere device tracker."""
    coordinator: BusWhereCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([BusWhereTracker(coordinator, entry)])


class BusWhereTracker(CoordinatorEntity[BusWhereCoordinator], TrackerEntity):
    """Represents the shuttle bus on the map."""

    _attr_has_entity_name = True
    _attr_name = "Bus"
    _attr_icon = "mdi:bus"

    def __init__(
        self,
        coordinator: BusWhereCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        org = entry.data[CONF_ORG]
        route_id = entry.data[CONF_ROUTE_ID]
        self._attr_unique_id = f"{org}_{route_id}_tracker"
        self._attr_device_info = _device_info(entry)

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        if self.coordinator.data and self.coordinator.data.get("current"):
            return self.coordinator.data["current"].get("lat")
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        if self.coordinator.data and self.coordinator.data.get("current"):
            return self.coordinator.data["current"].get("lon")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        attrs: dict[str, Any] = {}
        if data.get("last_known_address"):
            attrs["last_known_address"] = data["last_known_address"]
        if data.get("vehicle_id"):
            attrs["vehicle_id"] = data["vehicle_id"]
        params = data.get("params")
        if isinstance(params, dict) and params.get("vehicle_id"):
            attrs["vehicle_id"] = params["vehicle_id"]
        if data.get("started_at"):
            attrs["started_at"] = data["started_at"]
        return attrs


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    """Return device info shared by all entities of this route."""
    org = entry.data[CONF_ORG]
    route_id = entry.data[CONF_ROUTE_ID]
    return {
        "identifiers": {(DOMAIN, f"{org}_{route_id}")},
        "name": f"BusWhere {route_id.replace('_', ' ').title()}",
        "manufacturer": "BusWhere",
        "model": org.title(),
    }

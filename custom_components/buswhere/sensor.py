"""Sensor platform for BusWhere shuttle — route status + per-stop ETAs."""
from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ORG, CONF_ROUTE_ID, CONF_STOP_NAMES, DOMAIN
from .coordinator import BusWhereCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BusWhere sensors."""
    coordinator: BusWhereCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = [
        BusWhereStatusSensor(coordinator, entry),
    ]

    # Create a sensor for each stop (from the initial full data)
    stops = coordinator.data.get("stops", []) if coordinator.data else []
    for stop in stops:
        entities.append(BusWhereStopEtaSensor(coordinator, entry, stop))

    async_add_entities(entities)


class BusWhereStatusSensor(CoordinatorEntity[BusWhereCoordinator], SensorEntity):
    """Sensor showing overall route status."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:bus-alert"

    def __init__(
        self,
        coordinator: BusWhereCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)
        org = entry.data[CONF_ORG]
        route_id = entry.data[CONF_ROUTE_ID]
        self._attr_unique_id = f"{org}_{route_id}_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{org}_{route_id}")},
        }

    @property
    def native_value(self) -> str:
        """Return the route status."""
        if not self.coordinator.data:
            return "unknown"
        data = self.coordinator.data
        if data.get("suspended"):
            return "suspended"
        if data.get("active"):
            return "running"
        return "not_running"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        attrs: dict[str, Any] = {}
        if data.get("message"):
            attrs["message"] = data["message"]
        if data.get("starts_at"):
            attrs["service_start"] = data["starts_at"]
        if data.get("ends_at"):
            attrs["service_end"] = data["ends_at"]
        if data.get("active_days"):
            attrs["active_days"] = _format_active_days(data["active_days"])
            attrs["active_days_raw"] = data["active_days"]
        if data.get("last_known_address"):
            attrs["last_known_address"] = data["last_known_address"]
        # Include stop summary
        stops = data.get("stops", [])
        if stops:
            attrs["stop_count"] = len(stops)
            stop_names = [
                s.get("address") or s.get("name") for s in stops
            ]
            attrs["stops"] = stop_names
        return attrs


class BusWhereStopEtaSensor(CoordinatorEntity[BusWhereCoordinator], SensorEntity):
    """Sensor showing ETA to a specific stop."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bus-stop"
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self,
        coordinator: BusWhereCoordinator,
        entry: ConfigEntry,
        stop: dict[str, Any],
    ) -> None:
        """Initialize the stop ETA sensor."""
        super().__init__(coordinator)
        org = entry.data[CONF_ORG]
        route_id = entry.data[CONF_ROUTE_ID]
        self._entry = entry
        self._stop_id = stop["id"]
        self._stop_order = stop.get("order", 0)
        # Unique ID keyed by order (stable), not by id (can change per session)
        self._attr_unique_id = f"{org}_{route_id}_stop_{self._stop_order}_eta"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{org}_{route_id}")},
        }

    @property
    def name(self) -> str:
        """Return the entity name, dynamically reading custom names from options."""
        custom_names = self._entry.options.get(CONF_STOP_NAMES, {})
        custom_name = custom_names.get(str(self._stop_order))
        if custom_name:
            return f"{custom_name} ETA"
        return f"Stop {self._stop_order} ETA"

    def _find_stop(self) -> dict[str, Any] | None:
        """Find this stop in the current coordinator data."""
        if not self.coordinator.data:
            return None
        # Match by order (stable) first, fall back to id
        for stop in self.coordinator.data.get("stops", []):
            if stop.get("order") == self._stop_order:
                return stop
        for stop in self.coordinator.data.get("stops", []):
            if stop["id"] == self._stop_id:
                return stop
        return None

    @property
    def native_value(self) -> int | None:
        """Return ETA in minutes, or None if unavailable."""
        if not self.coordinator.data or not self.coordinator.data.get("active"):
            return None

        stop = self._find_stop()
        if not stop:
            return None

        if stop.get("arrived"):
            return 0
        if stop.get("departed") or stop.get("skipped"):
            return None

        eta_seconds = stop.get("eta")
        if eta_seconds is not None:
            return max(0, math.ceil(eta_seconds / 60))
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Only show unit when we have a numeric value."""
        stop = self._find_stop()
        if stop and (stop.get("arrived") or stop.get("departed") or stop.get("skipped")):
            return None
        if not self.coordinator.data or not self.coordinator.data.get("active"):
            return None
        return "min"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes about this stop."""
        stop = self._find_stop()
        if not stop:
            return {}
        attrs: dict[str, Any] = {
            "stop_id": stop["id"],
            "stop_name": stop.get("name"),
            "address": stop.get("address"),
            "stop_lat": stop.get("lat"),
            "stop_lon": stop.get("lon"),
            "order": stop.get("order"),
            "arrived": stop.get("arrived", False),
            "departed": stop.get("departed", False),
            "skipped": stop.get("skipped", False),
        }
        if stop.get("state"):
            attrs["state"] = stop["state"]
        eta_seconds = stop.get("eta")
        if eta_seconds is not None:
            attrs["eta_seconds"] = eta_seconds
        return attrs


def _format_active_days(days_str: str) -> str:
    """Convert '0111110' to 'Mon-Fri' style string."""
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    if len(days_str) != 7:
        return days_str
    active = [day_names[i] for i, ch in enumerate(days_str) if ch == "1"]
    if not active:
        return "None"
    if len(active) == 7:
        return "Every day"
    # Check for Mon-Fri
    if active == ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        return "Mon-Fri"
    return ", ".join(active)

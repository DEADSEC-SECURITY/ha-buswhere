"""BusWhere Shuttle Tracker integration for Home Assistant."""
from __future__ import annotations

import logging
import re

from homeassistant.components import zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ORG, CONF_ROUTE_ID, CONF_SCAN_INTERVAL, CONF_STOP_NAMES, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import BusWhereCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

DEFAULT_ZONE_RADIUS = 80  # meters — matches BusWhere's stop_threshold (~79m)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BusWhere from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    org = entry.data[CONF_ORG]
    route_id = entry.data[CONF_ROUTE_ID]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = BusWhereCoordinator(hass, org, route_id, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "zones_created": [],
    }

    # Create zones for each stop
    await _create_stop_zones(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options change (e.g., stop names)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove created zones
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        zone_ids = hass.data[DOMAIN][entry.entry_id].get("zones_created", [])
        await _remove_zones(hass, zone_ids)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def _slugify(text: str) -> str:
    """Create a slug from text."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    slug = slug.strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:50]


async def _create_stop_zones(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BusWhereCoordinator,
) -> None:
    """Create Home Assistant zones for each shuttle stop."""
    if not coordinator.data:
        return

    stops = coordinator.data.get("stops", [])
    if not stops:
        return

    route_id = entry.data[CONF_ROUTE_ID]
    custom_names = entry.options.get(CONF_STOP_NAMES, {})

    # Access zone storage collection
    if zone.DOMAIN not in hass.data:
        _LOGGER.warning("Zone integration not loaded, skipping stop zone creation")
        return

    storage_collection = hass.data[zone.DOMAIN]
    if not hasattr(storage_collection, "async_create_item"):
        _LOGGER.warning("Zone storage does not support async_create_item")
        return

    created_ids = []
    for stop in stops:
        stop_id_str = str(stop["id"])
        # Use custom name if set, otherwise fall back to address
        display_name = custom_names.get(stop_id_str) or stop.get("address") or f"Stop {stop.get('order', '?')}"
        slug_name = _slugify(f"buswhere_{route_id}_{display_name}")

        # Check if zone already exists
        existing_id = None
        try:
            for item in storage_collection.async_items():
                if item.get("name") == slug_name:
                    existing_id = item.get("id")
                    break
        except Exception as err:
            _LOGGER.debug("Could not check existing zones: %s", err)

        radius = float(stop.get("stop_threshold", DEFAULT_ZONE_RADIUS))
        zone_data = {
            "name": slug_name,
            "latitude": stop["lat"],
            "longitude": stop["lon"],
            "radius": radius,
            "icon": "mdi:bus-stop",
            "passive": False,
        }

        try:
            if existing_id:
                await storage_collection.async_update_item(existing_id, zone_data)
                created_ids.append(existing_id)
                _LOGGER.debug("Updated stop zone: %s (%s)", slug_name, stop_address)
            else:
                result = await storage_collection.async_create_item(zone_data)
                new_id = result.get("id") if isinstance(result, dict) else None
                if new_id:
                    created_ids.append(new_id)
                _LOGGER.debug("Created stop zone: %s (%s)", slug_name, stop_address)
        except Exception as err:
            _LOGGER.warning("Failed to create stop zone %s: %s", slug_name, err)

    hass.data[DOMAIN][entry.entry_id]["zones_created"] = created_ids
    _LOGGER.info("Created %d stop zones for route %s", len(created_ids), route_id)


async def _remove_zones(hass: HomeAssistant, zone_ids: list[str]) -> None:
    """Remove zones created by this integration."""
    if zone.DOMAIN not in hass.data:
        return

    storage_collection = hass.data[zone.DOMAIN]
    for zone_id in zone_ids:
        try:
            await storage_collection.async_delete_item(zone_id)
            _LOGGER.debug("Removed stop zone: %s", zone_id)
        except Exception:
            _LOGGER.debug("Zone %s already removed or not found", zone_id)

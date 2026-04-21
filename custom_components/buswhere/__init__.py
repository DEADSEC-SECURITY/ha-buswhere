"""BusWhere Shuttle Tracker integration for Home Assistant."""
from __future__ import annotations

import logging
import re

from homeassistant.components import zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await _create_stop_zones(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove all zones created for this route when the entry is deleted."""
    await _remove_route_zones(hass, entry.data[CONF_ROUTE_ID])


def _slugify(text: str) -> str:
    """Create a slug from text."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    slug = slug.strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:50]


def _route_zone_prefix(route_id: str) -> str:
    """Return the name prefix shared by all zones belonging to this route."""
    return "buswhere_" + _slugify(route_id) + "_"


async def _create_stop_zones(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BusWhereCoordinator,
) -> None:
    """Create or update Home Assistant zones for each shuttle stop.

    Orphaned zones (from renamed/removed stops) are deleted automatically.
    """
    if not coordinator.data:
        return

    stops = coordinator.data.get("stops", [])
    if not stops:
        return

    route_id = entry.data[CONF_ROUTE_ID]
    custom_names = entry.options.get(CONF_STOP_NAMES, {})
    prefix = _route_zone_prefix(route_id)

    storage_collection = hass.data.get(zone.DOMAIN)
    if storage_collection is None or not hasattr(storage_collection, "async_create_item"):
        _LOGGER.warning("Zone integration not loaded, skipping stop zone creation")
        return

    ent_reg = er.async_get(hass)

    # Build the desired zone set: slug_name → (zone_data, display_name)
    desired: dict[str, tuple[dict, str]] = {}
    for stop in stops:
        order = str(stop.get("order", stop["id"]))
        display_name = custom_names.get(order) or stop.get("address") or f"Stop {order}"
        slug_name = _slugify(f"buswhere_{route_id}_{display_name}")
        zone_data = {
            "name": slug_name,
            "latitude": stop["lat"],
            "longitude": stop["lon"],
            "radius": float(stop.get("stop_threshold", DEFAULT_ZONE_RADIUS)),
            "icon": "mdi:bus-stop",
            "passive": False,
        }
        desired[slug_name] = (zone_data, display_name)

    # Index all existing zones that belong to this route (by prefix or exact name match)
    existing: dict[str, str] = {}  # slug_name → zone_id
    for item in storage_collection.async_items():
        name = item.get("name", "")
        if name.startswith(prefix) or name in desired:
            existing[name] = item.get("id")

    # Delete orphaned zones (stop was renamed or removed)
    for name, zone_id in existing.items():
        if name not in desired:
            try:
                await storage_collection.async_delete_item(zone_id)
                _LOGGER.debug("Removed orphaned stop zone: %s", name)
            except Exception:
                pass

    # Create or update desired zones, then set the friendly display name
    for slug_name, (zone_data, display_name) in desired.items():
        existing_id = existing.get(slug_name)
        try:
            if existing_id:
                await storage_collection.async_update_item(existing_id, zone_data)
                _LOGGER.debug("Updated stop zone: %s", slug_name)
            else:
                await storage_collection.async_create_item(zone_data)
                _LOGGER.debug("Created stop zone: %s", slug_name)
        except Exception as err:
            _LOGGER.warning("Failed to manage stop zone %s: %s", slug_name, err)
            continue

        # Override the display label shown in the UI / on the map
        entity_id = f"zone.{slug_name}"
        if ent_reg.async_get(entity_id):
            ent_reg.async_update_entity(entity_id, name=display_name)

    _LOGGER.info("Synced %d stop zones for route %s", len(desired), route_id)


async def _remove_route_zones(hass: HomeAssistant, route_id: str) -> None:
    """Delete all zones whose names match the route prefix."""
    storage_collection = hass.data.get(zone.DOMAIN)
    if storage_collection is None or not hasattr(storage_collection, "async_delete_item"):
        return

    prefix = _route_zone_prefix(route_id)
    to_delete = [
        item.get("id")
        for item in storage_collection.async_items()
        if item.get("name", "").startswith(prefix)
    ]
    for zone_id in to_delete:
        try:
            await storage_collection.async_delete_item(zone_id)
            _LOGGER.debug("Removed stop zone %s", zone_id)
        except Exception:
            _LOGGER.debug("Zone %s already removed or not found", zone_id)

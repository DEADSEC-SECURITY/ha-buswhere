"""Config flow for BusWhere integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_ORG,
    CONF_ROUTE_ID,
    CONF_ROUTE_URL,
    CONF_SCAN_INTERVAL,
    CONF_STOP_NAMES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r"https?://buswhere\.com/([^/]+)/routes/([^/?#]+)"
)


class BusWhereConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BusWhere."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step — enter route URL."""
        errors = {}

        if user_input is not None:
            url = user_input[CONF_ROUTE_URL].strip().rstrip("/")
            match = URL_PATTERN.match(url)
            if not match:
                errors["base"] = "invalid_url"
            else:
                org = match.group(1)
                route_id = match.group(2)

                # Check for duplicates
                await self.async_set_unique_id(f"{org}_{route_id}")
                self._abort_if_unique_id_configured()

                # Validate by fetching the page
                if await self._validate_route(org, route_id):
                    scan_interval = user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    )
                    title = f"BusWhere {route_id.replace('_', ' ').title()}"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_ORG: org,
                            CONF_ROUTE_ID: route_id,
                            CONF_SCAN_INTERVAL: scan_interval,
                        },
                    )
                else:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ROUTE_URL): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=300,
                            step=5,
                            unit_of_measurement="seconds",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    async def _validate_route(org: str, route_id: str) -> bool:
        """Validate that we can fetch data from the route."""
        url = f"https://buswhere.com/{org}/routes/{route_id}"
        headers = {
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params={"t": "0", "initial": "true", "filter": ""},
                ) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.json()
                    return "current" in data
        except Exception:
            _LOGGER.exception("Error validating BusWhere route")
            return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return BusWhereOptionsFlow(config_entry)


class BusWhereOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for BusWhere — rename stops."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show form with current stop names for editing."""
        if user_input is not None:
            # Extract stop names from the flat form keys (stop_order_<N>)
            stop_names: dict[str, str] = {}
            for key, value in user_input.items():
                if key.startswith("stop_order_") and value:
                    order = key[len("stop_order_"):]
                    stop_names[order] = value.strip()

            return self.async_create_entry(
                title="",
                data={CONF_STOP_NAMES: stop_names},
            )

        # Get stops from the coordinator
        entry_data = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry.entry_id, {}
        )
        coordinator = entry_data.get("coordinator")
        stops = []
        if coordinator and coordinator.data:
            stops = coordinator.data.get("stops", [])

        # Get existing custom names (keyed by order)
        existing_names = self._config_entry.options.get(CONF_STOP_NAMES, {})

        # Build schema with one text field per stop, keyed by order
        schema_dict: dict[Any, Any] = {}
        for stop in sorted(stops, key=lambda s: s.get("order", 0)):
            order = str(stop.get("order", stop["id"]))
            default_name = stop.get("address") or f"Stop {order}"
            current_name = existing_names.get(order, default_name)

            schema_dict[
                vol.Optional(
                    f"stop_order_{order}",
                    description={"suggested_value": current_name},
                )
            ] = TextSelector(TextSelectorConfig())

        if not schema_dict:
            schema_dict[
                vol.Optional("_no_stops")
            ] = TextSelector(TextSelectorConfig())

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "stop_info": "\n".join(
                    f"Stop {s.get('order', '?')}: {s.get('address', 'Unknown')}"
                    for s in sorted(stops, key=lambda s: s.get("order", 0))
                )
            },
        )

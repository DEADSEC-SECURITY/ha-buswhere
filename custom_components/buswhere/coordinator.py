"""DataUpdateCoordinator for BusWhere shuttle tracking."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL, DEFAULT_SCAN_INTERVAL, FULL_REFRESH_INTERVAL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class BusWhereCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls BusWhere for shuttle data."""

    def __init__(
        self,
        hass: HomeAssistant,
        org: str,
        route_id: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"buswhere_{org}_{route_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.org = org
        self.route_id = route_id
        self._url = f"{BASE_URL}/{org}/routes/{route_id}"
        self._full_data: dict[str, Any] | None = None
        self._last_full_fetch: float = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from BusWhere."""
        now = time.monotonic()
        needs_full = (
            self._full_data is None
            or (now - self._last_full_fetch) >= FULL_REFRESH_INTERVAL
        )

        try:
            if needs_full:
                data = await self._fetch_full()
                self._full_data = data
                self._last_full_fetch = now
            else:
                poll = await self._fetch_poll()
                data = {**self._full_data, **poll}
                self._full_data = data
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with BusWhere: {err}") from err
        except (json.JSONDecodeError, ValueError) as err:
            raise UpdateFailed(f"Error parsing BusWhere data: {err}") from err

        return data

    async def _fetch_full(self) -> dict[str, Any]:
        """Fetch the full HTML page and parse Maps.data for complete route info."""
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession() as session:
            async with session.get(self._url, headers=headers) as resp:
                resp.raise_for_status()
                html = await resp.text()

        return self._parse_maps_data(html)

    async def _fetch_poll(self) -> dict[str, Any]:
        """Fetch the lightweight JSON polling endpoint."""
        params = {
            "t": str(int(time.time() * 1000)),
            "initial": "true",
            "filter": "",
        }
        headers = {
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self._url, params=params, headers=headers
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    @staticmethod
    def _parse_maps_data(html: str) -> dict[str, Any]:
        """Extract and parse the Maps.data JSON object from the HTML page."""
        idx = html.find("Maps.data =")
        if idx == -1:
            raise ValueError("Could not find Maps.data in page")

        # Find the opening brace
        brace_start = html.index("{", idx)

        # Walk forward counting braces to find the matching close
        depth = 0
        end = brace_start
        in_string = False
        escape_next = False
        for i in range(brace_start, len(html)):
            ch = html[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        raw = html[brace_start:end]

        # The JS object may contain unquoted keys or URL values that are valid JS
        # but not strict JSON. The BusWhere output is clean JSON though, so try
        # direct parse first, then fall back to a light cleanup.
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Strip JS-style trailing commas before } or ]
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            return json.loads(cleaned)

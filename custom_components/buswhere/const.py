"""Constants for the BusWhere integration."""

DOMAIN = "buswhere"

CONF_ROUTE_URL = "route_url"
CONF_ORG = "org"
CONF_ROUTE_ID = "route_id"
CONF_SCAN_INTERVAL = "scan_interval"

CONF_STOP_NAMES = "stop_names"

DEFAULT_SCAN_INTERVAL = 30  # seconds
FULL_REFRESH_INTERVAL = 300  # 5 minutes — re-fetch HTML for stop ETAs

BASE_URL = "https://buswhere.com"

USER_AGENT = "HomeAssistant-BusWhere/1.0"

# BusWhere Shuttle Tracker for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Track university shuttle buses from [BusWhere](https://buswhere.com) in Home Assistant. Get real-time GPS position, stop ETAs, and service status directly in your dashboard.

## Features

- **Live bus tracking** on the HA map via device tracker
- **Per-stop ETA sensors** showing minutes until arrival
- **Stop zones** on the map as named locations
- **Route status** sensor (running / not running / suspended)
- **Active binary sensor** for simple automations
- **Custom stop names** — rename stops via the integration options
- **No API key required** — works out of the box

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select **Custom repositories**
4. Add this repository URL and select **Integration** as the category
5. Click **Add**
6. Search for "BusWhere" and install it
7. Restart Home Assistant

### Manual

1. Copy the `custom_components/buswhere` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **BusWhere Shuttle Tracker**
3. Enter your BusWhere route URL (e.g., `https://buswhere.com/theory/routes/theory_shuttle`)
4. Optionally adjust the polling interval (default: 30 seconds)

### Finding your route URL

1. Go to [buswhere.com](https://buswhere.com)
2. Navigate to your school/organization
3. Select your shuttle route
4. Copy the URL from your browser — it should look like: `https://buswhere.com/{org}/routes/{route_id}`

## Entities

Once configured, the integration creates a device with these entities:

| Entity | Type | Description |
|--------|------|-------------|
| `device_tracker.buswhere_{route}_bus` | Device Tracker | Bus GPS position on the map |
| `sensor.buswhere_{route}_status` | Sensor | Route status: running / not_running / suspended |
| `binary_sensor.buswhere_{route}_active` | Binary Sensor | Whether the bus is currently active |
| `sensor.buswhere_{route}_stop_{N}_eta` | Sensor | ETA in minutes to each stop |

Additionally, **zones** are created for each stop on the route so they appear as named locations on your map.

## Renaming Stops

The default stop names come from BusWhere (usually street addresses). To customize them:

1. Go to **Settings** > **Devices & Services**
2. Find the BusWhere integration and click **Configure**
3. Enter custom names for each stop
4. The zones, and ETA sensor names will update automatically

## Automation Examples

### Notify when shuttle is close to your stop

```yaml
automation:
  - alias: "Shuttle approaching my stop"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.buswhere_theory_shuttle_stop_3_eta
        below: 3
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Shuttle Alert"
          message: >
            Shuttle arriving at your stop in
            {{ states('sensor.buswhere_theory_shuttle_stop_3_eta') }} minutes!
```

### Turn on porch light when shuttle is near home

```yaml
automation:
  - alias: "Shuttle near home"
    triggers:
      - trigger: zone
        entity_id: device_tracker.buswhere_theory_shuttle_bus
        zone: zone.home
        event: enter
    actions:
      - action: light.turn_on
        target:
          entity_id: light.porch
```

### Morning notification if shuttle is not running

```yaml
automation:
  - alias: "Shuttle not running alert"
    triggers:
      - trigger: time
        at: "07:30:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.buswhere_theory_shuttle_active
        state: "off"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Shuttle Status"
          message: "The shuttle is not running right now."
```

## How it works

The integration polls the BusWhere website:

- **Every 30 seconds** (configurable): lightweight JSON poll for current GPS position and active status
- **Every 5 minutes**: full page fetch to update stop ETAs, waypoints, and service metadata

No authentication or API keys are required. The integration uses the same public endpoints as the BusWhere website.

## Supported organizations

Any organization using BusWhere should work. The URL format is always `https://buswhere.com/{org}/routes/{route_id}`. Some known organizations:

- Syracuse University (`theory`)
- And many more — check [buswhere.com](https://buswhere.com)

## Troubleshooting

- **Entities show "unavailable"**: The bus may not be running. Check the `active_days` and `service_start`/`service_end` attributes on the status sensor.
- **ETAs are `None`**: The bus is either not active, or the stop has already been departed/skipped.
- **Zones not appearing**: Make sure the Zone integration is loaded (it is by default). Check logs for any errors.

## License

MIT

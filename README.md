# Wall Dashboard MVP

Lightweight wall dashboard built with FastAPI and plain HTML/CSS/JavaScript for an always-on older iPad.

## Features

- FastAPI backend that aggregates Home Assistant data
- Very lightweight frontend with no build step and no framework
- Home Assistant token stays on the backend
- Simple in-memory caching with 5 second TTL and stale fallback
- Dashboard pages and widgets configured through `dashboard.yaml`
- Heater controls and scene triggers routed through the backend
- Config changes are picked up without rebuilding the container

## Project Layout

```text
app/
  core/
    errors.py
    orchestrator.py
    provider_base.py
  main.py
  config.py
  providers/
    home_assistant.py
    weather.py
    mail.py
    fx.py
    calendar.py
  routers/
    dashboard.py
    actions.py
    health.py
  schemas/
    dashboard.py
    actions.py
  services/
    home_assistant.py
    cache.py
  static/
    index.html
    styles.css
    app.js
dashboard.yaml
requirements.txt
Dockerfile
docker-compose.yml
.env.example
README.md
```

## Configuration

Copy the example file and update it with your Home Assistant values:

```bash
cp .env.example .env
```

Environment variables:

```env
# Optional; defaults to 8080
APP_PORT=8080
HA_BASE_URL=
HA_TOKEN=
# Optional; defaults to ./dashboard.yaml
DASHBOARD_CONFIG_PATH=./dashboard.yaml
```

Dashboard layout lives in `dashboard.yaml`. It defines pages and widgets:

```yaml
default_page: home

pages:
  - id: home
    title: "1"
    widgets:
      - id: weather
        type: weather
        title: Weather
        weather_entity: weather.home
        rows:
          - label: Indoor
            entity: sensor.living_room_temperature
          - label: Humidity
            entity: sensor.living_room_humidity
          - label: CO2
            entity: sensor.living_room_co2

      - id: scenes
        type: scenes
        title: Scenes
        wide: true
        scenes:
          - id: morning
            name: Morning
            entity: scene.morning

  - id: climate
    title: "2"
    widgets:
      - id: heater
        type: heater
        title: Heater
        entity: climate.living_room
```

Supported widget types:

- `weather`: main weather entity plus extra sensor rows
- `sensor`: one large sensor value plus optional rows
- `heater`: toggle + mode buttons for a climate/select/water_heater entity
- `scenes`: one or more scene buttons

### Home Assistant Setup

1. Create a long-lived access token in Home Assistant.
2. Put your Home Assistant URL and token into `.env`.
3. Put entity IDs and page/widget layout into `dashboard.yaml`.
4. Make sure this app can reach your Home Assistant URL from the machine that runs it.

## Run Locally

Install dependencies with `uv`:

```bash
uv sync --dev
```

Load environment variables and start the server:

```bash
set -a
source .env
set +a
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "${APP_PORT:-8080}"
```

Open the dashboard at [http://localhost:8080](http://localhost:8080) by default, or use your `APP_PORT` value.

When you edit `dashboard.yaml`, the backend reloads it automatically on the next poll and the frontend refreshes itself when the config version changes.

Run quality checks:

```bash
uv run --group dev ruff check .
uv run --group dev ty check app
```

## Run With Docker

```bash
cp .env.example .env
docker compose up --build
```

After the first build, editing `dashboard.yaml` does not require rebuilding the container. The file is bind-mounted into the container and reloaded automatically.

Then open [http://localhost:8080](http://localhost:8080) by default, or use your `APP_PORT` value.

## API Endpoints

- `GET /api/dashboard` returns aggregated dashboard data
- `POST /api/actions/heater/toggle` toggles the configured heater
- `POST /api/actions/heater/mode` changes the heater mode
- `POST /api/actions/scene/{scene_id}` triggers a configured scene
- `GET /api/health` returns service health

## Notes

- The frontend polls `/api/dashboard` every 15 seconds.
- The frontend performs a full page reload every 30 minutes, reloads after 10 seconds if the dashboard API is unavailable, and reloads when the YAML config version changes.
- The clock is updated locally in the browser every second.
- Missing or unavailable entities are shown as unavailable per widget.
- If `dashboard.yaml` becomes invalid, the last good config stays active and the UI shows the config error.
- On Home Assistant request failures, the backend returns the last known cached value when possible.
- `requirements.txt` is included for compatibility, and `uv` is the recommended workflow for local development.

## How To Add A New Provider

1. Create a new file in `app/providers/`, for example `app/providers/mail.py`.
2. Implement a class that inherits from `BaseProvider` in [app/core/provider_base.py](/Users/maxim/Documents/dev/repos/wallpad/app/core/provider_base.py).
3. Give the provider a unique `name` and implement `fetch()` to return normalized dashboard data.
4. If the provider calls an external API, use the shared cache via `self.get_cached(...)` or `self.cache.get_or_set_namespaced(...)`.
5. Return a safe fallback structure from `fetch()` if the provider cannot load fresh data.
6. Register the provider in [app/core/orchestrator.py](/Users/maxim/Documents/dev/repos/wallpad/app/core/orchestrator.py) inside `get_dashboard_orchestrator()`.

Example shape:

```python
from app.core.provider_base import BaseProvider, ProviderPayload


class MailProvider(BaseProvider):
    name = "mail"
    cache_ttl_seconds = 60

    async def fetch(self) -> ProviderPayload:
        self.set_available(True)
        return {
            "mail": {
                "available": True,
                "unread_count": 3,
                "items": [],
            }
        }
```

After registration, the provider payload will be merged automatically into `/api/dashboard` without changing routers or the existing frontend contract.

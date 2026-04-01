# Wall Dashboard MVP

Lightweight wall dashboard built with FastAPI and plain HTML/CSS/JavaScript for an always-on older iPad.

## Features

- FastAPI backend that aggregates Home Assistant data
- Very lightweight frontend with no build step and no framework
- Home Assistant token stays on the backend
- Simple in-memory caching with 5 second TTL and stale fallback
- Heater controls and scene triggers routed through the backend

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
HA_WEATHER_ENTITY=
HA_INDOOR_TEMP_ENTITY=
HA_OUTDOOR_TEMP_ENTITY=
HA_HEATER_ENTITY=
HA_SCENE_MORNING=
HA_SCENE_NIGHT=
HA_SCENE_AWAY=
```

### Home Assistant Setup

1. Create a long-lived access token in Home Assistant.
2. Find the entity IDs for your weather, indoor temperature, outdoor temperature, heater, and scenes.
3. Put those values into `.env`.
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

Then open [http://localhost:8080](http://localhost:8080) by default, or use your `APP_PORT` value.

## API Endpoints

- `GET /api/dashboard` returns aggregated dashboard data
- `POST /api/actions/heater/toggle` toggles the configured heater
- `POST /api/actions/heater/mode` changes the heater mode
- `POST /api/actions/scene/{scene_id}` triggers a configured scene
- `GET /api/health` returns service health

## Notes

- The frontend polls `/api/dashboard` every 15 seconds.
- The frontend also performs a full page reload every 30 minutes and reloads after 10 seconds if the dashboard API is unavailable.
- The clock is updated locally in the browser every second.
- Missing entities are handled gracefully and shown as unavailable.
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

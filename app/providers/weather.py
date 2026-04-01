from __future__ import annotations

from app.core.provider_base import BaseProvider, ProviderPayload


class WeatherProvider(BaseProvider):
    name = "weather_stub"
    cache_ttl_seconds = 300

    async def fetch(self) -> ProviderPayload:
        self.set_available(False)
        return {
            "weather_stub": {
                "available": False,
                "summary": "Weather provider placeholder",
            }
        }

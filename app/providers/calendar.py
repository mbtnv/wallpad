from __future__ import annotations

from app.core.provider_base import BaseProvider, ProviderPayload


class CalendarProvider(BaseProvider):
    name = "calendar"
    cache_ttl_seconds = 300

    async def fetch(self) -> ProviderPayload:
        self.set_available(False)
        return {
            "calendar": {
                "available": False,
                "events": [],
            }
        }

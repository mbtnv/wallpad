from __future__ import annotations

from app.core.provider_base import BaseProvider, ProviderPayload


class MailProvider(BaseProvider):
    name = "mail"
    cache_ttl_seconds = 60

    async def fetch(self) -> ProviderPayload:
        self.set_available(False)
        return {
            "mail": {
                "available": False,
                "unread_count": 0,
                "items": [],
            }
        }

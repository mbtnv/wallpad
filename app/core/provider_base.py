from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.services.cache import TTLCache

ProviderPayload = dict[str, Any]


@dataclass(slots=True)
class ProviderExecutionResult:
    name: str
    available: bool
    data: ProviderPayload


class BaseProvider(ABC):
    name: str = "base"
    cache_ttl_seconds: int = 5

    def __init__(self, cache: TTLCache) -> None:
        self.cache = cache
        self._available = False

    @abstractmethod
    async def fetch(self) -> ProviderPayload:
        """Return structured provider data."""

    async def is_available(self) -> bool:
        """Return True if provider is operational."""
        return self._available

    async def aclose(self) -> None:
        """Release provider resources if needed."""

    def fallback_payload(self) -> ProviderPayload:
        """Return a safe fallback payload when fetching fails."""
        return {}

    def set_available(self, available: bool) -> None:
        self._available = available

    def build_cache_key(self, key: str) -> str:
        return self.cache.build_key(f"provider:{self.name}", key)

    async def get_cached(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: int | None = None,
    ) -> Any:
        return await self.cache.get_or_set_namespaced(
            namespace=f"provider:{self.name}",
            key=key,
            loader=loader,
            ttl_seconds=ttl_seconds or self.cache_ttl_seconds,
        )

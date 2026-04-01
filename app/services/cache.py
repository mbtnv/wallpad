from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import RLock
from typing import Any

_MISSING = object()


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime
    stored_at: datetime


class TTLCache:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = RLock()

    def build_key(self, namespace: str, key: str) -> str:
        if not namespace:
            return key
        return f"{namespace}:{key}"

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._entries.get(key)

        if entry is None:
            return _MISSING

        if entry.expires_at <= self._now():
            return _MISSING

        return entry.value

    def get_last_known(self, key: str) -> Any:
        with self._lock:
            entry = self._entries.get(key)

        if entry is None:
            return _MISSING

        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> Any:
        now = self._now()
        entry = CacheEntry(
            value=value,
            expires_at=now + timedelta(seconds=max(ttl_seconds, 0)),
            stored_at=now,
        )
        with self._lock:
            self._entries[key] = entry
        return value

    def get_namespaced(self, namespace: str, key: str) -> Any:
        return self.get(self.build_key(namespace, key))

    def get_last_known_namespaced(self, namespace: str, key: str) -> Any:
        return self.get_last_known(self.build_key(namespace, key))

    def set_namespaced(self, namespace: str, key: str, value: Any, ttl_seconds: int) -> Any:
        return self.set(self.build_key(namespace, key), value, ttl_seconds)

    def invalidate(self, *keys: str) -> None:
        if not keys:
            return

        with self._lock:
            for key in keys:
                self._entries.pop(key, None)

    def invalidate_namespaced(self, namespace: str, *keys: str) -> None:
        self.invalidate(*(self.build_key(namespace, key) for key in keys))

    async def get_or_set(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: int,
    ) -> Any:
        cached_value = self.get(key)
        if cached_value is not _MISSING:
            return cached_value

        try:
            loaded_value = await loader()
        except Exception:
            stale_value = self.get_last_known(key)
            if stale_value is not _MISSING:
                return stale_value
            raise

        return self.set(key, loaded_value, ttl_seconds)

    async def get_or_set_namespaced(
        self,
        namespace: str,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: int,
    ) -> Any:
        return await self.get_or_set(
            key=self.build_key(namespace, key),
            loader=loader,
            ttl_seconds=ttl_seconds,
        )


@lru_cache(maxsize=1)
def get_cache() -> TTLCache:
    return TTLCache()

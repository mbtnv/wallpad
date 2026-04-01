from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.core.errors import ActionError, ConfigurationError, UpstreamError
from app.services.cache import TTLCache, get_cache


class HomeAssistantService:
    def __init__(self, settings: Settings, cache: TTLCache) -> None:
        self.settings = settings
        self.cache = cache
        headers = {"Content-Type": "application/json"}
        if settings.ha_token:
            headers["Authorization"] = f"Bearer {settings.ha_token}"

        base_url = settings.normalized_ha_base_url or "http://localhost"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=settings.ha_timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_entity_state(self, entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id or not self.settings.home_assistant_enabled:
            return None

        async def load_state() -> dict[str, Any] | None:
            try:
                response = await self._client.get(f"/api/states/{entity_id}")
            except httpx.HTTPError as exc:
                raise UpstreamError("Failed to contact Home Assistant.") from exc

            if response.status_code == 404:
                return None

            if response.is_error:
                raise UpstreamError(
                    f"Home Assistant returned status {response.status_code} for {entity_id}."
                )

            return response.json()

        return await self.cache.get_or_set_namespaced(
            namespace="ha",
            key=f"entity:{entity_id}",
            loader=load_state,
            ttl_seconds=self.settings.ha_cache_ttl_seconds,
        )

    async def call_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any] | None = None,
    ) -> list[Any] | dict[str, Any] | None:
        self._ensure_enabled()
        payload = data or {}

        try:
            response = await self._client.post(
                f"/api/services/{domain}/{service}",
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Failed to contact Home Assistant.") from exc

        if response.is_error:
            detail = self._extract_error_detail(response)
            raise ActionError(detail)

        if not response.content:
            self.invalidate_entity_states_from_payload(payload)
            return None

        self.invalidate_entity_states_from_payload(payload)
        return response.json()

    def invalidate_entity_states(self, *entity_ids: str) -> None:
        keys = [f"entity:{entity_id}" for entity_id in entity_ids if entity_id]
        if keys:
            self.cache.invalidate_namespaced("ha", *keys)

    def invalidate_entity_states_from_payload(self, payload: dict[str, Any]) -> None:
        entity_id = payload.get("entity_id")
        if isinstance(entity_id, list):
            self.invalidate_entity_states(
                *(item for item in entity_id if isinstance(item, str))
            )
            return
        if isinstance(entity_id, str):
            self.invalidate_entity_states(entity_id)

    def _extract_error_detail(self, response: httpx.Response) -> str:
        default_message = f"Home Assistant rejected the request with status {response.status_code}."
        try:
            payload = response.json()
        except ValueError:
            return default_message

        if isinstance(payload, dict):
            message = payload.get("message")
            if message:
                return str(message)

        return default_message

    def _ensure_enabled(self) -> None:
        if not self.settings.home_assistant_enabled:
            raise ConfigurationError(
                "Home Assistant is not configured. Set HA_BASE_URL and HA_TOKEN."
            )


@lru_cache(maxsize=1)
def get_home_assistant_service() -> HomeAssistantService:
    return HomeAssistantService(get_settings(), get_cache())

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import quote

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

    async def get_weather_forecast(
        self,
        entity_id: str | None,
        forecast_type: str = "hourly",
    ) -> list[dict[str, Any]] | None:
        if not entity_id or not self.settings.home_assistant_enabled:
            return None

        async def load_forecast() -> list[dict[str, Any]] | None:
            try:
                response = await self._client.post(
                    "/api/services/weather/get_forecasts?return_response",
                    json={"entity_id": entity_id, "type": forecast_type},
                )
            except httpx.HTTPError as exc:
                raise UpstreamError("Failed to contact Home Assistant.") from exc

            if response.status_code == 404:
                return None

            if response.is_error:
                raise UpstreamError(
                    f"Home Assistant returned status {response.status_code} for {entity_id} "
                    f"forecast."
                )

            payload = response.json()
            if not isinstance(payload, dict):
                return None

            service_response = payload.get("service_response")
            if not isinstance(service_response, dict):
                return None

            entity_payload = service_response.get(entity_id)
            if not isinstance(entity_payload, dict):
                return None

            forecast = entity_payload.get("forecast")
            if not isinstance(forecast, list):
                return None

            return [item for item in forecast if isinstance(item, dict)]

        return await self.cache.get_or_set_namespaced(
            namespace="ha",
            key=f"forecast:{forecast_type}:{entity_id}",
            loader=load_forecast,
            ttl_seconds=self.settings.ha_cache_ttl_seconds,
        )

    async def get_entity_history(
        self,
        entity_id: str | None,
        hours: int = 24,
    ) -> list[dict[str, Any]] | None:
        if not entity_id or not self.settings.home_assistant_enabled:
            return None

        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)

        async def load_history() -> list[dict[str, Any]] | None:
            try:
                response = await self._client.get(
                    f"/api/history/period/{quote(start_time.isoformat(timespec='seconds'))}",
                    params={
                        "filter_entity_id": entity_id,
                        "end_time": end_time.isoformat(timespec="seconds"),
                        "minimal_response": "1",
                        "no_attributes": "1",
                    },
                )
            except httpx.HTTPError as exc:
                raise UpstreamError("Failed to contact Home Assistant.") from exc

            if response.status_code == 404:
                return None

            if response.is_error:
                raise UpstreamError(
                    f"Home Assistant returned status {response.status_code} for {entity_id} "
                    f"history."
                )

            payload = response.json()
            if not isinstance(payload, list):
                return None

            history_items: list[dict[str, Any]] = []
            for entry in payload:
                if isinstance(entry, dict):
                    history_items.append(entry)
                    continue
                if not isinstance(entry, list):
                    continue
                history_items.extend(item for item in entry if isinstance(item, dict))

            return history_items

        return await self.cache.get_or_set_namespaced(
            namespace="ha",
            key=f"history:{entity_id}:{hours}",
            loader=load_history,
            ttl_seconds=self.settings.ha_cache_ttl_seconds,
        )

    async def get_timezone(self) -> str | None:
        if not self.settings.home_assistant_enabled:
            return None

        async def load_config() -> dict[str, Any] | None:
            try:
                response = await self._client.get("/api/config")
            except httpx.HTTPError as exc:
                raise UpstreamError("Failed to contact Home Assistant.") from exc

            if response.status_code == 404:
                return None

            if response.is_error:
                raise UpstreamError(
                    f"Home Assistant returned status {response.status_code} for config."
                )

            payload = response.json()
            return payload if isinstance(payload, dict) else None

        config = await self.cache.get_or_set_namespaced(
            namespace="ha",
            key="config",
            loader=load_config,
            ttl_seconds=self.settings.ha_cache_ttl_seconds,
        )
        if not isinstance(config, dict):
            return None

        time_zone = config.get("time_zone")
        if not isinstance(time_zone, str):
            return None

        normalized_timezone = time_zone.strip()
        return normalized_timezone or None

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

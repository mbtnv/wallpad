from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.core.errors import ActionError, ConfigurationError
from app.core.provider_base import BaseProvider, ProviderPayload
from app.services.cache import TTLCache
from app.services.home_assistant import HomeAssistantService

UNAVAILABLE_STATES = {"unavailable", "unknown", "none", ""}


class HomeAssistantProvider(BaseProvider):
    name = "home_assistant"

    def __init__(
        self,
        settings: Settings,
        service: HomeAssistantService,
        cache: TTLCache,
    ) -> None:
        super().__init__(cache)
        self.settings = settings
        self.service = service
        self.cache_ttl_seconds = settings.dashboard_cache_ttl_seconds

    async def fetch(self) -> ProviderPayload:
        if not self.settings.home_assistant_enabled:
            self.set_available(False)
            return self.fallback_payload()

        try:
            payload = await self.get_cached(
                key="dashboard",
                loader=self._load_dashboard_payload,
                ttl_seconds=self.cache_ttl_seconds,
            )
        except Exception:
            self.set_available(False)
            return self.fallback_payload()

        self.set_available(self._compute_availability(payload))
        return payload

    async def is_available(self) -> bool:
        return self.settings.home_assistant_enabled and await super().is_available()

    async def aclose(self) -> None:
        await self.service.aclose()

    def fallback_payload(self) -> ProviderPayload:
        return {
            "weather": {
                "available": False,
                "condition": None,
                "temperature": None,
                "temperature_unit": None,
                "humidity": None,
                "wind_speed": None,
                "wind_speed_unit": None,
                "friendly_name": None,
            },
            "home": {
                "indoor_temperature": None,
                "indoor_temperature_unit": None,
                "outdoor_temperature": None,
                "outdoor_temperature_unit": None,
            },
            "heater": {
                "available": False,
                "entity_id": self.settings.ha_heater_entity or None,
                "state": None,
                "is_on": False,
                "mode": None,
                "supported_modes": [],
                "friendly_name": "Heater",
            },
            "scenes": [
                {
                    "id": scene_id,
                    "name": self._humanize(scene_id),
                    "entity_id": entity_id,
                    "available": False,
                }
                for scene_id, entity_id in self.settings.scene_map.items()
            ],
        }

    async def toggle_heater(self) -> ProviderPayload:
        entity_id = self.settings.ha_heater_entity
        if not entity_id:
            raise ConfigurationError("HA_HEATER_ENTITY is not configured.")

        current_state = await self.service.get_entity_state(entity_id)
        service = "turn_on"
        target_state = "on"
        if current_state and self._state_is_on(current_state.get("state")):
            service = "turn_off"
            target_state = "off"

        result = await self.service.call_service(
            "homeassistant",
            service,
            {"entity_id": entity_id},
        )
        self._invalidate_dashboard_cache()
        return {
            "entity_id": entity_id,
            "target_state": target_state,
            "service_result": result,
        }

    async def set_heater_mode(self, mode: str) -> ProviderPayload:
        entity_id = self.settings.ha_heater_entity
        if not entity_id:
            raise ConfigurationError("HA_HEATER_ENTITY is not configured.")

        normalized_mode = mode.strip()
        if not normalized_mode:
            raise ActionError("Mode must not be empty.")

        current_state = await self.service.get_entity_state(entity_id)
        attributes = current_state.get("attributes", {}) if current_state else {}
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "climate"

        attempts = self._build_mode_attempts(
            domain=domain,
            entity_id=entity_id,
            mode=normalized_mode,
            attributes=attributes,
        )
        if not attempts:
            raise ActionError("Configured heater entity does not expose a supported mode service.")

        last_error: Exception | None = None
        for domain_name, service_name, payload in attempts:
            try:
                result = await self.service.call_service(domain_name, service_name, payload)
                self._invalidate_dashboard_cache()
                return {
                    "entity_id": entity_id,
                    "mode": normalized_mode,
                    "service": f"{domain_name}.{service_name}",
                    "service_result": result,
                }
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        raise ActionError("Failed to update heater mode.")

    async def trigger_scene(self, scene_id: str) -> ProviderPayload:
        entity_id = self.settings.scene_map.get(scene_id)
        if entity_id is None and scene_id.startswith("scene."):
            entity_id = scene_id

        if not entity_id:
            raise ActionError(f"Scene '{scene_id}' is not configured.")

        result = await self.service.call_service(
            "scene",
            "turn_on",
            {"entity_id": entity_id},
        )
        self._invalidate_dashboard_cache()
        return {
            "scene_id": scene_id,
            "entity_id": entity_id,
            "service_result": result,
        }

    async def _load_dashboard_payload(self) -> ProviderPayload:
        entity_requests = [
            ("weather", self.settings.ha_weather_entity),
            ("indoor", self.settings.ha_indoor_temp_entity),
            ("outdoor", self.settings.ha_outdoor_temp_entity),
            ("heater", self.settings.ha_heater_entity),
        ]
        scene_requests = [
            (f"scene:{scene_id}", entity_id)
            for scene_id, entity_id in self.settings.scene_map.items()
        ]
        all_requests = entity_requests + scene_requests

        results = await asyncio.gather(
            *(self.service.get_entity_state(entity_id) for _, entity_id in all_requests),
            return_exceptions=True,
        )

        states: dict[str, dict[str, Any] | None] = {}
        for request, result in zip(all_requests, results):
            key = request[0]
            states[key] = None if isinstance(result, Exception) else result

        payload = {
            "weather": self._build_weather(states.get("weather")),
            "home": self._build_home(
                indoor_state=states.get("indoor"),
                outdoor_state=states.get("outdoor"),
            ),
            "heater": self._build_heater(states.get("heater")),
            "scenes": self._build_scenes(states),
        }
        self.set_available(self._compute_availability(payload))
        return payload

    def _compute_availability(self, payload: ProviderPayload) -> bool:
        weather = payload.get("weather", {})
        home = payload.get("home", {})
        heater = payload.get("heater", {})
        scenes = payload.get("scenes", [])

        has_weather = isinstance(weather, dict) and bool(weather.get("available"))
        has_heater = isinstance(heater, dict) and bool(heater.get("available"))
        has_temperature = isinstance(home, dict) and (
            home.get("indoor_temperature") is not None
            or home.get("outdoor_temperature") is not None
        )
        has_scene = any(
            isinstance(scene, dict) and bool(scene.get("available"))
            for scene in scenes
            if isinstance(scenes, list)
        )
        return has_weather or has_heater or has_temperature or has_scene

    def _invalidate_dashboard_cache(self) -> None:
        self.cache.invalidate(self.build_cache_key("dashboard"))

    def _build_mode_attempts(
        self,
        domain: str,
        entity_id: str,
        mode: str,
        attributes: dict[str, Any],
    ) -> list[tuple[str, str, dict[str, Any]]]:
        attempts: list[tuple[str, str, dict[str, Any]]] = []

        if domain == "climate":
            preset_modes = self._normalize_mode_list(attributes.get("preset_modes"))
            hvac_modes = self._normalize_mode_list(attributes.get("hvac_modes"))
            if mode in preset_modes:
                attempts.append(
                    ("climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": mode})
                )
            if mode in hvac_modes:
                attempts.append(
                    ("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": mode})
                )
            if not attempts:
                attempts.append(
                    ("climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": mode})
                )
                attempts.append(
                    ("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": mode})
                )
            return attempts

        if domain == "water_heater":
            return [
                (
                    "water_heater",
                    "set_operation_mode",
                    {"entity_id": entity_id, "operation_mode": mode},
                )
            ]

        if domain == "select":
            return [("select", "select_option", {"entity_id": entity_id, "option": mode})]

        if domain == "input_select":
            return [
                ("input_select", "select_option", {"entity_id": entity_id, "option": mode})
            ]

        return attempts

    def _build_weather(self, state: dict[str, Any] | None) -> dict[str, Any]:
        if not state:
            return self.fallback_payload()["weather"]

        attributes = state.get("attributes", {})
        return {
            "available": self._state_is_available(state.get("state")),
            "condition": state.get("state"),
            "temperature": self._coerce_float(attributes.get("temperature")),
            "temperature_unit": attributes.get("temperature_unit"),
            "humidity": self._coerce_float(attributes.get("humidity")),
            "wind_speed": self._coerce_float(attributes.get("wind_speed")),
            "wind_speed_unit": attributes.get("wind_speed_unit"),
            "friendly_name": attributes.get("friendly_name"),
        }

    def _build_home(
        self,
        indoor_state: dict[str, Any] | None,
        outdoor_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        indoor_value, indoor_unit = self._extract_sensor_value(indoor_state)
        outdoor_value, outdoor_unit = self._extract_sensor_value(outdoor_state)
        return {
            "indoor_temperature": indoor_value,
            "indoor_temperature_unit": indoor_unit,
            "outdoor_temperature": outdoor_value,
            "outdoor_temperature_unit": outdoor_unit,
        }

    def _build_heater(self, state: dict[str, Any] | None) -> dict[str, Any]:
        if not state:
            return self.fallback_payload()["heater"]

        attributes = state.get("attributes", {})
        supported_modes = self._normalize_mode_list(
            attributes.get("preset_modes") or attributes.get("hvac_modes")
        )
        return {
            "available": self._state_is_available(state.get("state")),
            "entity_id": state.get("entity_id") or self.settings.ha_heater_entity or None,
            "state": state.get("state"),
            "is_on": self._state_is_on(state.get("state")),
            "mode": (
                attributes.get("preset_mode")
                or attributes.get("hvac_mode")
                or state.get("state")
            ),
            "supported_modes": supported_modes,
            "friendly_name": attributes.get("friendly_name") or "Heater",
        }

    def _build_scenes(self, states: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for scene_id, entity_id in self.settings.scene_map.items():
            state = states.get(f"scene:{scene_id}")
            attributes = state.get("attributes", {}) if state else {}
            scenes.append(
                {
                    "id": scene_id,
                    "name": attributes.get("friendly_name") or self._humanize(scene_id),
                    "entity_id": entity_id,
                    "available": state is not None,
                }
            )
        return scenes

    def _extract_sensor_value(
        self,
        state: dict[str, Any] | None,
    ) -> tuple[float | None, str | None]:
        if not state or not self._state_is_available(state.get("state")):
            return None, None

        attributes = state.get("attributes", {})
        return self._coerce_float(state.get("state")), attributes.get("unit_of_measurement")

    def _normalize_mode_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            if value is None:
                continue
            normalized.append(str(value))
        return normalized

    def _state_is_available(self, state: Any) -> bool:
        if state is None:
            return False
        return str(state).strip().lower() not in UNAVAILABLE_STATES

    def _state_is_on(self, state: Any) -> bool:
        if not self._state_is_available(state):
            return False
        return str(state).strip().lower() != "off"

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _humanize(self, value: str) -> str:
        return value.replace("_", " ").strip().title()

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.core.errors import ActionError, ConfigurationError
from app.core.provider_base import BaseProvider, ProviderPayload
from app.schemas.dashboard_config import (
    DashboardConfig,
    HeaterWidgetConfig,
    SceneConfig,
    ScenesWidgetConfig,
    SensorRowConfig,
    SensorWidgetConfig,
    WeatherWidgetConfig,
    WidgetConfig,
)
from app.services.cache import TTLCache
from app.services.dashboard_config import DashboardConfigStore
from app.services.home_assistant import HomeAssistantService

UNAVAILABLE_STATES = {"unavailable", "unknown", "none", ""}
NO_SPACE_UNITS = {"%", "°C", "°F"}


class HomeAssistantProvider(BaseProvider):
    name = "home_assistant"

    def __init__(
        self,
        settings: Settings,
        service: HomeAssistantService,
        cache: TTLCache,
        config_store: DashboardConfigStore,
    ) -> None:
        super().__init__(cache)
        self.settings = settings
        self.service = service
        self.config_store = config_store
        self.cache_ttl_seconds = settings.dashboard_cache_ttl_seconds
        self._last_dashboard_cache_key: str | None = None

    async def fetch(self) -> ProviderPayload:
        snapshot = self.config_store.get_snapshot()
        cache_key = f"dashboard:{snapshot.version}"
        self._track_dashboard_cache_key(cache_key)

        if not self.settings.home_assistant_enabled:
            self.set_available(False)
            return self._build_payload(snapshot.config, snapshot.version, snapshot.error, {})

        try:
            payload = await self.get_cached(
                key=cache_key,
                loader=lambda: self._load_dashboard_payload(snapshot.config, snapshot.version),
                ttl_seconds=self.cache_ttl_seconds,
            )
        except Exception:
            self.set_available(False)
            return self.fallback_payload()

        payload["config_error"] = snapshot.error
        self.set_available(self._compute_availability(payload))
        return payload

    async def is_available(self) -> bool:
        return self.settings.home_assistant_enabled and await super().is_available()

    async def aclose(self) -> None:
        await self.service.aclose()

    def fallback_payload(self) -> ProviderPayload:
        snapshot = self.config_store.get_snapshot()
        return self._build_payload(snapshot.config, snapshot.version, snapshot.error, {})

    async def toggle_heater(self, widget_id: str | None = None) -> ProviderPayload:
        heater_widget = self._require_heater_widget(widget_id)
        entity_id = heater_widget.entity

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
            "widget_id": heater_widget.id,
            "target_state": target_state,
            "service_result": result,
        }

    async def set_heater_mode(self, mode: str, widget_id: str | None = None) -> ProviderPayload:
        heater_widget = self._require_heater_widget(widget_id)
        entity_id = heater_widget.entity

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
                    "widget_id": heater_widget.id,
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
        entity_id = self._resolve_scene_entity(scene_id)
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

    async def _load_dashboard_payload(
        self,
        config: DashboardConfig,
        version: str,
    ) -> ProviderPayload:
        states = await self._load_entity_states(config)
        payload = self._build_payload(config, version, None, states)
        self.set_available(self._compute_availability(payload))
        return payload

    async def _load_entity_states(
        self,
        config: DashboardConfig,
    ) -> dict[str, dict[str, Any] | None]:
        entity_ids = list(dict.fromkeys(self._collect_entity_ids(config)))
        results = await asyncio.gather(
            *(self.service.get_entity_state(entity_id) for entity_id in entity_ids),
            return_exceptions=True,
        )

        states: dict[str, dict[str, Any] | None] = {}
        for entity_id, result in zip(entity_ids, results):
            states[entity_id] = None if isinstance(result, Exception) else result
        return states

    def _collect_entity_ids(self, config: DashboardConfig) -> list[str]:
        entity_ids: list[str] = []
        for widget in config.iter_widgets():
            entity_ids.extend(self._collect_widget_entities(widget))
        return [entity_id for entity_id in entity_ids if entity_id]

    def _collect_widget_entities(self, widget: WidgetConfig) -> list[str]:
        if isinstance(widget, WeatherWidgetConfig):
            return [widget.weather_entity, *(row.entity for row in widget.rows)]
        if isinstance(widget, SensorWidgetConfig):
            return [widget.entity, *(row.entity for row in widget.rows)]
        if isinstance(widget, HeaterWidgetConfig):
            return [widget.entity]
        if isinstance(widget, ScenesWidgetConfig):
            return [scene.entity for scene in widget.scenes]
        return []

    def _build_payload(
        self,
        config: DashboardConfig,
        version: str,
        config_error: str | None,
        states: dict[str, dict[str, Any] | None],
    ) -> ProviderPayload:
        return {
            "config_version": version,
            "config_error": config_error,
            "default_page": config.resolved_default_page(),
            "pages": [self._build_page(page, states) for page in config.pages],
        }

    def _build_page(
        self,
        page: Any,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        return {
            "id": page.id,
            "title": page.title,
            "widgets": [self._build_widget(widget, states) for widget in page.widgets],
        }

    def _build_widget(
        self,
        widget: WidgetConfig,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        if isinstance(widget, WeatherWidgetConfig):
            return self._build_weather_widget(widget, states)
        if isinstance(widget, SensorWidgetConfig):
            return self._build_sensor_widget(widget, states)
        if isinstance(widget, HeaterWidgetConfig):
            return self._build_heater_widget(widget, states)
        if isinstance(widget, ScenesWidgetConfig):
            return self._build_scenes_widget(widget, states)

        return {
            "id": widget.id,
            "type": widget.type,
            "title": widget.title,
            "wide": widget.wide,
            "available": False,
            "primary_text": "--",
            "secondary_text": "Unsupported widget type",
            "rows": [],
            "actions": [],
        }

    def _build_weather_widget(
        self,
        widget: WeatherWidgetConfig,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        weather_state = states.get(widget.weather_entity)
        weather_available = self._state_is_available_from_state(weather_state)
        attributes = weather_state.get("attributes", {}) if weather_state else {}
        weather_condition = weather_state.get("state") if weather_state else None
        rows = [self._build_sensor_row(row, states.get(row.entity)) for row in widget.rows]

        return {
            "id": widget.id,
            "type": widget.type,
            "title": widget.title,
            "wide": widget.wide,
            "available": weather_available or any(row["available"] for row in rows),
            "primary_text": self._format_weather_temperature(weather_state),
            "secondary_text": (
                self._humanize(str(weather_condition))
                if weather_available and weather_condition is not None
                else attributes.get("friendly_name") or "Weather unavailable"
            ),
            "rows": rows,
            "actions": [],
        }

    def _build_sensor_widget(
        self,
        widget: SensorWidgetConfig,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        sensor_state = states.get(widget.entity)
        sensor_available = self._state_is_available_from_state(sensor_state)
        attributes = sensor_state.get("attributes", {}) if sensor_state else {}
        rows = [self._build_sensor_row(row, states.get(row.entity)) for row in widget.rows]

        return {
            "id": widget.id,
            "type": widget.type,
            "title": widget.title,
            "wide": widget.wide,
            "available": sensor_available or any(row["available"] for row in rows),
            "primary_text": self._format_entity_state(sensor_state),
            "secondary_text": (
                widget.subtitle
                or attributes.get("friendly_name")
                or ("Sensor unavailable" if not sensor_available else None)
            ),
            "rows": rows,
            "actions": [],
        }

    def _build_heater_widget(
        self,
        widget: HeaterWidgetConfig,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        state = states.get(widget.entity)
        available = self._state_is_available_from_state(state)
        attributes = state.get("attributes", {}) if state else {}
        current_mode = (
            attributes.get("preset_mode")
            or attributes.get("hvac_mode")
            or (state.get("state") if state else None)
        )
        supported_modes = self._normalize_mode_list(
            attributes.get("preset_modes") or attributes.get("hvac_modes")
        )
        is_on = available and bool(state) and self._state_is_on(state.get("state"))
        toggle_label = "Turn Off" if is_on else "Turn On"

        actions = [
            {
                "action": "heater_toggle",
                "label": toggle_label,
                "widget_id": widget.id,
                "disabled": not available,
                "variant": "primary",
            }
        ]
        actions.extend(
            {
                "action": "heater_mode",
                "label": self._humanize(mode),
                "widget_id": widget.id,
                "mode": mode,
                "disabled": not available,
                "active": mode == current_mode,
                "variant": "success" if mode == current_mode else "default",
            }
            for mode in supported_modes
        )

        return {
            "id": widget.id,
            "type": widget.type,
            "title": widget.title,
            "wide": widget.wide,
            "available": available,
            "primary_text": "On" if is_on else "Off",
            "secondary_text": (
                f"Mode: {self._humanize(str(current_mode))}"
                if available and current_mode
                else "No live state"
            ),
            "rows": [],
            "actions": actions,
        }

    def _build_scenes_widget(
        self,
        widget: ScenesWidgetConfig,
        states: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        actions = [
            self._build_scene_action(scene, states.get(scene.entity))
            for scene in widget.scenes
        ]
        return {
            "id": widget.id,
            "type": widget.type,
            "title": widget.title,
            "wide": widget.wide,
            "available": any(not action["disabled"] for action in actions),
            "primary_text": None,
            "secondary_text": "Tap to run a scene" if actions else "No scenes configured",
            "rows": [],
            "actions": actions,
        }

    def _build_scene_action(
        self,
        scene: SceneConfig,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "action": "scene",
            "label": scene.name,
            "scene_id": scene.id,
            "disabled": not self._scene_is_available(state),
            "variant": "primary",
        }

    def _build_sensor_row(
        self,
        row: SensorRowConfig,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        available = self._state_is_available_from_state(state)
        return {
            "label": row.label,
            "value": self._format_entity_state(state),
            "available": available,
        }

    def _compute_availability(self, payload: ProviderPayload) -> bool:
        pages = payload.get("pages", [])
        if not isinstance(pages, list):
            return False

        for page in pages:
            if not isinstance(page, dict):
                continue
            widgets = page.get("widgets", [])
            if not isinstance(widgets, list):
                continue
            if any(isinstance(widget, dict) and widget.get("available") for widget in widgets):
                return True
        return False

    def _invalidate_dashboard_cache(self) -> None:
        if self._last_dashboard_cache_key:
            self.cache.invalidate(self.build_cache_key(self._last_dashboard_cache_key))

    def _track_dashboard_cache_key(self, cache_key: str) -> None:
        if self._last_dashboard_cache_key and self._last_dashboard_cache_key != cache_key:
            self.cache.invalidate(self.build_cache_key(self._last_dashboard_cache_key))
        self._last_dashboard_cache_key = cache_key

    def _resolve_scene_entity(self, scene_id: str) -> str | None:
        snapshot = self.config_store.get_snapshot()
        scene = snapshot.config.get_scene(scene_id)
        return scene.entity if scene else None

    def _require_heater_widget(self, widget_id: str | None) -> HeaterWidgetConfig:
        snapshot = self.config_store.get_snapshot()
        heater_widget = snapshot.config.get_heater_widget(widget_id)
        if heater_widget is None:
            if widget_id:
                raise ConfigurationError(
                    f"Heater widget '{widget_id}' is not configured in dashboard.yaml."
                )
            raise ConfigurationError("No heater widget is configured in dashboard.yaml.")
        return heater_widget

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

    def _normalize_mode_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            if value is None:
                continue
            normalized.append(str(value))
        return normalized

    def _format_weather_temperature(self, state: dict[str, Any] | None) -> str:
        if not state or not self._state_is_available(state.get("state")):
            return "--"

        attributes = state.get("attributes", {})
        return self._format_value(attributes.get("temperature"), attributes.get("temperature_unit"))

    def _format_entity_state(self, state: dict[str, Any] | None) -> str:
        if not state or not self._state_is_available(state.get("state")):
            return "--"

        attributes = state.get("attributes", {})
        return self._format_value(state.get("state"), attributes.get("unit_of_measurement"))

    def _format_value(self, value: Any, unit: str | None = None) -> str:
        normalized_value = self._coerce_float(value)
        if normalized_value is not None:
            rendered_value = self._trim_zero(normalized_value)
        elif value is None:
            return "--"
        else:
            rendered_value = self._humanize(str(value))

        if not unit:
            return rendered_value
        if unit in NO_SPACE_UNITS:
            return f"{rendered_value}{unit}"
        return f"{rendered_value} {unit}"

    def _trim_zero(self, value: float) -> str:
        rounded = round(value, 1)
        if rounded.is_integer():
            return str(int(rounded))
        return str(rounded)

    def _state_is_available_from_state(self, state: dict[str, Any] | None) -> bool:
        return bool(state) and self._state_is_available(state.get("state"))

    def _scene_is_available(self, state: dict[str, Any] | None) -> bool:
        if not state:
            return False
        raw_state = state.get("state")
        if raw_state is None:
            return True
        return str(raw_state).strip().lower() != "unavailable"

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
        return value.replace(".", " ").replace("_", " ").strip().title()

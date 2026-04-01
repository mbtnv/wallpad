from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class Settings:
    ha_base_url: str
    ha_token: str
    ha_weather_entity: str
    ha_indoor_temp_entity: str
    ha_outdoor_temp_entity: str
    ha_heater_entity: str
    ha_scene_morning: str
    ha_scene_night: str
    ha_scene_away: str
    ha_timeout_seconds: float = 10.0
    ha_cache_ttl_seconds: int = 5
    dashboard_cache_ttl_seconds: int = 5

    @property
    def normalized_ha_base_url(self) -> str:
        return self.ha_base_url.rstrip("/")

    @property
    def home_assistant_enabled(self) -> bool:
        return bool(self.normalized_ha_base_url and self.ha_token)

    @property
    def scene_map(self) -> dict[str, str]:
        scene_pairs = {
            "morning": self.ha_scene_morning,
            "night": self.ha_scene_night,
            "away": self.ha_scene_away,
        }
        return {scene_id: entity_id for scene_id, entity_id in scene_pairs.items() if entity_id}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        ha_base_url=_env("HA_BASE_URL"),
        ha_token=_env("HA_TOKEN"),
        ha_weather_entity=_env("HA_WEATHER_ENTITY"),
        ha_indoor_temp_entity=_env("HA_INDOOR_TEMP_ENTITY"),
        ha_outdoor_temp_entity=_env("HA_OUTDOOR_TEMP_ENTITY"),
        ha_heater_entity=_env("HA_HEATER_ENTITY"),
        ha_scene_morning=_env("HA_SCENE_MORNING"),
        ha_scene_night=_env("HA_SCENE_NIGHT"),
        ha_scene_away=_env("HA_SCENE_AWAY"),
    )

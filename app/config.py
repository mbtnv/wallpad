from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class Settings:
    ha_base_url: str
    ha_token: str
    dashboard_config_path: str
    ha_timeout_seconds: float = 10.0
    ha_cache_ttl_seconds: int = 5
    dashboard_cache_ttl_seconds: int = 5

    @property
    def normalized_ha_base_url(self) -> str:
        return self.ha_base_url.rstrip("/")

    @property
    def home_assistant_enabled(self) -> bool:
        return bool(self.normalized_ha_base_url and self.ha_token)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        ha_base_url=_env("HA_BASE_URL"),
        ha_token=_env("HA_TOKEN"),
        dashboard_config_path=_env("DASHBOARD_CONFIG_PATH") or str(BASE_DIR / "dashboard.yaml"),
    )

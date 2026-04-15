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
    dashboard_config_seed_path: str
    config_editor_username: str
    config_editor_password: str
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
    def config_editor_auth_configured(self) -> bool:
        return bool(self.config_editor_username or self.config_editor_password)

    @property
    def config_editor_auth_enabled(self) -> bool:
        return bool(self.config_editor_username and self.config_editor_password)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        ha_base_url=_env("HA_BASE_URL"),
        ha_token=_env("HA_TOKEN"),
        dashboard_config_path=_env("DASHBOARD_CONFIG_PATH") or str(BASE_DIR / "dashboard.yaml"),
        dashboard_config_seed_path=_env("DASHBOARD_CONFIG_SEED_PATH")
        or str(BASE_DIR / "dashboard.yaml"),
        config_editor_username=_env("CONFIG_EDITOR_USERNAME"),
        config_editor_password=_env("CONFIG_EDITOR_PASSWORD"),
    )

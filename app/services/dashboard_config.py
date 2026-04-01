from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha1
from pathlib import Path
from threading import RLock

import yaml

from app.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.schemas.dashboard_config import DashboardConfig


@dataclass(frozen=True)
class DashboardConfigSnapshot:
    config: DashboardConfig
    version: str
    error: str | None = None


class DashboardConfigStore:
    def __init__(self, settings: Settings) -> None:
        self._path = Path(settings.dashboard_config_path).expanduser()
        self._lock = RLock()
        self._cached_snapshot: DashboardConfigSnapshot | None = None
        self._cached_signature: tuple[int, int] | None = None

    def get_snapshot(self) -> DashboardConfigSnapshot:
        try:
            stat_result = self._path.stat()
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Dashboard config file '{self._path}' was not found."
            ) from exc

        signature = (stat_result.st_mtime_ns, stat_result.st_size)

        with self._lock:
            if self._cached_snapshot is not None and signature == self._cached_signature:
                return self._cached_snapshot

            try:
                contents = self._path.read_text(encoding="utf-8")
                raw_data = yaml.safe_load(contents) or {}
                config = DashboardConfig.model_validate(raw_data)
            except Exception as exc:
                self._cached_signature = signature
                if self._cached_snapshot is not None:
                    return DashboardConfigSnapshot(
                        config=self._cached_snapshot.config,
                        version=self._cached_snapshot.version,
                        error=f"Failed to load dashboard.yaml: {exc}",
                    )
                raise ConfigurationError(f"Failed to load dashboard.yaml: {exc}") from exc

            snapshot = DashboardConfigSnapshot(
                config=config,
                version=sha1(contents.encode("utf-8")).hexdigest()[:12],
                error=None,
            )
            self._cached_snapshot = snapshot
            self._cached_signature = signature
            return snapshot


@lru_cache(maxsize=1)
def get_dashboard_config_store() -> DashboardConfigStore:
    return DashboardConfigStore(get_settings())

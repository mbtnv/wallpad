from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha1
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from threading import RLock

import yaml

from app.config import Settings, get_settings
from app.core.errors import ConfigurationError, ConflictError
from app.schemas.dashboard_config import DashboardConfig


@dataclass(frozen=True)
class DashboardConfigSnapshot:
    config: DashboardConfig
    version: str
    error: str | None = None


@dataclass(frozen=True)
class DashboardConfigDocument:
    content: str
    version: str
    is_valid: bool
    validation_error: str | None = None


class DashboardConfigStore:
    def __init__(self, settings: Settings) -> None:
        self._path = Path(settings.dashboard_config_path).expanduser()
        self._seed_path = Path(settings.dashboard_config_seed_path).expanduser()
        self._lock = RLock()
        self._cached_snapshot: DashboardConfigSnapshot | None = None
        self._cached_signature: tuple[int, int] | None = None

    def get_snapshot(self) -> DashboardConfigSnapshot:
        with self._lock:
            self._ensure_config_exists_unlocked()
            stat_result = self._path.stat()
            signature = (stat_result.st_mtime_ns, stat_result.st_size)

            if self._cached_snapshot is not None and signature == self._cached_signature:
                return self._cached_snapshot

            try:
                contents = self._path.read_text(encoding="utf-8")
                config = self._parse_config(contents)
            except Exception as exc:
                error_message = f"Failed to load dashboard config: {exc}"
                if self._cached_snapshot is not None:
                    fallback_snapshot = DashboardConfigSnapshot(
                        config=self._cached_snapshot.config,
                        version=self._cached_snapshot.version,
                        error=error_message,
                    )
                    self._cached_snapshot = fallback_snapshot
                    self._cached_signature = signature
                    return fallback_snapshot
                raise ConfigurationError(error_message) from exc

            snapshot = DashboardConfigSnapshot(
                config=config,
                version=self._build_version(contents),
                error=None,
            )
            self._cached_snapshot = snapshot
            self._cached_signature = signature
            return snapshot

    def get_document(self) -> DashboardConfigDocument:
        with self._lock:
            self._ensure_config_exists_unlocked()
            contents = self._path.read_text(encoding="utf-8")
            return self.inspect_document(contents)

    def inspect_document(self, contents: str) -> DashboardConfigDocument:
        validation_error: str | None = None
        try:
            self._parse_config(contents)
        except Exception as exc:
            validation_error = f"Failed to validate dashboard config: {exc}"

        return DashboardConfigDocument(
            content=contents,
            version=self._build_version(contents),
            is_valid=validation_error is None,
            validation_error=validation_error,
        )

    def save_document(
        self,
        contents: str,
        expected_version: str | None = None,
    ) -> DashboardConfigDocument:
        document = self.inspect_document(contents)
        if not document.is_valid:
            raise ConfigurationError(document.validation_error or "Dashboard config is invalid.")

        with self._lock:
            self._ensure_config_exists_unlocked()
            current_contents = self._path.read_text(encoding="utf-8")
            current_version = self._build_version(current_contents)

            if expected_version is not None and expected_version != current_version:
                raise ConflictError(
                    "The config file was changed in another session. Reload it before saving."
                )

            self._write_contents_unlocked(contents)
            self._cached_snapshot = None
            self._cached_signature = None

        return document

    def _ensure_config_exists_unlocked(self) -> None:
        if self._path.exists():
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)

        if self._seed_path.exists() and self._seed_path.resolve() != self._path.resolve():
            copyfile(self._seed_path, self._path)
            return

        raise ConfigurationError(f"Dashboard config file '{self._path}' was not found.")

    def _parse_config(self, contents: str) -> DashboardConfig:
        raw_data = yaml.safe_load(contents) or {}
        return DashboardConfig.model_validate(raw_data)

    def _write_contents_unlocked(self, contents: str) -> None:
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                delete=False,
            ) as temporary_file:
                temporary_file.write(contents)
                temporary_path = Path(temporary_file.name)

            if temporary_path is None:
                raise ConfigurationError("Failed to create a temporary config file.")

            temporary_path.replace(self._path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def _build_version(self, contents: str) -> str:
        return sha1(contents.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=1)
def get_dashboard_config_store() -> DashboardConfigStore:
    return DashboardConfigStore(get_settings())

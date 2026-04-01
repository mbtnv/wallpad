from __future__ import annotations

import asyncio
from datetime import datetime
from functools import lru_cache
from typing import TypeVar

from app.config import get_settings
from app.core.errors import ProviderNotRegisteredError
from app.core.provider_base import BaseProvider, ProviderExecutionResult, ProviderPayload
from app.providers.home_assistant import HomeAssistantProvider
from app.schemas.dashboard import ClockData, DashboardResponse, ProviderStatus
from app.services.cache import get_cache
from app.services.dashboard_config import get_dashboard_config_store
from app.services.home_assistant import get_home_assistant_service

TProvider = TypeVar("TProvider", bound=BaseProvider)

RESERVED_RESPONSE_KEYS = {"generated_at", "clock", "providers"}


class DashboardOrchestrator:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register_provider(self, provider: BaseProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered.")
        self._providers[provider.name] = provider

    def get_provider(self, name: str, provider_type: type[TProvider]) -> TProvider:
        provider = self._providers.get(name)
        if provider is None or not isinstance(provider, provider_type):
            raise ProviderNotRegisteredError(f"Provider '{name}' is not registered.")
        return provider

    async def build_dashboard(self) -> ProviderPayload:
        now = datetime.now().astimezone()
        dashboard = self._build_base_dashboard(now)
        providers = list(self._providers.values())

        results = await asyncio.gather(
            *(self._execute_provider(provider) for provider in providers),
            return_exceptions=True,
        )

        for provider, result in zip(providers, results):
            if isinstance(result, Exception):
                dashboard["providers"][provider.name] = ProviderStatus(available=False).model_dump()
                self._merge_provider_data(dashboard, provider.fallback_payload())
                continue

            dashboard["providers"][result.name] = ProviderStatus(
                available=result.available
            ).model_dump()
            self._merge_provider_data(dashboard, result.data)

        return dashboard

    async def toggle_heater(self, widget_id: str | None = None) -> ProviderPayload:
        provider = self.get_provider("home_assistant", HomeAssistantProvider)
        return await provider.toggle_heater(widget_id)

    async def set_heater_mode(self, mode: str, widget_id: str | None = None) -> ProviderPayload:
        provider = self.get_provider("home_assistant", HomeAssistantProvider)
        return await provider.set_heater_mode(mode, widget_id)

    async def trigger_scene(self, scene_id: str) -> ProviderPayload:
        provider = self.get_provider("home_assistant", HomeAssistantProvider)
        return await provider.trigger_scene(scene_id)

    async def aclose(self) -> None:
        await asyncio.gather(
            *(provider.aclose() for provider in self._providers.values()),
            return_exceptions=True,
        )

    async def _execute_provider(self, provider: BaseProvider) -> ProviderExecutionResult:
        try:
            data = await provider.fetch()
        except Exception:
            provider.set_available(False)
            data = provider.fallback_payload()

        available = False
        try:
            available = await provider.is_available()
        except Exception:
            available = False

        if not isinstance(data, dict):
            data = provider.fallback_payload()
            available = False

        return ProviderExecutionResult(
            name=provider.name,
            available=available,
            data=data,
        )

    def _build_base_dashboard(self, now: datetime) -> ProviderPayload:
        return DashboardResponse(
            generated_at=now.isoformat(),
            clock=self._build_clock(now),
            config_version=None,
            config_error=None,
            default_page=None,
            pages=[],
            providers={},
        ).model_dump()

    def _build_clock(self, now: datetime) -> ClockData:
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        return ClockData(
            iso=now.isoformat(),
            time=now.strftime("%H:%M"),
            date=f"{months[now.month - 1]} {now.day}, {now.year}",
            weekday=weekdays[now.weekday()],
        )

    def _merge_provider_data(
        self,
        dashboard: ProviderPayload,
        provider_data: ProviderPayload,
    ) -> None:
        for key, value in provider_data.items():
            if key in RESERVED_RESPONSE_KEYS:
                continue
            dashboard[key] = value


@lru_cache(maxsize=1)
def get_dashboard_orchestrator() -> DashboardOrchestrator:
    orchestrator = DashboardOrchestrator()
    cache = get_cache()
    settings = get_settings()
    home_assistant_service = get_home_assistant_service()
    config_store = get_dashboard_config_store()

    orchestrator.register_provider(
        HomeAssistantProvider(
            settings=settings,
            service=home_assistant_service,
            cache=cache,
            config_store=config_store,
        )
    )
    return orchestrator

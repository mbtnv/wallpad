from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClockData(BaseModel):
    iso: str
    time: str
    date: str
    weekday: str


class WidgetRowData(BaseModel):
    label: str
    value: str = "--"
    available: bool = False


class WidgetActionData(BaseModel):
    action: Literal["heater_toggle", "heater_mode", "scene"]
    label: str
    widget_id: str | None = None
    scene_id: str | None = None
    mode: str | None = None
    disabled: bool = False
    active: bool = False
    variant: Literal["default", "primary", "success"] = "default"


class DashboardWidgetData(BaseModel):
    id: str
    type: Literal["weather", "sensor", "heater", "scenes"]
    title: str
    wide: bool = False
    available: bool = False
    primary_text: str | None = None
    secondary_text: str | None = None
    rows: list[WidgetRowData] = Field(default_factory=list)
    actions: list[WidgetActionData] = Field(default_factory=list)


class DashboardPageData(BaseModel):
    id: str
    title: str
    widgets: list[DashboardWidgetData] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    available: bool = False


class DashboardResponse(BaseModel):
    generated_at: str
    clock: ClockData
    config_version: str | None = None
    config_error: str | None = None
    default_page: str | None = None
    pages: list[DashboardPageData] = Field(default_factory=list)
    providers: dict[str, ProviderStatus] = Field(default_factory=dict)

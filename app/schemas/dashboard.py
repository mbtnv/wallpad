from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClockData(BaseModel):
    iso: str
    time: str
    date: str
    weekday: str


class WeatherData(BaseModel):
    available: bool = False
    condition: str | None = None
    temperature: float | None = None
    temperature_unit: str | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    wind_speed_unit: str | None = None
    friendly_name: str | None = None


class HomeData(BaseModel):
    indoor_temperature: float | None = None
    indoor_temperature_unit: str | None = None
    outdoor_temperature: float | None = None
    outdoor_temperature_unit: str | None = None


class HeaterData(BaseModel):
    available: bool = False
    entity_id: str | None = None
    state: str | None = None
    is_on: bool = False
    mode: str | None = None
    supported_modes: list[str] = Field(default_factory=list)
    friendly_name: str | None = None


class SceneData(BaseModel):
    id: str
    name: str
    entity_id: str | None = None
    available: bool = False


class ProviderStatus(BaseModel):
    available: bool = False


class DashboardResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: str
    clock: ClockData
    weather: WeatherData = Field(default_factory=WeatherData)
    home: HomeData = Field(default_factory=HomeData)
    heater: HeaterData = Field(default_factory=HeaterData)
    scenes: list[SceneData] = Field(default_factory=list)
    providers: dict[str, ProviderStatus] = Field(default_factory=dict)

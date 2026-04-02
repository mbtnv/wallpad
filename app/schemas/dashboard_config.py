from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class SensorRowConfig(BaseModel):
    label: str
    entity: str


class SensorHistoryConfig(BaseModel):
    title: str | None = None
    hours: int = Field(default=24, ge=1, le=168)
    points: int = Field(default=48, ge=2, le=240)
    min: float | None = None
    max: float | None = None
    warning_min: float | None = None
    warning_max: float | None = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> SensorHistoryConfig:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Sensor history 'min' must be less than or equal to 'max'.")

        if self.warning_min is not None and self.warning_max is not None:
            if self.warning_min > self.warning_max:
                raise ValueError(
                    "Sensor history 'warning_min' must be less than or equal to 'warning_max'."
                )

        if self.min is not None and self.warning_min is not None and self.warning_min < self.min:
            raise ValueError("Sensor history 'warning_min' must be greater than or equal to 'min'.")

        if self.max is not None and self.warning_max is not None and self.warning_max > self.max:
            raise ValueError("Sensor history 'warning_max' must be less than or equal to 'max'.")

        return self


class WeatherRowConfig(BaseModel):
    label: str
    entity: str | None = None
    attribute: str | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> WeatherRowConfig:
        has_entity = bool(self.entity and self.entity.strip())
        has_attribute = bool(self.attribute and self.attribute.strip())

        if has_entity == has_attribute:
            raise ValueError("Weather rows must define exactly one of 'entity' or 'attribute'.")

        return self


class WeatherForecastConfig(BaseModel):
    type: Literal["hourly"] = "hourly"
    title: str | None = None
    hours: int = Field(default=6, ge=1, le=24)
    primary: str = "temperature"
    secondary: str | None = "condition"


class SceneConfig(BaseModel):
    id: str
    name: str
    entity: str


class WidgetBaseConfig(BaseModel):
    id: str
    type: str
    title: str
    wide: bool = False


class WeatherWidgetConfig(WidgetBaseConfig):
    type: Literal["weather"]
    weather_entity: str
    rows: list[WeatherRowConfig] = Field(default_factory=list)
    forecast: WeatherForecastConfig | None = None


class SensorWidgetConfig(WidgetBaseConfig):
    type: Literal["sensor"]
    entity: str
    subtitle: str | None = None
    history: SensorHistoryConfig | None = None
    rows: list[SensorRowConfig] = Field(default_factory=list)


class HeaterWidgetConfig(WidgetBaseConfig):
    type: Literal["heater"]
    entity: str


class ScenesWidgetConfig(WidgetBaseConfig):
    type: Literal["scenes"]
    scenes: list[SceneConfig] = Field(default_factory=list)


WidgetConfig = Annotated[
    WeatherWidgetConfig | SensorWidgetConfig | HeaterWidgetConfig | ScenesWidgetConfig,
    Field(discriminator="type"),
]


class DashboardPageConfig(BaseModel):
    id: str
    title: str
    widgets: list[WidgetConfig] = Field(default_factory=list)


class DashboardConfig(BaseModel):
    default_page: str | None = None
    swipe_enabled: bool = True
    pages: list[DashboardPageConfig]

    @model_validator(mode="after")
    def validate_structure(self) -> DashboardConfig:
        if not self.pages:
            raise ValueError("dashboard.yaml must define at least one page.")

        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Page ids in dashboard.yaml must be unique.")

        widget_ids: list[str] = []
        scene_ids: list[str] = []
        for page in self.pages:
            page_widget_ids = [widget.id for widget in page.widgets]
            if len(page_widget_ids) != len(set(page_widget_ids)):
                raise ValueError(f"Widget ids on page '{page.id}' must be unique.")

            widget_ids.extend(page_widget_ids)

            for widget in page.widgets:
                if isinstance(widget, ScenesWidgetConfig):
                    local_scene_ids = [scene.id for scene in widget.scenes]
                    if len(local_scene_ids) != len(set(local_scene_ids)):
                        raise ValueError(
                            f"Scene ids in widget '{widget.id}' on page '{page.id}' must be unique."
                        )
                    scene_ids.extend(local_scene_ids)

        if len(widget_ids) != len(set(widget_ids)):
            raise ValueError("Widget ids in dashboard.yaml must be unique across all pages.")

        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("Scene ids in dashboard.yaml must be unique across all pages.")

        if self.default_page and self.default_page not in page_ids:
            raise ValueError("default_page must reference an existing page id.")

        return self

    def iter_widgets(self) -> Iterator[WidgetConfig]:
        for page in self.pages:
            yield from page.widgets

    def resolved_default_page(self) -> str:
        return self.default_page or self.pages[0].id

    def get_heater_widget(self, widget_id: str | None = None) -> HeaterWidgetConfig | None:
        heater_widgets = [
            widget for widget in self.iter_widgets() if isinstance(widget, HeaterWidgetConfig)
        ]
        if widget_id:
            for widget in heater_widgets:
                if widget.id == widget_id:
                    return widget
            return None
        return heater_widgets[0] if heater_widgets else None

    def get_scene(self, scene_id: str) -> SceneConfig | None:
        for widget in self.iter_widgets():
            if not isinstance(widget, ScenesWidgetConfig):
                continue
            for scene in widget.scenes:
                if scene.id == scene_id:
                    return scene
        return None

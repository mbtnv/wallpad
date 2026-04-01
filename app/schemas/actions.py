from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HeaterModeRequest(BaseModel):
    mode: str = Field(min_length=1)


class ActionResponse(BaseModel):
    status: str = "ok"
    message: str
    result: dict[str, Any] | None = None

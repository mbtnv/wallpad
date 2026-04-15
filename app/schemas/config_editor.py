from __future__ import annotations

from pydantic import BaseModel


class DashboardConfigDocumentResponse(BaseModel):
    content: str
    version: str
    is_valid: bool
    validation_error: str | None = None


class DashboardConfigValidateRequest(BaseModel):
    content: str


class DashboardConfigUpdateRequest(BaseModel):
    content: str
    version: str | None = None


class DashboardConfigUpdateResponse(DashboardConfigDocumentResponse):
    message: str

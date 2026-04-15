from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import Settings, get_settings
from app.core.errors import ConfigurationError, ConflictError
from app.core.static_pages import render_static_html
from app.schemas.config_editor import (
    DashboardConfigDocumentResponse,
    DashboardConfigUpdateRequest,
    DashboardConfigUpdateResponse,
    DashboardConfigValidateRequest,
)
from app.services.dashboard_config import DashboardConfigDocument, get_dashboard_config_store

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(tags=["config"])
basic_auth = HTTPBasic(auto_error=False)


def _build_document_response(document: DashboardConfigDocument) -> DashboardConfigDocumentResponse:
    return DashboardConfigDocumentResponse(
        content=document.content,
        version=document.version,
        is_valid=document.is_valid,
        validation_error=document.validation_error,
    )


def require_config_editor_access(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if settings.config_editor_auth_configured and not settings.config_editor_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Config editor authentication is misconfigured. "
                "Set both CONFIG_EDITOR_USERNAME and CONFIG_EDITOR_PASSWORD."
            ),
        )

    if not settings.config_editor_auth_enabled:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required for the config editor.",
            headers={"WWW-Authenticate": "Basic"},
        )

    valid_username = secrets.compare_digest(
        credentials.username,
        settings.config_editor_username,
    )
    valid_password = secrets.compare_digest(
        credentials.password,
        settings.config_editor_password,
    )
    if valid_username and valid_password:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid config editor credentials.",
        headers={"WWW-Authenticate": "Basic"},
    )


@router.get(
    "/config",
    include_in_schema=False,
    dependencies=[Depends(require_config_editor_access)],
)
async def config_editor_page():
    return render_static_html(STATIC_DIR, "config.html")


@router.get(
    "/config.html",
    include_in_schema=False,
    dependencies=[Depends(require_config_editor_access)],
)
async def config_editor_page_file():
    return render_static_html(STATIC_DIR, "config.html")


@router.get(
    "/api/config",
    response_model=DashboardConfigDocumentResponse,
    dependencies=[Depends(require_config_editor_access)],
)
async def get_config_document() -> DashboardConfigDocumentResponse:
    document = get_dashboard_config_store().get_document()
    return _build_document_response(document)


@router.post(
    "/api/config/validate",
    response_model=DashboardConfigDocumentResponse,
    dependencies=[Depends(require_config_editor_access)],
)
async def validate_config_document(
    payload: DashboardConfigValidateRequest,
) -> DashboardConfigDocumentResponse:
    document = get_dashboard_config_store().inspect_document(payload.content)
    return _build_document_response(document)


@router.put(
    "/api/config",
    response_model=DashboardConfigUpdateResponse,
    dependencies=[Depends(require_config_editor_access)],
)
async def update_config_document(
    payload: DashboardConfigUpdateRequest,
) -> DashboardConfigUpdateResponse:
    try:
        document = get_dashboard_config_store().save_document(
            payload.content,
            expected_version=payload.version,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return DashboardConfigUpdateResponse(
        content=document.content,
        version=document.version,
        is_valid=document.is_valid,
        validation_error=document.validation_error,
        message="Config saved successfully.",
    )

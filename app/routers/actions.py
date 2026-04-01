from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.errors import (
    ActionError,
    ConfigurationError,
    ProviderNotRegisteredError,
    UpstreamError,
)
from app.core.orchestrator import DashboardOrchestrator, get_dashboard_orchestrator
from app.schemas.actions import ActionResponse, HeaterActionRequest, HeaterModeRequest

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.post("/heater/toggle", response_model=ActionResponse)
async def toggle_heater(
    request: HeaterActionRequest | None = None,
    orchestrator: DashboardOrchestrator = Depends(get_dashboard_orchestrator),
) -> ActionResponse:
    try:
        result = await orchestrator.toggle_heater(request.widget_id if request else None)
    except (ConfigurationError, ProviderNotRegisteredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ActionResponse(message="Heater state updated.", result=result)


@router.post("/heater/mode", response_model=ActionResponse)
async def set_heater_mode(
    request: HeaterModeRequest,
    orchestrator: DashboardOrchestrator = Depends(get_dashboard_orchestrator),
) -> ActionResponse:
    try:
        result = await orchestrator.set_heater_mode(request.mode, request.widget_id)
    except (ConfigurationError, ProviderNotRegisteredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ActionResponse(
        message=f"Heater mode changed to {request.mode}.",
        result=result,
    )


@router.post("/scene/{scene_id}", response_model=ActionResponse)
async def trigger_scene(
    scene_id: str,
    orchestrator: DashboardOrchestrator = Depends(get_dashboard_orchestrator),
) -> ActionResponse:
    try:
        result = await orchestrator.trigger_scene(scene_id)
    except (ConfigurationError, ProviderNotRegisteredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ActionResponse(
        message=f"Scene {scene_id} triggered.",
        result=result,
    )

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.orchestrator import DashboardOrchestrator, get_dashboard_orchestrator
from app.schemas.dashboard import DashboardResponse

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    orchestrator: DashboardOrchestrator = Depends(get_dashboard_orchestrator),
) -> DashboardResponse:
    dashboard_data = await orchestrator.build_dashboard()
    return DashboardResponse.model_validate(dashboard_data)

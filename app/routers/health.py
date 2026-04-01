from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "home_assistant_configured": settings.home_assistant_enabled,
    }

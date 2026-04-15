from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.orchestrator import get_dashboard_orchestrator
from app.routers.actions import router as actions_router
from app.routers.config_editor import router as config_editor_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import router as health_router

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    if get_dashboard_orchestrator.cache_info().currsize:
        await get_dashboard_orchestrator().aclose()


app = FastAPI(title="Wall Dashboard", version="0.1.0", lifespan=lifespan)
app.include_router(dashboard_router)
app.include_router(actions_router)
app.include_router(config_editor_router)
app.include_router(health_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/index.html", include_in_schema=False)
async def index_file() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

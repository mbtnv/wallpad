from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

STATIC_ASSETS = (
    "icon.svg",
    "apple-touch-icon.png",
    "styles.css",
    "app.js",
    "config-editor.js",
)


def _versioned_static_url(static_dir: Path, asset_name: str) -> str:
    asset_path = static_dir / asset_name
    version = asset_path.stat().st_mtime_ns if asset_path.exists() else 0
    return f"/static/{asset_name}?v={version}"


def render_static_html(static_dir: Path, filename: str) -> HTMLResponse:
    html = (static_dir / filename).read_text(encoding="utf-8")

    for asset_name in STATIC_ASSETS:
        html = html.replace(f"/static/{asset_name}", _versioned_static_url(static_dir, asset_name))

    return HTMLResponse(content=html, headers=NO_STORE_HEADERS)

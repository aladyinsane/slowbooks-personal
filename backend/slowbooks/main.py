"""FastAPI application entry point.

In development: run the API here and the Vite dev server separately —
    uvicorn slowbooks.main:app --reload      # API on :8000
    npm run dev                              # UI on :5173, proxying /api to :8000

In a packaged build there is only one server: this app also serves the built frontend
(see ``_frontend_dir``), so the whole product is one URL. That's what lets it ship as a
single double-click executable (ADR 0013).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from slowbooks.api.routes import router

app = FastAPI(
    title="SlowBooks",
    description="Simple accounting software that doesn't suck to use.",
    version="0.1.0",
)

# Only needed in development, where the Vite dev server is a different origin. In a
# packaged build the UI is served from this same origin, so CORS never comes into it.
# Localhost only -- there is no remote anything (ADR 0001).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The API is added before the static mount below, so /api always wins over the catch-all.
app.include_router(router, prefix="/api")


def _frontend_dir() -> Path | None:
    """Where the built frontend lives, or None if it hasn't been built.

    Two homes: inside a PyInstaller bundle it's unpacked next to the code under
    ``frontend``; from source it's ``frontend/dist``, three levels up from this file.
    Returning None (rather than failing) keeps `uvicorn slowbooks.main:app` working in
    development, where the UI is served by Vite and this app is API-only.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "frontend"
    else:
        candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return candidate if candidate.is_dir() else None


_frontend = _frontend_dir()
if _frontend is not None:
    # Catch-all, mounted last: serves index.html and the built assets. `html=True` hands
    # back index.html for "/", which is all the SPA needs.
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
else:

    @app.get("/")
    def root():
        # Development, API-only: point a curious browser at the docs rather than 404.
        return {"name": "SlowBooks", "version": "0.1.0", "docs": "/docs"}

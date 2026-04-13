"""Project Sentinel FastAPI backend.

Replaces the Django backend described in ADR 0001 § Implementation
implications. Responsibilities:

- Serve POST /api/session/new (create a new game session)
- Serve POST /api/stream (SSE streaming DM turns)
- Serve GET /healthz (liveness)

State reads go directly against data/state/*.json via
``backend/state/``. State writes go through the engine → fs-manager →
git-sync path (the engine package's dispatch module). There is no
ORM, no Django, no Postgres query — Postgres keeps running per
ADR 0001 Phase 1 but nothing in this backend touches it.

Run locally (from repo root) with:

    just dev-backend

or directly:

    uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .routes import health, session, stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load settings once at startup; fail fast if .env is missing.
    app.state.settings = Settings.load()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Project Sentinel Backend",
        description=(
            "FastAPI backend for Project Sentinel — serves the React "
            "frontend and orchestrates the engine → fs-manager → "
            "git-sync write path per ADR 0001."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS configured lazily at first request — we don't have
    # app.state.settings yet at create_app() time, but the middleware
    # is installed up-front with the default dev origins and permissive
    # mode. Production deployments should override via CORS_ALLOWED_ORIGINS.
    settings_for_cors = Settings.load()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"] if settings_for_cors.cors_allow_all_origins else list(settings_for_cors.cors_allowed_origins)
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(stream.router)

    return app


app = create_app()

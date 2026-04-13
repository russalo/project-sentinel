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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .routes import health, session, stream


def create_app() -> FastAPI:
    # Load settings exactly once per process. Stored on
    # ``app.state.settings`` for route handlers and reused here for
    # CORS middleware configuration. No lifespan context manager is
    # needed — nothing async has to happen at startup.
    settings = Settings.load()

    app = FastAPI(
        title="Project Sentinel Backend",
        description=(
            "FastAPI backend for Project Sentinel — serves the React "
            "frontend and orchestrates the engine → fs-manager → "
            "git-sync write path per ADR 0001."
        ),
        version="0.2.0",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"] if settings.cors_allow_all_origins else list(settings.cors_allowed_origins)
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

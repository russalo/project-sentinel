"""Project Sentinel FastAPI backend.

Implements ADR 0001: canonical state lives in ``data/state/*.json`` +
``data/lore/*.md`` under git. Responsibilities:

- Serve POST /api/session/new (create a new game session)
- Serve POST /api/stream (SSE streaming DM turns)
- Serve GET /healthz (liveness)

State reads go directly against ``data/state/*.json`` via
``backend/state/``. State writes go through the engine → fs-manager →
git-sync path (the engine package's dispatch module). No ORM, no
database queries.

Run locally (from repo root) with:

    just dev-backend

or directly:

    uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .admin_metrics import AdminMetrics
from .concurrency import StreamSlotLimiter
from .config import Settings
from .mcp_agreement import verify_world_mode_agreement
from .ratelimit import RateLimiter
from .routes import admin, health, session, stream, training, world

logger = logging.getLogger(__name__)


def _log_access_posture(settings: Settings) -> None:
    """One startup line stating whether the ADR 0003 controls are armed.

    A misconfigured prod (secret unset → open) is the main risk of the
    enforce-only-when-configured model, so make the posture loud at boot.
    """
    logger.info(
        "ADR 0003 access layer — world-token enforcement: %s; "
        "rate limits (per-IP session-create/hr=%d, per-world stream/min=%d, "
        "global LLM/day=%d; 0=disabled); "
        "max-concurrent /api/stream=%d (0=disabled, hard-reject 503 at cap)",
        "ON" if settings.session_token_secret else "OFF (no secret configured)",
        settings.rl_session_create_per_hour,
        settings.rl_stream_per_minute,
        settings.llm_daily_ceiling,
        settings.max_concurrent_streams,
    )


def create_app() -> FastAPI:
    # Load settings exactly once per process. Stored on
    # ``app.state.settings`` for route handlers and reused here for
    # CORS middleware configuration. No lifespan context manager is
    # needed — nothing async has to happen at startup.
    settings = Settings.load()

    # Cutover safety (ADR 0002 / A2): in per-world mode, refuse to start unless
    # both MCP servers also report per-world mode. No-op in shared mode (default),
    # so dev/test setups without the MCP servers running are unaffected.
    verify_world_mode_agreement(settings)

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
    # One process-wide in-memory rate limiter (ADR 0003 Slice B). Stored on
    # app.state so every request shares the same counters.
    app.state.rate_limiter = RateLimiter()
    # One process-wide stream-slot limiter (ADR 0003 access dim #3 —
    # max concurrent /api/stream requests). Same single-instance-per-process
    # pattern as the rate limiter; per-worker capacity if/when uvicorn ever
    # runs with --workers N (each worker keeps independent count — deliberate,
    # matches the per-process semaphore semantics). Disabled when
    # max_concurrent_streams == 0 (the default; arm at cutover).
    app.state.stream_limiter = StreamSlotLimiter(settings.max_concurrent_streams)
    # Operator metrics for the closed-alpha status dashboard (`/_status` + the
    # `/api/admin/status` JSON endpoint). Counters live in-process; reset on
    # restart — acceptable for closed-alpha scale, see backend/admin_metrics.py.
    # The endpoints themselves MUST stay tailnet/loopback-only — the Caddy
    # invariant excludes /api/admin/* and /_status from the public edge.
    app.state.admin_metrics = AdminMetrics()
    _log_access_posture(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"]
            if settings.cors_allow_all_origins
            else list(settings.cors_allowed_origins)
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(stream.router)
    app.include_router(training.router)
    app.include_router(world.router)
    app.include_router(admin.router)

    return app


app = create_app()

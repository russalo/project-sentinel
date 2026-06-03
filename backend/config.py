"""Backend configuration — loads from environment, validates at startup.

This module is the boundary between the OS environment and the rest of
the backend: every ``os.environ`` read that the app does happens here,
and everything downstream takes a ``Settings`` instance as an explicit
argument. The ``engine/`` package is forbidden from reading env vars by
its own boundary contract, so the backend builds an ``engine.Config``
from these settings and hands it in.

Reads ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, ``DM_MODEL``,
``DM_MAX_COMPLETION_TOKENS``, ``FS_MANAGER_URL``, ``GIT_SYNC_URL``,
``CORS_ALLOWED_ORIGINS``, ``SENTINEL_WORLDS_ROOT``, ``SENTINEL_DEBUG``, and the
ADR 0003 access-layer knobs (``SENTINEL_SESSION_TOKEN_SECRET``,
``SENTINEL_SESSION_TOKEN_TTL``, ``SENTINEL_RL_SESSION_CREATE_PER_HOUR``,
``SENTINEL_RL_STREAM_PER_MINUTE``, ``SENTINEL_LLM_DAILY_CEILING``) from
``infrastructure/.env`` via python-dotenv. Set ``SENTINEL_SKIP_ENV_CHECK=1`` to
bypass the .env requirement in CI.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ENV_PATH = REPO_ROOT / "infrastructure" / ".env"


def _load_env() -> None:
    """Load infrastructure/.env into os.environ if present.

    Raises on a missing .env file unless SENTINEL_SKIP_ENV_CHECK is set —
    same ergonomic as the old Django settings.py. CI environments that
    inject secrets directly should set SENTINEL_SKIP_ENV_CHECK=1.
    """
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
        return
    if os.environ.get("SENTINEL_SKIP_ENV_CHECK"):
        return
    raise RuntimeError(
        f"infrastructure/.env not found at {ENV_PATH}.\n"
        f"Run `just env` from the repo root to generate it, then retry.\n"
        f"(Set SENTINEL_SKIP_ENV_CHECK=1 to bypass — e.g. in CI.)"
    )


@dataclass(frozen=True)
class Settings:
    """Backend-wide settings loaded from environment variables.

    Construct via ``Settings.load()`` at application startup; pass it
    explicitly to anything that needs it (route handlers read it from
    ``request.app.state.settings``).
    """

    openai_api_key: str
    openai_base_url: str | None
    dm_model: str
    max_completion_tokens: int

    fs_manager_url: str
    git_sync_url: str

    data_dir: Path
    # Per-world isolation root (ADR 0002 Slice 3). When set, the backend reads
    # each world's tree at ``<worlds_root>/<world_id>/data`` (resolved via
    # ``backend.state.world_root.resolve_world_data_dir``) instead of the single
    # shared ``data_dir``. ``None`` (the default) keeps today's shared-tree
    # behavior — the cutover is an operational flip of ``SENTINEL_WORLDS_ROOT``,
    # the same env var the MCP servers already read.
    worlds_root: str | None

    cors_allowed_origins: tuple[str, ...]
    cors_allow_all_origins: bool
    debug: bool

    # ── ADR 0003 access layer (all opt-in; defaults = disabled) ──────────
    # Every knob below is dormant by default so local & tailnet play stays
    # anonymous and unthrottled — the public edge sets them. Defaults live on
    # the dataclass fields (not just in ``load``) so direct ``Settings(...)``
    # construction (tests) need not enumerate them.
    #
    # When ``session_token_secret`` is set, world creation mints a per-world
    # HMAC token and the world-scoped routes (/stream, /world GET+DELETE)
    # require ``X-Sentinel-World-Token``. Unset → no minting, no enforcement.
    session_token_secret: str | None = None
    session_token_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days
    # Rate limits — each disabled at <= 0. Per-IP on world creation, per-world
    # on turns, and a global daily LLM-call circuit breaker.
    rl_session_create_per_hour: int = 0
    rl_stream_per_minute: int = 0
    llm_daily_ceiling: int = 0

    @classmethod
    def load(cls) -> "Settings":
        _load_env()

        def _env(name: str, default: str | None = None) -> str | None:
            value = os.environ.get(name)
            return value if value else default

        def _int_env(name: str, default: str) -> int:
            """Parse an integer env var, failing with a clear message.

            A bare ``int(_env(...))`` raises a cryptic ``ValueError`` at import
            time on a typo'd value (e.g. ``SENTINEL_SESSION_TOKEN_TTL=7d``);
            name the offending var instead.
            """
            raw = _env(name, default)
            try:
                return int(raw)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc

        # Debug mode defaults to OFF for safety. Dev environments
        # that want permissive CORS + verbose errors should set
        # SENTINEL_DEBUG=true in their infrastructure/.env.
        #
        # ``_env(name, default)`` always returns a non-None string when
        # a default is supplied — ``return value if value else default``
        # falls through to the default on missing-or-empty env. The
        # ``# type: ignore[union-attr]`` on .lower() below is therefore
        # not needed, and none of the call sites in the cls(...) block
        # need an ``or <default>`` fallback either. Keeping the calls
        # terse and trusting the helper's contract.
        debug = _env("SENTINEL_DEBUG", "false").lower() == "true"

        return cls(
            openai_api_key=_env("OPENAI_API_KEY", ""),
            openai_base_url=_env("OPENAI_BASE_URL"),
            dm_model=_env("DM_MODEL", "gpt-4o-mini"),
            max_completion_tokens=_int_env("DM_MAX_COMPLETION_TOKENS", "2000"),
            fs_manager_url=_env("FS_MANAGER_URL", "http://127.0.0.1:8010"),
            git_sync_url=_env("GIT_SYNC_URL", "http://127.0.0.1:8012"),
            data_dir=DATA_DIR,
            worlds_root=_env("SENTINEL_WORLDS_ROOT"),
            cors_allowed_origins=tuple(
                _env(
                    "CORS_ALLOWED_ORIGINS",
                    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173",
                ).split(",")
            ),
            cors_allow_all_origins=debug,
            debug=debug,
            session_token_secret=_env("SENTINEL_SESSION_TOKEN_SECRET"),
            session_token_ttl_seconds=_int_env(
                "SENTINEL_SESSION_TOKEN_TTL", str(7 * 24 * 60 * 60)
            ),
            rl_session_create_per_hour=_int_env(
                "SENTINEL_RL_SESSION_CREATE_PER_HOUR", "0"
            ),
            rl_stream_per_minute=_int_env("SENTINEL_RL_STREAM_PER_MINUTE", "0"),
            llm_daily_ceiling=_int_env("SENTINEL_LLM_DAILY_CEILING", "0"),
        )

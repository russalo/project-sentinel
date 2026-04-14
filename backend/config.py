"""Backend configuration — loads from environment, validates at startup.

This module is the boundary between the OS environment and the rest of
the backend: every ``os.environ`` read that the app does happens here,
and everything downstream takes a ``Settings`` instance as an explicit
argument. The ``engine/`` package is forbidden from reading env vars by
its own boundary contract, so the backend builds an ``engine.Config``
from these settings and hands it in.

Reads ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, ``DM_MODEL``,
``DM_MAX_COMPLETION_TOKENS``, ``FS_MANAGER_URL``, ``GIT_SYNC_URL``,
``CORS_ALLOWED_ORIGINS``, and ``SENTINEL_DEBUG`` from
``infrastructure/.env`` via python-dotenv. Set ``SENTINEL_SKIP_ENV_CHECK=1``
to bypass the .env requirement in CI.
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

    cors_allowed_origins: tuple[str, ...]
    cors_allow_all_origins: bool
    debug: bool

    @classmethod
    def load(cls) -> "Settings":
        _load_env()

        def _env(name: str, default: str | None = None) -> str | None:
            value = os.environ.get(name)
            return value if value else default

        # Debug mode defaults to OFF for safety. Dev environments
        # that want permissive CORS + verbose errors should set
        # SENTINEL_DEBUG=true in their infrastructure/.env.
        debug = (_env("SENTINEL_DEBUG", "false") or "false").lower() == "true"

        return cls(
            openai_api_key=_env("OPENAI_API_KEY", "") or "",
            openai_base_url=_env("OPENAI_BASE_URL"),
            dm_model=_env("DM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            max_completion_tokens=int(_env("DM_MAX_COMPLETION_TOKENS", "2000") or "2000"),
            fs_manager_url=_env("FS_MANAGER_URL", "http://127.0.0.1:8010") or "http://127.0.0.1:8010",
            git_sync_url=_env("GIT_SYNC_URL", "http://127.0.0.1:8012") or "http://127.0.0.1:8012",
            data_dir=DATA_DIR,
            cors_allowed_origins=tuple(
                (
                    _env(
                        "CORS_ALLOWED_ORIGINS",
                        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173",
                    )
                    or ""
                ).split(",")
            ),
            cors_allow_all_origins=debug,
            debug=debug,
        )

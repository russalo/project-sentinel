"""Adapter layer between backend settings and the engine package.

The engine/ package is deliberately framework-agnostic and forbids
Django/backend imports (enforced by tests/engine/test_boundaries.py).
This module is the one place the backend imports engine and converts
its own Settings into an engine.Config.

Callers use the helpers here rather than importing from ``engine``
directly so (a) there's one place the Config-construction logic lives,
and (b) the shape of the backend → engine boundary stays explicit and
auditable.
"""

import engine

from .config import Settings


def build_engine_config(settings: Settings) -> engine.Config:
    """Construct an engine.Config from the backend's Settings."""
    return engine.Config(
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        dm_model=settings.dm_model,
        max_completion_tokens=settings.max_completion_tokens,
        fs_manager_url=settings.fs_manager_url,
        git_sync_url=settings.git_sync_url,
    )

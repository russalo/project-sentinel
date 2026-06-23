"""Process-lifetime module registry (ADR-0005 / RFC-0005).

A tiny cache so a module's manifest + prompt fragment are read from disk
once per process, not on every prompt assembly. ``uvicorn --reload``
re-imports the code (clearing the cache); a fresh process repopulates it
on first use. Tests call ``registry.clear()`` to force a re-read.

Kept deliberately minimal — no thread-locking. The cache is populated
with idempotent reads (same name → same LoadedModule), so a concurrent
double-populate is harmless (both produce equal values; last write
wins with identical content).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .loader import LoadedModule


class _Registry:
    def __init__(self) -> None:
        self._cache: dict[str, LoadedModule] = {}

    def get(self, name: str) -> LoadedModule | None:
        return self._cache.get(name)

    def put(self, name: str, module: LoadedModule) -> None:
        self._cache[name] = module

    def clear(self) -> None:
        """Drop all cached modules. Used by tests that need a cold read."""
        self._cache.clear()


# Module-level singleton — one cache per process.
registry = _Registry()

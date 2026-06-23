"""Subsystem modules (ADR-0005).

Sentinel's roleplay engine is a registry of swappable per-subsystem
modules. Core ships one module per subsystem; community packs can ship
replacements sharing the same interface. This package is the
foundational wiring (RFC-0005): manifest model, loader, registry, and
the DM-prompt assembly that composes a world's active modules into one
system prompt.

RFC-0005 ships a single module — ``core/base-v1`` — that carries the
invariant DM personality + STATE DISCIPLINE rules (the content
previously hard-coded as ``engine.prompts.dm.DM_SYSTEM_PROMPT``). It
adds no roleplay mechanics; mechanic modules land in RFC-0006+.

Public surface:

- ``build_dm_prompt(modules)`` — assemble the DM system prompt for a
  world's active module set (defaults to the core set).
- ``DEFAULT_MODULES`` — the core default module set.
- ``CANONICAL_SUBSYSTEM_ORDER`` — deterministic assembly order.
- ``discover_modules`` / ``load_module`` — loader entry points.
- ``ModuleManifest`` — the manifest dataclass.
"""

from .assembly import CANONICAL_SUBSYSTEM_ORDER, DEFAULT_MODULES, build_dm_prompt
from .loader import discover_modules, load_module
from .manifest import ModuleManifest

__all__ = [
    "build_dm_prompt",
    "DEFAULT_MODULES",
    "CANONICAL_SUBSYSTEM_ORDER",
    "discover_modules",
    "load_module",
    "ModuleManifest",
]

"""Resolve a world's class-module rules-data → a PC's mechanical class rules
(RFC-0018, ADR-0004 Slice 1b; the ADR-0005 "module provides rules-data" pattern).

The class module (``core/four-class-fantasy-v1``) ships a machine-readable
``rules.json`` mapping each archetype to its ``{hp_factor, magic}``. This module
is the IO boundary: it resolves a world's bound class module, loads its
rules-data, and looks up the PC's (free-text) ``class`` string — so
``engine/progression.py`` stays a pure computation over a resolved rules dict.

**Fail-safe (never raise, never guess).** Any miss — no class module bound, the
module ships no rules-data, or the PC's ``class`` isn't one of the archetype keys
(``Sal``=``Proctor``, ``Chez``=``chaingang boss`` don't map) — returns None. The
caller (``enforce_progression``) then leaves ``hp.max``/``magic_pool.max``
DM-authored, exactly as before RFC-0018. Deriving a max is opt-in on a *known*
class, not a default guess. (A DM-driven free-text → archetype mapping that
closes this gap is ADR-0004 Slice 1c — see ``docs/BACKLOG.md``.)
"""

from __future__ import annotations

from typing import Any

from .modules.assembly import resolve_active_module
from .modules.loader import load_module
from .modules.manifest import ManifestError


def resolve_class_rules(
    modules: dict[str, str] | None, pc_class: Any
) -> dict[str, Any] | None:
    """The ``{hp_factor, magic}`` rules for ``pc_class`` under a world's class
    module, or None on any miss (fail-safe; see module docstring).

    ``pc_class`` is looked up case-insensitively against the rules-data keys
    (which are lowercase archetype slugs). Non-string / empty class → None.
    """
    if not isinstance(pc_class, str) or not pc_class.strip():
        return None
    class_module = resolve_active_module(modules, "class")
    if not class_module:
        return None
    try:
        loaded = load_module(class_module)
    except ManifestError:
        # Unknown/malformed class module — fail safe rather than break a turn.
        return None
    rules = loaded.rules_data
    if not isinstance(rules, dict):
        return None
    key = pc_class.strip().lower()
    for name, entry in rules.items():
        if isinstance(name, str) and name.lower() == key and isinstance(entry, dict):
            return entry
    return None

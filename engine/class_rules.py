"""Resolve a world's class-module rules-data → a PC's mechanical class rules
(RFC-0018 + RFC-0019; ADR-0004 Slices 1b/1c; the ADR-0005 "module provides
rules-data" pattern).

The class module (``core/four-class-fantasy-v1``) ships a machine-readable
``rules.json`` mapping each archetype to its ``{hp_factor, magic}``. This module
is the IO boundary: it resolves a world's bound class module, loads its
rules-data, and looks the PC up in it — so ``engine/progression.py`` stays a pure
computation over a resolved rules dict.

**Two ways a PC maps to an archetype** (RFC-0019):
1. the engine-pinned top-level ``archetype`` slug the DM assigns at establishment
   (``Sal`` = class "Proctor", archetype "cleric"), which wins; else
2. the free-text ``class`` itself, when it happens to name an archetype
   ("Warrior") — the RFC-0018 behavior, kept so nothing regresses.

**Fail-safe (never raise, never guess).** Any miss — no class module bound, the
module ships no rules-data, or neither the archetype nor the class matches a key
— returns None. The caller (``enforce_progression``) then leaves
``hp.max``/``magic_pool.max`` DM-authored. Deriving a max is opt-in on a *known*
class, never a default guess.
"""

from __future__ import annotations

from typing import Any

from .modules.assembly import resolve_active_module
from .modules.loader import load_module
from .modules.manifest import ManifestError


def _rules_data(modules: dict[str, str] | None) -> dict[str, Any] | None:
    """The bound class module's rules-data, or None (fail-safe, never raises)."""
    class_module = resolve_active_module(modules, "class")
    if not class_module:
        return None
    try:
        loaded = load_module(class_module)
    except ManifestError:
        # Unknown/malformed class module — fail safe rather than break a turn.
        return None
    rules = loaded.rules_data
    return rules if isinstance(rules, dict) else None


def _lookup(rules: dict[str, Any], value: Any) -> dict[str, Any] | None:
    """Case-insensitive lookup of ``value`` in the rules-data keys."""
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    for name, entry in rules.items():
        if isinstance(name, str) and name.lower() == key and isinstance(entry, dict):
            return entry
    return None


def archetypes(modules: dict[str, str] | None) -> tuple[str, ...]:
    """The bound class module's archetype slugs, or () when there are none.

    The valid set RFC-0019's write-once ``archetype`` pin checks a DM-emitted value
    against (``engine.progression`` stays pure by taking this tuple rather than
    doing the module IO itself). Empty → the pin is inert, so a world with no
    class rules-data behaves exactly as it did pre-RFC-0019.
    """
    rules = _rules_data(modules)
    if not rules:
        return ()
    return tuple(name for name in rules if isinstance(name, str))


def canonical_archetype(modules: dict[str, str] | None, value: Any) -> str | None:
    """The canonical (rules-data-cased) archetype slug for ``value``, or None if it
    isn't one of the bound class module's archetypes.

    The establishment gate for RFC-0019's write-once ``archetype``: a DM-emitted
    value that isn't a real archetype (e.g. "paladin") is rejected rather than
    stored, so the PC stays unclassified and the next turn can retry — never
    persist a slug no rules-data can resolve.
    """
    rules = _rules_data(modules)
    if rules is None or not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    for name in rules:
        if isinstance(name, str) and name.lower() == key:
            return name
    return None


def resolve_class_rules(
    modules: dict[str, str] | None, character: Any
) -> dict[str, Any] | None:
    """The ``{hp_factor, magic}`` rules for a PC, or None on any miss (fail-safe).

    ``character`` is the stored PC dict; its pinned ``archetype`` is preferred and
    its free-text ``class`` is the fallback (see module docstring). A bare string
    is also accepted and treated as the class, so pre-RFC-0019 callers/tests keep
    working.
    """
    rules = _rules_data(modules)
    if rules is None:
        return None
    if isinstance(character, str):
        return _lookup(rules, character)
    if not isinstance(character, dict):
        return None
    return _lookup(rules, character.get("archetype")) or _lookup(
        rules, character.get("class")
    )

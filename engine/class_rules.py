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
    # Only keys whose entry is a rules DICT — a stray scalar (e.g. a "schema": "1"
    # metadata key) must not be pinnable as an archetype `resolve_class_rules`
    # could never resolve (coderabbit).
    return tuple(
        name
        for name, entry in rules.items()
        if isinstance(name, str) and isinstance(entry, dict)
    )


def canonical_archetype(modules: dict[str, str] | None, value: Any) -> str | None:
    """The canonical (rules-data-cased) archetype slug for ``value``, or None if it
    isn't one of the bound class module's archetypes.

    The establishment gate for RFC-0019's write-once ``archetype``: a DM-emitted
    value that isn't a real archetype (e.g. "paladin") is rejected rather than
    stored, so the PC stays unclassified and the next turn can retry — never
    persist a slug no rules-data can resolve.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    for name in archetypes(modules):  # dict-valued keys only
        if name.lower() == key:
            return name
    return None


def sanitize_payload_archetypes(
    payload: Any, modules: dict[str, str] | None = None
) -> int:
    """Canonicalize-or-drop every ``archetype`` in an apply_world_update payload's
    entity ops, in place. Returns how many were dropped.

    The establishment gate for dispatch paths that do NOT run
    ``enforce_progression`` — notably the intro at ``/api/session/new``, which sends
    the extracted payload straight to ``apply_world_update``. Without this an
    LLM-emitted ``"archetype": "paladin"`` persists at world creation, and because
    later turns see an archetype as *present* the PC can stay mechanically
    unresolved (codex). Tolerant of any malformed payload shape.
    """
    dropped = 0
    if not isinstance(payload, dict):
        return 0
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return 0
    # First valid archetype seen per entity file. The intro can emit the same
    # character more than once (duplicate entries, or a second <world_update>
    # block — the Fact-Extractor keeps them all and fs-manager applies them in
    # order), so canonicalizing each op independently would let the LAST valid
    # value win and bypass write-once during establishment itself (codex). The
    # first valid one is pinned onto every later op for that entity — the same
    # rule enforce_progression applies on a normal turn.
    pinned: dict[str, str] = {}
    for op in updates:
        if not isinstance(op, dict):
            continue
        target = str(op.get("target_file"))
        if "/entities/" not in target:
            continue
        data = op.get("data")
        if not isinstance(data, dict) or "archetype" not in data:
            continue
        canonical = pinned.get(target) or canonical_archetype(
            modules, data.get("archetype")
        )
        if canonical is None:
            data.pop("archetype")
            dropped += 1
        else:
            data["archetype"] = canonical
            pinned.setdefault(target, canonical)
    return dropped


def sanitize_hint_archetypes(hint: Any, modules: dict[str, str] | None = None) -> int:
    """Canonicalize-or-drop every character ``archetype`` in a DM **hint** block, in
    place. Returns how many were dropped.

    The display-side twin of ``sanitize_payload_archetypes``. The intro's
    ``world_updates`` hint goes straight into the frontend's ``worldStore``, which
    copies character fields verbatim — so without this an invalid archetype lives on
    in the UI even though the persisted payload was sanitized (coderabbit).
    """
    dropped = 0
    if not isinstance(hint, dict):
        return 0
    chars = hint.get("characters")
    if not isinstance(chars, list):
        return 0
    pinned: dict[str, str] = {}
    for char in chars:
        if not isinstance(char, dict) or "archetype" not in char:
            continue
        key = str(char.get("name", "")).strip().lower()
        canonical = pinned.get(key) or canonical_archetype(
            modules, char.get("archetype")
        )
        if canonical is None:
            char.pop("archetype")
            dropped += 1
        else:
            char["archetype"] = canonical
            pinned.setdefault(key, canonical)
    return dropped


def seed_payload_vitality(payload: Any, modules: dict[str, str] | None = None) -> int:
    """Seed engine-derived ``hp``/``magic_pool`` onto entity ops that carry an
    archetype + stats. Returns how many pools were written.

    For the **establishment** dispatch only (``/api/session/new``), which never runs
    ``enforce_progression``. Without it an intro that validly classifies a PC still
    persists the DM's invented maxes — a cleric written as 20/20 is later reconciled
    to 20/36 and never reaches full health, because reconciliation corrects the max
    but leaves the (narrative-owned) current (codex). A newly established character
    starts at full: ``current = max``.
    """
    from .progression import authoritative_maxes  # local: avoid an import cycle

    seeded = 0
    if not isinstance(payload, dict):
        return 0
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return 0
    for op in updates:
        if not isinstance(op, dict) or "/entities/" not in str(op.get("target_file")):
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            continue
        rules = _lookup(_rules_data(modules) or {}, data.get("archetype"))
        if not rules:
            continue
        sheet = data.get("module_data", {})
        sheet = sheet.get("character_sheet") if isinstance(sheet, dict) else None
        stats = sheet.get("stats") if isinstance(sheet, dict) else None
        if not isinstance(stats, dict):
            continue
        hp_max, mp_max = authoritative_maxes(stats, rules)
        if hp_max is not None:
            sheet["hp"] = {"current": hp_max, "max": hp_max}
            seeded += 1
        if mp_max is not None:
            sheet["magic_pool"] = {"current": mp_max, "max": mp_max}
            seeded += 1
        elif "magic_pool" in sheet:
            sheet.pop("magic_pool")  # a resolved non-caster owns no pool
    return seeded


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

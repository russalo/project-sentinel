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

from .agents.fact_extractor import _slugify as _slugify_entity
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


def seed_payload_vitality(
    payload: Any, player_name: str, modules: dict[str, str] | None = None
) -> int:
    """Seed engine-derived ``hp``/``magic_pool`` onto entity ops that carry an
    archetype + stats. Returns how many pools were written.

    For the **establishment** dispatch only (``/api/session/new``), which never runs
    ``enforce_progression``. Without it an intro that validly classifies a PC still
    persists the DM's invented maxes — a cleric written as 20/20 is later reconciled
    to 20/36 and never reaches full health, because reconciliation corrects the max
    but leaves the (narrative-owned) current (codex). A newly established character
    starts at full: ``current = max``.
    """
    seeded = 0
    if not isinstance(payload, dict):
        return 0
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return 0
    rules_data = _rules_data(modules) or {}

    player_slug = _slugify_entity((player_name or "").strip())
    if not player_slug:
        return 0

    def _entity_ops():
        """ONLY the player character's ops. RFC-0019's authority — like all of
        progression enforcement — is PC-scoped: seeding an NPC would overwrite its
        narrative vitality (an injured NPC introduced at 1/10 silently healed to a
        derived 40/40) and strip a non-caster NPC's pool (codex)."""
        for op in updates:
            if not isinstance(op, dict):
                continue
            target = str(op.get("target_file"))
            if "/entities/" not in target:
                continue
            data = op.get("data")
            if not isinstance(data, dict):
                continue
            name = str(data.get("name", "")).strip()
            if not target.endswith(f"/entities/{player_slug}.json") and (
                not name or _slugify_entity(name) != player_slug
            ):
                continue
            yield target, data

    # The archetype each entity is being established with, so DUPLICATE ops for the
    # same entity are all seeded — not just the one that happens to carry the field.
    # fs-manager applies ops in order with a shallow `existing.update(data)`, so a
    # later fragment carrying DM-authored module_data would otherwise overwrite the
    # seeded pools (reverting a cleric from 36/36 to 20/20; codex).
    # …and the SHEET it was established with, so a later fragment that carries only
    # DM-authored HP inherits the stats instead of erasing them under the shallow
    # update (codex).
    by_target: dict[str, dict[str, Any]] = {}
    for target, data in _entity_ops():
        entry = by_target.setdefault(target, {})
        if "rules" not in entry:
            rules = _lookup(rules_data, data.get("archetype"))
            if rules:
                entry["rules"] = rules
        if "sheet" not in entry:
            sheet = data.get("module_data", {})
            sheet = sheet.get("character_sheet") if isinstance(sheet, dict) else None
            if isinstance(sheet, dict) and isinstance(sheet.get("stats"), dict):
                entry["sheet"] = sheet

    for target, data in _entity_ops():
        entry = by_target.get(target) or {}
        rules = entry.get("rules")
        if not rules:
            continue
        module_data = data.get("module_data")
        if not isinstance(module_data, dict):
            # No module_data at all: fs-manager's shallow update leaves the stored
            # one alone, so there is nothing to protect here.
            continue
        sheet = module_data.get("character_sheet")
        if not isinstance(sheet, dict):
            # module_data WITHOUT a character_sheet still replaces the stored
            # module_data wholesale — a `combat`-only fragment would erase the
            # seeded stats/hp/pool. Materialize the sheet so the carry lands (codex).
            sheet = {}
            module_data["character_sheet"] = sheet
        seeded += _seed_sheet(sheet, rules, entry.get("sheet"))
    return seeded


def _seed_sheet(
    sheet: Any, rules: dict[str, Any], carried_sheet: dict[str, Any] | None = None
) -> int:
    """Write full engine-derived pools onto one ``character_sheet``. Returns how
    many pools were written. Shared by the payload (persisted) and hint (displayed)
    seeders so the two can't disagree.

    ``carried_sheet`` is the sheet this entity was established with. A later
    duplicate fragment may carry only DM-authored HP, and fs-manager applies ops
    with a shallow ``existing.update(data)`` — so that fragment's ``module_data``
    becomes authoritative and would ERASE the stats. Any key the fragment omits is
    therefore copied in from the carried sheet, not merely borrowed for the
    calculation (codex).
    """
    from .progression import STAT_CAP, authoritative_maxes  # local: import cycle

    if not isinstance(sheet, dict):
        return 0
    if isinstance(carried_sheet, dict):
        carried_stats = carried_sheet.get("stats")
        for key, value in carried_sheet.items():
            if key not in sheet:
                sheet[key] = value
        # `setdefault` alone isn't enough for `stats`: a fragment carrying an
        # explicit but PARTIAL or malformed stats dict (e.g. `{"stats": {}}`) keeps
        # the key, bypasses the carry, and then erases the real stats under the
        # shallow update — leaving the PC unseeded (codex). Fill in per stat, and
        # replace a non-dict outright.
        if isinstance(carried_stats, dict):
            if isinstance(sheet.get("stats"), dict):
                for stat, value in carried_stats.items():
                    sheet["stats"].setdefault(stat, value)
            else:
                sheet["stats"] = carried_stats
    stats = sheet.get("stats")
    if not isinstance(stats, dict):
        return 0

    def _governing(stat: str) -> bool:
        """A usable governing stat: a positive integer within the module's cap.
        Malformed LLM output reaches here (the Fact-Extractor doesn't validate the
        sheet shape, and the intro runs no enforcement), so a missing/non-numeric
        value would coerce to 0 — a 0/0 character — and an out-of-range one like
        ``body: 100`` would mint 800 HP. Either way, leave the DM's pool alone
        (codex)."""
        value = stats.get(stat)
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= STAT_CAP
        )

    seeded = 0
    hp_max, mp_max = authoritative_maxes(stats, rules)
    if hp_max is not None and _governing("body"):
        sheet["hp"] = {"current": hp_max, "max": hp_max}
        seeded += 1
    if mp_max is not None:
        if _governing("will"):
            sheet["magic_pool"] = {"current": mp_max, "max": mp_max}
            seeded += 1
    elif "magic_pool" in sheet:
        sheet.pop("magic_pool")  # a resolved non-caster owns no pool
    return seeded


def seed_hint_vitality(
    hint: Any, player_name: str, modules: dict[str, str] | None = None
) -> int:
    """The display-side twin of ``seed_payload_vitality``: seed the same derived
    pools onto a DM **hint** block's characters, in place. Returns pools written.

    ``WorldCreation.jsx`` applies the intro hint straight into ``worldStore`` and
    ``useWorldHydration`` deliberately skips re-fetching after creation, so without
    this the UI shows the DM's invented vitality (a cleric's 20/20) while the
    persisted entity holds the engine's 36/36 — until a reload (coderabbit + codex,
    convergent). Uses the same rules and guards as the payload seeder.
    """
    seeded = 0
    if not isinstance(hint, dict):
        return 0
    chars = hint.get("characters")
    if not isinstance(chars, list):
        return 0
    rules_data = _rules_data(modules) or {}
    player_slug = _slugify_entity((player_name or "").strip())
    if not player_slug:
        return 0

    def _is_pc(char: Any) -> bool:
        """PC-scoped, exactly like the payload seeder — an NPC's narrative vitality
        is the DM's (codex)."""
        name = str(char.get("name", "")).strip() if isinstance(char, dict) else ""
        return bool(name) and _slugify_entity(name) == player_slug

    def _sheet_of(char: Any) -> Any:
        sheet = char.get("module_data", {}) if isinstance(char, dict) else None
        return sheet.get("character_sheet") if isinstance(sheet, dict) else None

    # Same per-character carry as the payload seeder: a duplicate fragment may
    # repeat neither the archetype nor the stats.
    by_name: dict[str, dict[str, Any]] = {}
    for char in chars:
        if not _is_pc(char):
            continue
        entry = by_name.setdefault(str(char.get("name", "")).strip().lower(), {})
        if "rules" not in entry:
            rules = _lookup(rules_data, char.get("archetype"))
            if rules:
                entry["rules"] = rules
        if "sheet" not in entry:
            sheet = _sheet_of(char)
            if isinstance(sheet, dict) and isinstance(sheet.get("stats"), dict):
                entry["sheet"] = sheet

    for char in chars:
        if not _is_pc(char):
            continue
        entry = by_name.get(str(char.get("name", "")).strip().lower()) or {}
        rules = entry.get("rules")
        if not rules:
            continue
        module_data = char.get("module_data")
        if not isinstance(module_data, dict):
            continue
        sheet = module_data.get("character_sheet")
        if not isinstance(sheet, dict):
            sheet = {}
            module_data["character_sheet"] = sheet
        seeded += _seed_sheet(sheet, rules, entry.get("sheet"))
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

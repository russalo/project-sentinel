"""Deterministic PC establishment at session creation (ADR-0004).

Until now the player character's entity file only came into existence when the
DM's intro ``<world_update>`` happened to emit it — and the DM may never do so
(a live world ran five turns with no PC file at all). Every ADR-0004 guarantee
(death-stakes RFC-0014, progression RFC-0017, derived maxes RFC-0018, archetype
mapping RFC-0019, and the #192 identity anchoring) attaches to that entity, so
its existence cannot be left to LLM whim.

This module builds the schema-valid ``apply_world_update`` payload that
provisions the PC **deterministically** from the creation request, for the
backend to dispatch through the normal engine → fs-manager path *before* the
intro's own payload. Pure: no IO, no dispatch — the engine boundary holds.

Design notes
------------
**``operation: "create"`` is the idempotency mechanism.** fs-manager 409s a
``create`` whose target exists, so the write boundary itself — not a backend
filesystem probe — decides whether the PC is already established. In per-world
mode a fresh world can never collide; in the shared tree a slug surviving from
a prior session is *protected* by the 409 (a leveled character is never
re-minted back to level 1).

**No stats, no pools.** There is no deterministic stat source: the four-stat
module grounds stats in the fiction ("not flat defaults"), and the RFC-0018
maxes derive *from* stats. The skeleton establishes identity + mechanics
anchors (``role``, ``level``, ``archetype`` when derivable); vitality becomes
engine-derived the moment the DM supplies stats (``seed_payload_vitality`` at
the intro, ``enforce_progression`` afterwards).

**Archetype only when the class already names one.** ``canonical_archetype``
maps the free-text class ("Warrior" → ``warrior``); anything else is left for
RFC-0019's DM mapping on a later turn. Deriving is opt-in on a known class,
never a guess — the same fail-safe as everywhere else in class_rules.

**Unsluggable names return no payload.** A name with no ASCII slug characters
has no entity file the Fact-Extractor could ever target either; the caller
must fail loud (log) rather than silently skip. NOT solved here — the product
call on non-ASCII names is pending.
"""

from __future__ import annotations

from typing import Any

from .agents.fact_extractor import _slugify as _slugify_entity
from .class_rules import canonical_archetype
from .textsafe import scrub_control_bytes

# Establishment values the engine owns at creation time.
STARTING_LEVEL = 1

# Matches the schema's log_entry bounds (minLength 10 / maxLength 4000).
_LOG_ENTRY_MAX = 4000


def pc_entity_target(player_name: str) -> str | None:
    """The PC's entity file path under the world's data root, or None when the
    name has no usable slug. The same ``_slugify`` contract the Fact-Extractor
    uses to build an op's target — so the provisioned file IS the file every
    later DM fragment for this character merges into."""
    slug = _slugify_entity(str(player_name or "").strip())
    return f"data/state/core/entities/{slug}.json" if slug else None


def pc_provision_payload(
    session_id: str,
    player_name: str,
    player_class: str,
    modules: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """The ``apply_world_update`` payload establishing the PC, or None.

    Returns ``(payload, canonical_archetype)``. ``payload`` is None when the
    name has no usable slug — the caller must log loudly and continue (the
    session still has value; enforcement simply has nothing to anchor on until
    the DM emits the entity, which is exactly today's behavior).
    ``canonical_archetype`` is the pinned archetype when the free-text class
    names one, else None; the caller feeds it to the establishment pins so the
    intro's own payload can't overwrite it.
    """
    name = str(player_name or "").strip()
    target = pc_entity_target(name)
    if target is None:
        return None, None

    archetype = canonical_archetype(modules, player_class)
    data: dict[str, Any] = {
        "name": name,
        "class": str(player_class or "").strip(),
        "role": "player",
        "level": STARTING_LEVEL,
    }
    if archetype is not None:
        data["archetype"] = archetype

    # Scrub + clamp: the name is user text (the schema rejects control bytes,
    # and player_character_name has no max length).
    log_entry = scrub_control_bytes(
        f"[Session Start] Player character {name} established."
    )[:_LOG_ENTRY_MAX]

    payload: dict[str, Any] = {
        "session_id": session_id,
        "log_entry": log_entry,
        "updates": [
            {
                "target_file": target,
                "operation": "create",
                "data": data,
            }
        ],
        # "orchestrator" — this write is backend orchestration, not an LLM agent.
        "metadata": {"agent": "orchestrator", "turn_number": 0},
    }
    return payload, archetype


def _is_pc_entity_op(op: Any, player_slug: str) -> bool:
    """Whether an updates[] op writes the PC's entity — by target path or by the
    slug of the name it carries (the same dual match ``seed_payload_vitality``
    uses, so the establishment pins and the seeders agree on identity)."""
    if not isinstance(op, dict):
        return False
    target = str(op.get("target_file"))
    if "/entities/" not in target:
        return False
    data = op.get("data")
    if not isinstance(data, dict):
        return False
    if target.endswith(f"/entities/{player_slug}.json"):
        return True
    name = str(data.get("name", "")).strip()
    return bool(name) and _slugify_entity(name) == player_slug


def strip_payload_pc_level(payload: Any, player_name: str) -> int:
    """Remove ``level`` from the PC's entity ops in an intro payload, in place.
    Returns how many were removed.

    ``level`` is engine-owned (RFC-0017), but the intro path runs no
    ``enforce_progression`` — so a DM emitting ``"level": 7`` at establishment
    would shallow-merge over the provisioned ``level: 1`` (or over a stored
    level, in the shared-tree 409 case) and persist unenforced. Stripping —
    rather than overwriting with 1 — lets fs-manager's merge keep whatever the
    engine already committed, which is correct in both cases. Tolerant of any
    malformed payload shape.
    """
    stripped = 0
    if not isinstance(payload, dict):
        return 0
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return 0
    player_slug = _slugify_entity(str(player_name or "").strip())
    if not player_slug:
        return 0
    for op in updates:
        if not _is_pc_entity_op(op, player_slug):
            continue
        if "level" in op["data"]:
            op["data"].pop("level")
            stripped += 1
    return stripped


def pin_hint_pc_level(hint: Any, player_name: str, level: int | None) -> int:
    """Pin (or strip) ``level`` on the PC's entries in a DM **hint** block, in
    place. Returns how many entries were touched.

    The display-side twin of ``strip_payload_pc_level`` (the #189 lesson: every
    engine-owned field needs a hint mirror, or the displayed value diverges from
    the persisted one until a reload). ``level`` as an int pins the engine's
    committed establishment value; None strips the DM's claim without asserting
    one (the 409 already-established case, where the stored level isn't known
    here — showing nothing beats showing a DM invention).
    """
    touched = 0
    if not isinstance(hint, dict):
        return 0
    chars = hint.get("characters")
    if not isinstance(chars, list):
        return 0
    player_slug = _slugify_entity(str(player_name or "").strip())
    if not player_slug:
        return 0
    for char in chars:
        if not isinstance(char, dict):
            continue
        name = str(char.get("name", "")).strip()
        if not name or _slugify_entity(name) != player_slug:
            continue
        if level is None:
            if "level" in char:
                char.pop("level")
                touched += 1
        elif char.get("level") != level:
            char["level"] = level
            touched += 1
    return touched

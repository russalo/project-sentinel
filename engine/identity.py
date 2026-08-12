"""Player-character identity enforcement (entity-identity hardening).

The companion to ``death_stakes.find_player_character``'s stable-identity
resolution: that stops an imposter from being *resolved* as the PC; this stops one
from being *minted* in the first place.

**The hole this closes.** ``fact_extractor`` passes ``role`` straight through
(``_strip_action`` strips only ``action``) and its ``update`` op upserts to a NEW
slug, and fs-manager writes an absent target. So a hallucinated or injected
``<world_update>`` could introduce e.g. ``0-imposter`` with ``role:"player"``.
Because characters load in ``sorted(glob("*.json"))`` filename order, that entity
sorted ahead of the real PC and became it — and since its name/slug differed from
the session PC, ``enforce_progression`` never matched it, so it could carry
``level: 5``, maxed stats, derived maxes and any archetype. Every RFC-0017 / 0018 /
0019 invariant was bypassable through the shadow.

**Mechanism (a), not (b)** (ADR-0004): ``role`` is *conditionally* writable — NPCs
legitimately carry one, and the authorized and hallucinated writes are
byte-identical ops — so a write-boundary guard structurally can't tell them apart.
This runs at the dispatch seam, like the progression and death-stakes injections.

**Neutralize, don't delete.** Only the ``role: "player"`` CLAIM is stripped; the
entity still lands as an ordinary NPC. The DM may have had a real narrative reason
to introduce the character — we take away the identity claim, not the character.
"""

from __future__ import annotations

from typing import Any

from .agents.fact_extractor import _slugify as _slugify_entity


def enforce_pc_identity(payload: Any, player_name: str) -> list[str]:
    """Strip a ``role: "player"`` claim from every entity op that isn't the PC's.

    Returns player-facing notices (parity with the other enforcers). In place;
    tolerant of any malformed payload shape. A blank ``player_name`` disables the
    guard — with no anchor we can't tell the PC from an imposter, and silently
    stripping every ``role:"player"`` would break a legacy world whose PC we can't
    identify.
    """
    if not isinstance(payload, dict):
        return []
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return []
    player_slug = _slugify_entity((player_name or "").strip())
    if not player_slug:
        return []

    stripped: list[str] = []
    for op in updates:
        if not isinstance(op, dict):
            continue
        target = str(op.get("target_file", ""))
        if "/entities/" not in target:
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            continue
        if str(data.get("role", "")).strip().lower() != "player":
            continue
        # Is this op the PC's own entity? Match the way the ops themselves are
        # addressed — by target slug OR by name — so a punctuation variant of the
        # PC's name ("O Neil" for stored "O'Neil", both o_neil.json) is still the PC.
        name = str(data.get("name", "")).strip()
        is_pc = target.endswith(f"/entities/{player_slug}.json") or (
            bool(name) and _slugify_entity(name) == player_slug
        )
        if is_pc:
            continue
        data.pop("role")
        stripped.append(name or target.rsplit("/", 1)[-1])

    if not stripped:
        return []
    who = ", ".join(dict.fromkeys(stripped))  # de-duped, order-preserving
    return [
        f"Only your character is the player character — a stray claim on {who} "
        "was ignored."
    ]

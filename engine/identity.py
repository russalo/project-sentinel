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


def _identity_key(value: Any) -> str | None:
    """A comparable identity for a character name: the Fact-Extractor slug when the
    name is sluggable, else the casefolded name.

    The fallback matters — ``_slugify`` returns None for a name with no ASCII slug
    characters (e.g. ``李``), and ``NewSessionRequest`` imposes no character set.
    Treating that as "no identity" would disable the guard AND make the resolver
    trust the first ``role:"player"`` entity, handing every such session back to an
    imposter (codex).
    """
    name = str(value or "").strip()
    if not name:
        return None
    return _slugify_entity(name) or name.casefold()


def _is_pc(name: Any, player_key: str) -> bool:
    """True when this character NAME resolves to the PC's identity."""
    return _identity_key(name) == player_key


def sanitize_hint_pc_identity(hint: Any, player_name: str) -> list[str]:
    """Strip a ``role: "player"`` claim from non-PC characters in a DM **hint**, in
    place. Returns player-facing notices.

    The display-side twin of ``enforce_pc_identity`` — and NOT optional. The hint is
    emitted before the payload is enforced, ``useDMStream`` applies it straight into
    ``worldStore``, and player-facing components fall back to *any*
    ``role === 'player'`` character — so an imposter would drive live vitals, check
    prompts and the level-up UI until a reload, even though disk state was clean.

    It must also run BEFORE the other hint normalizers: ``_locate_pc_in_hint``
    prefers ``role == "player"``, so an unsanitized imposter would be mistaken for
    the PC and have the real PC's authoritative level/stats/maxes copied onto it
    (codex).
    """
    if not isinstance(hint, dict):
        return []
    chars = hint.get("characters")
    if not isinstance(chars, list):
        return []
    player_key = _identity_key(player_name)
    if not player_key:
        return []

    stripped: list[str] = []
    repaired = False
    for char in chars:
        if not isinstance(char, dict):
            continue
        role = str(char.get("role", "")).strip().lower()
        # A hint fragment has no target_file, so the NAME is the only identity we
        # have here — that's fine: the hint never authorizes a write, it only drives
        # display, and the payload guard is what protects disk.
        if _is_pc(char.get("name"), player_key):
            # The PC's own entry (playtest 2026-09-13, the #192 sibling gap):
            # a role OTHER than "player" here would flow into worldStore and
            # orphan every component that locates the PC by role === "player"
            # (vitals silhouette, check prompts, level-up UI). Repair in place;
            # an explicit role:"player" is the normal shape and passes silently.
            if "role" in char and role != "player":
                char["role"] = "player"
                repaired = True
            continue
        if role != "player":
            continue
        # Explicit non-player role, not a pop: the client shallow-spreads top-level
        # character fields, so omitting the key would leave a previously-applied
        # `role:"player"` in the store.
        char["role"] = "npc"
        stripped.append(str(char.get("name", "")).strip() or "an unnamed character")
    return _notice(stripped) + _demotion_notice(repaired)


def _demotion_notice(repaired: bool) -> list[str]:
    """Player-facing notice for a repaired PC self-demotion (Item 4).

    A DM op/entry writing a non-player role onto the REAL PC is the sibling of
    the imposter mint: fs-manager's shallow merge would land it on disk, the
    DM's POV flips to whoever holds role:"player" next turn, and the SPA
    orphans the PC. Names aren't needed — it is always the session PC.
    """
    if not repaired:
        return []
    return [
        "Your character remains the player character — an attempt to change "
        "their role was ignored."
    ]


def _notice(stripped: list[str]) -> list[str]:
    if not stripped:
        return []
    who = ", ".join(dict.fromkeys(stripped))  # de-duped, order-preserving
    return [
        f"Only your character is the player character — a stray claim on {who} "
        "was ignored."
    ]


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
    if not str(player_name or "").strip():
        return []
    # Authorize from the TARGET PATH, never from the mutable `data`. An op for
    # `entities/imposter.json` carrying `{"name": "Sal", "role": "player"}` would
    # otherwise pass a name-based check and write a player role onto the imposter
    # (coderabbit). The Fact-Extractor derives the target from the same slug
    # contract, so a punctuation variant of the PC's name still targets its file.
    player_slug = _slugify_entity(str(player_name).strip())

    stripped: list[str] = []
    repaired = False
    for op in updates:
        if not isinstance(op, dict):
            continue
        target = str(op.get("target_file", ""))
        if "/entities/" not in target:
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            continue
        role = str(data.get("role", "")).strip().lower()
        if player_slug and target.endswith(f"/entities/{player_slug}.json"):
            # The PC's OWN file (authorized by TARGET PATH, as everywhere in
            # this guard). role:"player" here is the normal — and documented
            # RECOVERY — shape (playtest 2026-09-13: it repairs a previously
            # contaminated file) and passes untouched. Any OTHER role is a
            # self-demotion: fs-manager's shallow merge would flip the stored
            # role, hand the DM's POV to an imposter, and orphan the SPA's
            # role === "player" lookups. Repair in place (Item 4, the #192
            # sibling gap — the original guard only protected NON-PC ops).
            if "role" in data and role != "player":
                data["role"] = "player"
                repaired = True
            continue
        if role != "player":
            continue
        # An unsluggable PC name has no entity file the extractor could ever write,
        # so no op can legitimately be the PC's — strip them all.
        # Write an explicit non-player role rather than dropping the key: fs-manager
        # applies `existing.update(data)`, so merely omitting `role` would leave a
        # PREVIOUSLY STORED `role:"player"` in place (worlds predating this guard,
        # or one an imposter already landed) and the notice would be a lie (codex).
        data["role"] = "npc"
        stripped.append(str(data.get("name", "")).strip() or target.rsplit("/", 1)[-1])
    return _notice(stripped) + _demotion_notice(repaired)

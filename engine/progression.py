"""Engine-authoritative character progression (RFC-0017, ADR-0004 Slice 1).

`level` and `stats` are engine-owned: the DM *proposes* a level-up (the `level_up`
signal) and narrates it, but the engine — not the DM — commits `level` and the
single chosen `stats` raise, computed from the player-enacted ``LevelUpChoice``.
A DM `<world_update>` that raises `level`/`stats` on its own (no enactment, or
beyond the enacted delta) is overridden back to the authoritative value.

Mirrors ``engine/death_stakes.py``: a pure computation + an authoritative inject
at the backend dispatch seam (``backend/routes/stream.py``), reusing the
stored-``module_data`` deep-merge so a partial write can't wipe sibling module
state (the fs-manager ``update`` merge is shallow).

Scope (Slice 1): `level` (a top-level entity field) + `module_data.character_sheet.
stats` only. The derived `hp` / `magic_pool` bumps stay prompt-applied (the DM
still writes them) until the fast-follow slice gives the class HP factor a code
home — see RFC-0017 § Out of Scope. Those DM-written derived fields are preserved
here, not stripped.
"""

import copy
from typing import Any

from .agents.fact_extractor import _slugify as _slugify_entity
from .death_stakes import find_player_character

STATS = ("body", "mind", "heart", "will")
STAT_CAP = 10  # tracks the four-stat module cap; rises with it
MAX_LEVEL = 5  # tracks the milestone module's v0.1 level cap; rises with it


def _as_dict(value: Any) -> dict[str, Any]:
    """LLM-emitted state may be well-formed JSON of the wrong type — degrade,
    don't raise (the malformed-LLM-output hunt pattern)."""
    return value if isinstance(value, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` onto a copy of ``base`` (dict values only)."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def stored_level(character: dict[str, Any] | None) -> int:
    """Read the stored top-level ``level`` (>= 1; 1 if absent/malformed)."""
    return max(1, _to_int(_as_dict(character).get("level", 1), 1))


def stored_stats(character: dict[str, Any] | None) -> dict[str, int]:
    """Read the stored ``module_data.character_sheet.stats`` as a full {stat: int}."""
    raw = _as_dict(
        _as_dict(_as_dict(character).get("module_data")).get("character_sheet")
    ).get("stats")
    raw = _as_dict(raw)
    return {stat: _to_int(raw.get(stat, 0)) for stat in STATS}


def authoritative_progression(
    cur_level: int, cur_stats: dict[str, int], choice: dict[str, Any] | None
) -> tuple[int, dict[str, int]]:
    """The (level, stats) the engine will commit.

    - No enactment (``choice`` falsy) → freeze at the stored level/stats; the DM
      cannot advance them.
    - Enactment → ``level`` = the bounded ``to_level`` (or unchanged if absent),
      the chosen stat +1 (capped at ``STAT_CAP``); every other stat stays.

    Pure; ``choice`` is a ``LevelUpChoice``-shaped dict (``stat``/``to_level``).
    """
    level = cur_level
    stats = dict(cur_stats)
    choice = _as_dict(choice)
    if choice:
        # The engine advances by EXACTLY one level. The client-supplied `to_level`
        # is advisory (display/prompt) and NOT trusted for the commit — otherwise a
        # crafted client could jump straight to level 5 (gemini security-high). Capped
        # at the module max so re-enacting at the cap is a no-op.
        level = min(cur_level + 1, MAX_LEVEL)
        stat = choice.get("stat")
        if stat in STATS:
            stats[stat] = min(cur_stats.get(stat, 0) + 1, STAT_CAP)
    return level, stats


def _pc_entity_op(op: Any, player_name: str, slug: str | None) -> bool:
    """True if this op writes the player character's entity.

    Matches ``update`` AND ``create``: the DM path only ever emits ``update``
    (fact_extractor), but a direct-MCP caller could ``create`` an imposter PC file —
    gate that too so `level`/`stats` can't be granted through it (defense in depth;
    the broader "an imposter shadows the real PC in resolution" hole is filed
    separately — see the BACKLOG entity-identity item)."""
    if not isinstance(op, dict) or str(op.get("operation")) not in ("update", "create"):
        return False
    target = str(op.get("target_file", ""))
    if "/entities/" not in target:
        return False
    data = op.get("data")
    if (
        isinstance(data, dict)
        and str(data.get("name", "")).strip().lower()
        == (player_name or "").strip().lower()
    ):
        return True
    return bool(slug) and target.endswith(f"/entities/{slug}.json")


def enforce_progression(
    payload: dict[str, Any],
    *,
    stored_characters: list[dict[str, Any]],
    player_name: str,
    choice: dict[str, Any] | None,
) -> list[str]:
    """Make the engine's ``level`` + ``stats`` the authoritative PC write.

    On every PC entity op, force ``level`` and ``module_data.character_sheet.stats``
    to the authoritative values (stored, or stored + the enacted delta), deep-merging
    the stored ``module_data`` so the shallow fs-manager merge preserves siblings —
    ``combat``, ``magic``, and the DM's still-prompt-applied ``hp``/``magic_pool``.
    On an enactment with no PC op emitted, append one so the gain still commits.

    Returns player-facing notices when the DM attempted an unauthorized level/stats
    change (parity with ``death_stakes.enforce_permadeath`` rejections). PC-scoped;
    NPC writes pass through untouched.
    """
    if not isinstance(payload, dict):
        return []
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return []

    pc = find_player_character(stored_characters, player_name)
    if pc is None:
        # Can't resolve the PC's baseline (a real PC carries role=="player"; None
        # means identity drift). Fail SAFE — never force a real sheet to level 1 /
        # stats 0 on a mis-resolution (gemini/finder). The drift itself is a
        # separate entity-identity concern (filed in BACKLOG).
        return []
    cur_level = stored_level(pc)
    cur_stats = stored_stats(pc)
    auth_level, auth_stats = authoritative_progression(cur_level, cur_stats, choice)
    # Deep-copy: `pc` is an element of the caller's stored_characters
    # (world_context.characters). Merging/mutating below must not write back into
    # that shared read-state (gemini).
    base_md = copy.deepcopy(_as_dict(_as_dict(pc).get("module_data")))
    slug = _slugify_entity(player_name) if player_name else None

    matching = [op for op in updates if _pc_entity_op(op, player_name, slug)]
    if not matching:
        # No PC write this turn: only append one when an enactment must commit.
        if not choice or slug is None:
            return []
        op = {
            "target_file": f"data/state/core/entities/{slug}.json",
            "operation": "update",
            "data": {"name": player_name},
        }
        updates.append(op)
        matching = [op]

    dm_attempted = False
    for op in matching:
        data = op.get("data")
        if not isinstance(data, dict):
            if not choice:
                continue  # malformed op can't carry a level/stats attack
            data = {"name": player_name}
            op["data"] = data
        # Note a DM override attempt (for the player notice). Direct comparison so a
        # malformed write — a string `level`, a non-dict or partial `stats` — counts
        # as an attempt (malformed-LLM-output intolerance; gemini).
        level_bad = "level" in data and data["level"] != auth_level
        cs_in = _as_dict(_as_dict(data.get("module_data")).get("character_sheet"))
        stats_bad = "stats" in cs_in and cs_in["stats"] != auth_stats
        dm_attempted = dm_attempted or level_bad or stats_bad
        # Force on EVERY PC op — as the stats owner, protect them on the common turn
        # too (a plain damage turn writing only hp would otherwise let fs-manager's
        # shallow merge wipe stored stats/combat; finder issue 3). Write the FULL
        # module_data so the shallow merge preserves siblings: stored module_data <-
        # this op's same-turn changes <- authoritative stats.
        merged = _deep_merge(base_md, _as_dict(data.get("module_data")))
        sheet = _as_dict(merged.get("character_sheet"))
        sheet["stats"] = dict(auth_stats)
        merged["character_sheet"] = sheet
        data["module_data"] = merged
        data["level"] = auth_level

    notices: list[str] = []
    if dm_attempted:
        if choice:
            notices.append(
                "Level and stats are set by the engine from your enacted level-up — "
                "the DM's version was corrected to the chosen growth."
            )
        else:
            notices.append(
                "Level and stats can only change through an enacted level-up — the "
                "DM's attempted change was ignored."
            )
    return notices

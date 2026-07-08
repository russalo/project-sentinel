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

from typing import Any

from .agents.fact_extractor import _slugify as _slugify_entity
from .death_stakes import find_player_character

STATS = ("body", "mind", "heart", "will")
STAT_CAP = 10  # tracks the four-stat module cap; rises with it


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
        to_level = choice.get("to_level")
        if isinstance(to_level, int):
            level = to_level
        stat = choice.get("stat")
        if stat in STATS:
            stats[stat] = min(cur_stats.get(stat, 0) + 1, STAT_CAP)
    return level, stats


def _pc_entity_op(op: Any, player_name: str, slug: str | None) -> bool:
    """True if this update op targets the player character's entity file."""
    if not isinstance(op, dict) or str(op.get("operation")) != "update":
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
    cur_level = stored_level(pc)
    cur_stats = stored_stats(pc)
    auth_level, auth_stats = authoritative_progression(cur_level, cur_stats, choice)
    base_md = _as_dict(_as_dict(pc).get("module_data"))
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
        level_bad = "level" in data and _to_int(data["level"], auth_level) != auth_level
        dm_stats = _as_dict(
            _as_dict(data.get("module_data")).get("character_sheet")
        ).get("stats")
        stats_bad = isinstance(dm_stats, dict) and any(
            stat in dm_stats and _to_int(dm_stats.get(stat)) != auth_stats[stat]
            for stat in STATS
        )
        # Only rewrite when there's something to enforce: an enactment to commit,
        # or a DM level/stats change to override. A turn that doesn't touch
        # level/stats is left untouched — no gratuitous module_data injection.
        if not (choice or level_bad or stats_bad):
            continue
        dm_attempted = dm_attempted or level_bad or stats_bad
        # Full module_data so the shallow fs-manager merge preserves the sheet:
        # stored module_data <- this op's same-turn changes <- authoritative stats.
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

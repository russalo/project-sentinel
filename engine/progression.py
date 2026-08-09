"""Engine-authoritative character progression (RFC-0017 + RFC-0018, ADR-0004
Slice 1 + 1b).

`level` and `stats` are engine-owned: the DM *proposes* a level-up (the `level_up`
signal) and narrates it, but the engine — not the DM — commits `level` and the
single chosen `stats` raise, computed from the player-enacted ``LevelUpChoice``.
A DM `<world_update>` that raises `level`/`stats` on its own (no enactment, or
beyond the enacted delta) is overridden back to the authoritative value.

Mirrors ``engine/death_stakes.py``: a pure computation + an authoritative inject
at the backend dispatch seam (``backend/routes/stream.py``), reusing the
stored-``module_data`` deep-merge so a partial write can't wipe sibling module
state (the fs-manager ``update`` merge is shallow).

Scope: `level` (a top-level entity field) + `module_data.character_sheet.stats`
(Slice 1); PLUS the derived vitality **maxes** `hp.max` (= Body × class HP factor)
and `magic_pool.max` (= Will × 2, casters only) — Slice 1b / RFC-0018. The maxes
are deterministic from the engine-owned stats + the class factor, so the engine
owns them on every PC op; a DM-inflated max is overridden. The **currents**
(`hp.current` / `magic_pool.current`) stay narrative-owned (damage / casting) —
the engine touches `current` only to grant a level-up's growth (bump by the max
delta) or to seed a first-established max. This module stays a PURE computation:
the class factor is resolved to a rules dict by ``engine/class_rules.py`` (the IO
boundary) and passed in; when it can't resolve (a free-text class that isn't a
known archetype), the maxes are left DM-authored — fail-safe, see
``authoritative_maxes``.
"""

import copy
from typing import Any

from .agents.fact_extractor import _slugify as _slugify_entity
from .death_stakes import find_player_character

STATS = ("body", "mind", "heart", "will")
STAT_CAP = 10  # tracks the four-stat module cap; rises with it
MAX_LEVEL = 5  # tracks the milestone module's v0.1 level cap; rises with it
MAGIC_POOL_PER_WILL = 2  # magic_pool.max = Will × 2 (RFC-0008 realm-pool-v1)


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


def _apply_max(
    pool: Any, new_max: int, growth: int, stored_pool: dict[str, Any]
) -> dict[str, Any]:
    """Force a ``{current, max}`` vitality pool's ``max`` and grant a level-up's
    ``growth`` to ``current`` (RFC-0018). Returns the pool dict (``pool`` is the
    op's merged pool — stored ⊕ this turn's DM write).

    - ``max`` := ``new_max`` (engine-owned; silently reconciles a stale stored max).
    - **Growth** (``growth > 0`` — the HP/pool gained *from the raised stat* this
      level-up, NOT the max delta): ``current`` := the *stored* current + ``growth``,
      so a wounded PC keeps their wound (30/56 → 38/64). Keying on the stat-driven
      growth — not ``new_max − stored_max`` — means reconciling a stale max, or a
      level-up that raised a *non-governing* stat (Mind, not Body), never heals
      (codex: a Body-6 Warrior raising Mind stays wounded, not 28/48).
    - **Otherwise** ``current`` is narrative-owned and left exactly as the DM wrote
      it — a damage / casting / reconcile turn must not touch it. Only a genuinely
      *absent* current (first establishment) is seeded to ``new_max`` so a max never
      ships without one; a DM-written current that turn (e.g. damage) is kept.
    """
    pool = _as_dict(pool)
    pool["max"] = new_max
    if growth > 0:
        stored_current = stored_pool.get("current")
        pool["current"] = (
            _to_int(stored_current) + growth if stored_current is not None else new_max
        )
    elif "current" not in pool:
        pool["current"] = new_max
    return pool


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


def authoritative_maxes(
    stats: dict[str, int], class_rules: dict[str, Any] | None
) -> tuple[int | None, int | None]:
    """The engine-owned derived maxes ``(hp_max, magic_pool_max)`` for a PC.

    ``hp_max = Body × hp_factor`` and ``magic_pool_max = Will × 2`` (casters
    only). Pure: ``class_rules`` is the resolved ``{hp_factor, magic}`` dict for
    the PC's class (from ``engine/class_rules.py``), or None.

    Returns None for a max the engine cannot derive — so the caller leaves it
    DM-authored (fail-safe):
    - ``hp_max`` is None when there's no positive ``hp_factor`` (no class rules,
      or a free-text class that isn't a known archetype).
    - ``magic_pool_max`` is None for a non-caster (``magic`` falsy) — non-casters
      get no ``magic_pool`` written (RFC-0018 D4).
    """
    rules = _as_dict(class_rules)
    factor = _to_int(rules.get("hp_factor", 0))
    hp_max = _to_int(stats.get("body", 0)) * factor if factor > 0 else None
    magic_pool_max = (
        _to_int(stats.get("will", 0)) * MAGIC_POOL_PER_WILL
        if rules.get("magic")
        else None
    )
    return hp_max, magic_pool_max


def authoritative_for_pc(
    stored_characters: list[dict[str, Any]],
    player_name: str,
    choice: dict[str, Any] | None,
) -> tuple[int, dict[str, int]] | None:
    """The (level, stats) the engine will commit for the PC, or None if the PC
    can't be resolved. Used to mirror the committed values into the SSE hint (so the
    player sees a level-up live, not only after hydration) AND — recomputed —
    enforced at dispatch; deterministic, so both agree."""
    pc = find_player_character(stored_characters, player_name)
    if pc is None:
        return None
    return authoritative_progression(stored_level(pc), stored_stats(pc), choice)


def authoritative_vitality_for_pc(
    stored_characters: list[dict[str, Any]],
    player_name: str,
    choice: dict[str, Any] | None,
    class_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    """The engine's verdict on the PC's derived vitality, for BOTH consumers.

    Returns ``{"hp_max": int|None, "magic_pool_max": int|None,
    "strip_magic_pool": bool}``:
    - the maxes the engine owns this turn (None → DM-authored, fail-safe), and
    - whether a *resolved* non-caster's ``magic_pool`` should be dropped.

    Single source of truth so the SSE hint (display) and ``enforce_progression``
    (persisted state) can never disagree about an engine-owned field — the whole
    point of the fast-follow. Honors the same guards as enforcement: an
    unresolvable PC and a stored-**dead** PC both yield "engine owns nothing"
    (a dead PC's vitality is left alone — see ``enforce_progression``).
    """
    none = {
        "hp_max": None,
        "magic_pool_max": None,
        "strip_magic_pool": False,
        "hp_pool": None,
        "magic_pool": None,
    }
    pc = find_player_character(stored_characters, player_name)
    if pc is None:
        return none
    if str(_as_dict(pc).get("status", "")).strip().lower() == "dead":
        return none
    cur_stats = stored_stats(pc)
    _, auth_stats = authoritative_progression(stored_level(pc), cur_stats, choice)
    hp_max, mp_max = authoritative_maxes(auth_stats, class_rules)

    # The COMPLETE {current, max} the engine will commit on a growth turn, so the
    # SSE hint can mirror the whole pool rather than only patching a max the DM
    # may not have emitted at all (the RFC-0018 prompts tell the DM not to write
    # vitality on a level-up, so a growth turn's hint usually carries no pool).
    # None when there's no growth — then `current` is narrative-owned and only the
    # max is authoritative.
    stored_sheet = _as_dict(
        _as_dict(_as_dict(pc).get("module_data")).get("character_sheet")
    )

    def _grown(stat: str, per: int, new_max: int | None, key: str):
        if new_max is None:
            return 0, None
        growth = (auth_stats.get(stat, 0) - cur_stats.get(stat, 0)) * per
        if growth <= 0:
            return growth, None
        stored_pool = _as_dict(stored_sheet.get(key))
        stored_current = stored_pool.get("current")
        current = (
            _to_int(stored_current) + growth if stored_current is not None else new_max
        )
        return growth, {"current": current, "max": new_max}

    factor = _to_int(_as_dict(class_rules).get("hp_factor", 0))
    _, hp_pool = _grown("body", factor, hp_max, "hp")
    _, magic_pool = _grown("will", MAGIC_POOL_PER_WILL, mp_max, "magic_pool")

    return {
        "hp_max": hp_max,
        "magic_pool_max": mp_max,
        # A resolved non-caster (rules present, magic falsy) owns no pool; an
        # unresolved free-text class (None) must NOT strip — fail-safe.
        "strip_magic_pool": isinstance(class_rules, dict)
        and not class_rules.get("magic"),
        # Complete pools to mirror on a growth turn (None = no growth this turn).
        "hp_pool": hp_pool,
        "magic_pool": magic_pool,
    }


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
    class_rules: dict[str, Any] | None = None,
) -> list[str]:
    """Make the engine's ``level`` + ``stats`` (+ derived maxes) the authoritative
    PC write.

    On every PC entity op, force ``level`` and ``module_data.character_sheet.stats``
    to the authoritative values (stored, or stored + the enacted delta), deep-merging
    the stored ``module_data`` so the shallow fs-manager merge preserves siblings —
    ``combat``, ``magic``, and the narrative-owned ``hp``/``magic_pool`` currents.
    On an enactment with no PC op emitted, append one so the gain still commits.

    RFC-0018 (``class_rules`` supplied): also force the derived **maxes**
    ``hp.max = Body × factor`` and (casters) ``magic_pool.max = Will × 2`` from the
    authoritative stats, and grant a level-up's growth by bumping the matching
    ``current`` by the max delta (or seeding ``current = max`` on first
    establishment). The **currents** are otherwise untouched — a plain damage turn
    (no growth) leaves ``hp.current`` exactly as the DM wrote it. When
    ``class_rules`` can't derive a max (None / free-text class not an archetype),
    that max is left DM-authored — fail-safe (see ``authoritative_maxes``). Clamping
    ``current ≤ max`` is out of scope (a combat-lane follow-up).

    Returns player-facing notices when the DM attempted an unauthorized
    level/stats/max change (parity with ``death_stakes.enforce_permadeath``
    rejections). PC-scoped; NPC writes pass through untouched.
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

    # RFC-0018 derived maxes, computed once against the STORED sheet (the baseline
    # before this turn) so the growth delta and the DM-attempt check are stable
    # across multiple same-turn PC ops. None → that max is left DM-authored.
    stored_sheet = _as_dict(
        _as_dict(_as_dict(pc).get("module_data")).get("character_sheet")
    )
    stored_hp = _as_dict(stored_sheet.get("hp"))
    stored_mp = _as_dict(stored_sheet.get("magic_pool"))
    # The SAME verdict the SSE hint normalizer consumes, so display and persisted
    # state can't disagree. Encapsulates the fail-safe (unresolved class) and the
    # stored-DEAD skip: the downstream permadeath gate (`enforce_permadeath`, run
    # AFTER this) drops HP-restore fields, so injecting a max for a dead PC would
    # leave the dispatched module_data carrying an incomplete pool that the shallow
    # fs-manager merge then persists over the stored one.
    vitality = authoritative_vitality_for_pc(
        stored_characters, player_name, choice, class_rules
    )
    new_hp_max = vitality["hp_max"]
    new_mp_max = vitality["magic_pool_max"]
    known_non_caster = vitality["strip_magic_pool"]
    if new_hp_max is None and new_mp_max is None and not known_non_caster:
        class_rules = None  # engine owns nothing here (dead PC / unresolved class)
    # The current-bump is the vitality gained FROM THE RAISED STAT this level-up —
    # ``(new stat − stored stat) × factor`` — NOT ``new_max − stored_max``. Keying
    # on the stat delta means reconciling a stale stored max never heals, and a
    # level-up that raised a *non-governing* stat (Mind, not Body) grants no HP
    # (codex: a Body-6 Warrior raising Mind must not gain HP). The engine raises
    # exactly one stat by +1 (or 0 at the cap), so this is the factor or 0.
    factor = _to_int(_as_dict(class_rules).get("hp_factor", 0))
    hp_growth = (
        (auth_stats.get("body", 0) - cur_stats.get("body", 0)) * factor
        if new_hp_max is not None
        else 0
    )
    mp_growth = (
        (auth_stats.get("will", 0) - cur_stats.get("will", 0)) * MAGIC_POOL_PER_WILL
        if new_mp_max is not None
        else 0
    )

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
    max_attempted = False
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
        # A DM write to an engine-owned max (only checked when the engine actually
        # owns it — new_*_max not None) is a separate attempt → the vitality notice.
        hp_in = _as_dict(cs_in.get("hp"))
        mp_in = _as_dict(cs_in.get("magic_pool"))
        hp_max_bad = (
            new_hp_max is not None
            and "max" in hp_in
            and _to_int(hp_in.get("max")) != new_hp_max
        )
        mp_max_bad = (
            new_mp_max is not None
            and "max" in mp_in
            and _to_int(mp_in.get("max")) != new_mp_max
        )
        max_attempted = max_attempted or hp_max_bad or mp_max_bad
        # Force on EVERY PC op — as the stats owner, protect them on the common turn
        # too (a plain damage turn writing only hp would otherwise let fs-manager's
        # shallow merge wipe stored stats/combat; finder issue 3). Write the FULL
        # module_data so the shallow merge preserves siblings: stored module_data <-
        # this op's same-turn changes <- authoritative stats.
        merged = _deep_merge(base_md, _as_dict(data.get("module_data")))
        sheet = _as_dict(merged.get("character_sheet"))
        sheet["stats"] = dict(auth_stats)
        # RFC-0018: force the derived maxes the engine owns (skip a None — that max
        # stays DM-authored, fail-safe). Only the stat-driven `*_growth` bumps
        # `current`; a plain / reconcile / establishment turn leaves it to the DM.
        if new_hp_max is not None:
            sheet["hp"] = _apply_max(sheet.get("hp"), new_hp_max, hp_growth, stored_hp)
        if new_mp_max is not None:
            sheet["magic_pool"] = _apply_max(
                sheet.get("magic_pool"), new_mp_max, mp_growth, stored_mp
            )
        elif known_non_caster:
            # A resolved non-caster (Warrior/Rogue) owns no pool — drop a DM-written
            # one from this op so it can't land (codex P2). NOT done for an
            # unresolved free-text class (class_rules None → fail-safe, leave it be).
            sheet.pop("magic_pool", None)
        merged["character_sheet"] = sheet
        data["module_data"] = merged
        data["level"] = auth_level
        # Accumulate across multiple same-turn PC ops: fs-manager applies them in
        # order with a shallow merge, so a later op must carry the earlier ops'
        # module_data changes (e.g. an hp bump) or it would revert them to stored
        # (codex). `merged` is a fresh dict — no aliasing back to `pc`.
        base_md = merged

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
    if max_attempted:
        notices.append(
            "Maximum health and magic are derived by the engine from your stats and "
            "class — the DM's values were corrected."
        )
    return notices

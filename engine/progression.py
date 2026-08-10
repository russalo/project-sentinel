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


def _canonical_archetype(value: Any, archetypes: tuple[str, ...] | None) -> str | None:
    """The canonically-cased archetype slug for ``value``, or None if it isn't one of
    ``archetypes`` (RFC-0019). Pure — the caller resolves the valid set from the
    bound class module (``engine/class_rules.canonical_archetype`` does the IO)."""
    if not archetypes or not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    for name in archetypes:
        if isinstance(name, str) and name.lower() == key:
            return name
    return None


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
        "hp_growth": 0,
        "magic_growth": 0,
    }
    pc = find_player_character(stored_characters, player_name)
    if pc is None:
        return none
    if str(_as_dict(pc).get("status", "")).strip().lower() == "dead":
        return none
    cur_stats = stored_stats(pc)
    _, auth_stats = authoritative_progression(stored_level(pc), cur_stats, choice)
    hp_max, mp_max = authoritative_maxes(auth_stats, class_rules)

    # The COMPLETE {current, max} the engine will commit, so the SSE hint can
    # mirror a whole pool rather than only patching a max the DM may not have
    # emitted at all — the RFC-0018 prompts tell the DM not to write vitality, so
    # its hint often carries no pool (a growth turn), or no character_sheet at all
    # (a status/combat-only turn). `current` = the stored current plus this
    # level-up's growth (0 on an ordinary turn, so the narrative current is
    # unchanged — the hint consumer only uses this when the DM emitted no pool).
    # None when nothing is derivable (no engine max, or no stored current and no
    # growth) — never invent a pool with no real current.
    stored_sheet = _as_dict(
        _as_dict(_as_dict(pc).get("module_data")).get("character_sheet")
    )

    def _pool(stat: str, per: int, new_max: int | None, key: str):
        """(growth, complete pool | None) for one vitality pool."""
        if new_max is None:
            return 0, None
        growth = max(0, (auth_stats.get(stat, 0) - cur_stats.get(stat, 0)) * per)
        stored_current = _as_dict(stored_sheet.get(key)).get("current")
        if stored_current is None:
            # Nothing stored: only a growth turn justifies seeding a full pool.
            return growth, ({"current": new_max, "max": new_max} if growth else None)
        return growth, {"current": _to_int(stored_current) + growth, "max": new_max}

    factor = _to_int(_as_dict(class_rules).get("hp_factor", 0))
    hp_growth, hp_pool = _pool("body", factor, hp_max, "hp")
    magic_growth, magic_pool = _pool("will", MAGIC_POOL_PER_WILL, mp_max, "magic_pool")

    return {
        "hp_max": hp_max,
        "magic_pool_max": mp_max,
        # A resolved non-caster (rules present, magic falsy) owns no pool; an
        # unresolved free-text class (None) must NOT strip — fail-safe.
        "strip_magic_pool": isinstance(class_rules, dict)
        and not class_rules.get("magic"),
        # Complete {current, max} pools for the hint to mirror when the DM emitted
        # none (None = not derivable). `*_growth` > 0 marks a level-up that raised
        # the governing stat — there enforcement OVERRIDES the DM's current with
        # stored+growth, so the hint must mirror the complete pool even when the DM
        # did emit one.
        "hp_pool": hp_pool,
        "magic_pool": magic_pool,
        "hp_growth": hp_growth,
        "magic_growth": magic_growth,
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
    archetypes: tuple[str, ...] | None = None,
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

    RFC-0019 (``archetypes`` supplied — the bound class module's archetype slugs):
    also pin the top-level ``archetype``, the mechanical handle that maps a
    free-text ``class`` ("Proctor") onto a rules-data key ("cleric"). **Write-once:**
    a valid stored value is forced on every PC op (so a DM re-map — ``rogue`` →
    ``warrior``, i.e. Body×6 → Body×8 free HP — is overridden with a notice); with
    none stored, a DM-emitted value is accepted only if it names a real archetype,
    and an invalid one is dropped so the PC stays unclassified and the next turn can
    retry. ``class`` itself is untouched — it stays the character's flavor.

    Returns player-facing notices when the DM attempted an unauthorized
    level/stats/max/archetype change (parity with ``death_stakes.enforce_permadeath``
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

    # RFC-0019: the pinned archetype. A stored value that isn't a real archetype is
    # treated as absent so a garbage/legacy slug can be re-established rather than
    # forced forever (self-healing).
    pinned_archetype = _canonical_archetype(_as_dict(pc).get("archetype"), archetypes)

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
    archetype_attempted = False
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
        # RFC-0019 archetype pin (write-once). Precedence:
        #  - a valid STORED archetype is forced on every PC op, so a DM re-map is
        #    overridden (it would otherwise be a free HP lever via the class factor);
        #  - otherwise a DM-emitted value establishes it, but only if it names a real
        #    archetype — an invalid one is dropped so the PC stays unclassified and
        #    the next turn can retry, rather than persisting an unresolvable slug.
        if archetypes:
            if pinned_archetype is not None:
                if (
                    "archetype" in data
                    and _canonical_archetype(data.get("archetype"), archetypes)
                    != pinned_archetype
                ):
                    archetype_attempted = True
                data["archetype"] = pinned_archetype
            elif "archetype" in data:
                accepted = _canonical_archetype(data.get("archetype"), archetypes)
                if accepted is None:
                    data.pop("archetype")
                else:
                    data["archetype"] = accepted
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
    if archetype_attempted:
        notices.append(
            "Your character's archetype is set once, when they're established — the "
            "DM's attempt to change it was ignored."
        )
    return notices

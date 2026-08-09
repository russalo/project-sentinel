"""RFC-0018 / ADR-0004 Slice 1b — engine-authoritative derived maxes.

The engine owns the PC's ``hp.max`` (= Body × class factor) and, for casters,
``magic_pool.max`` (= Will × 2), forced on every PC op from the authoritative
stats + the resolved class rules. The currents stay narrative-owned; a level-up's
growth bumps the matching current by the max delta. When the class can't be
resolved to a factor, the maxes are left DM-authored (fail-safe).
"""

from engine import progression
from engine.class_rules import resolve_class_rules
from engine.modules.registry import registry

WARRIOR = {"hp_factor": 8, "magic": None}
MAGE = {"hp_factor": 4, "magic": "arcane"}


def _payload(ops):
    return {"session_id": "s", "log_entry": "x" * 10, "updates": ops}


def _op(**data):
    data.setdefault("name", "Kael")
    return {
        "target_file": "data/state/core/entities/kael.json",
        "operation": "update",
        "data": data,
    }


def _pc(stats, *, hp=None, magic_pool=None, level=2, name="Kael"):
    sheet = {"stats": stats}
    if hp is not None:
        sheet["hp"] = hp
    if magic_pool is not None:
        sheet["magic_pool"] = magic_pool
    return {
        "role": "player",
        "name": name,
        "level": level,
        "module_data": {"character_sheet": sheet},
    }


def _sheet(payload, idx=-1):
    return payload["updates"][idx]["data"]["module_data"]["character_sheet"]


# ── pure computation ──────────────────────────────────────────────────────────


def test_maxes_warrior_hp_only():
    assert progression.authoritative_maxes({"body": 6, "will": 5}, WARRIOR) == (
        48,
        None,
    )


def test_maxes_mage_hp_and_pool():
    assert progression.authoritative_maxes({"body": 3, "will": 8}, MAGE) == (12, 16)


def test_maxes_none_class_rules_fail_safe():
    assert progression.authoritative_maxes({"body": 6, "will": 8}, None) == (None, None)


def test_maxes_zero_factor_is_none():
    assert progression.authoritative_maxes({"body": 6}, {"hp_factor": 0}) == (
        None,
        None,
    )


# ── enforcement: forcing on every PC op ───────────────────────────────────────


def test_forces_hp_max_on_plain_turn_current_preserved():
    # A damage turn (no level-up): the DM writes hp.current; the engine forces the
    # max from Body×factor and leaves the DM's current untouched (narrative-owned).
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload([_op(module_data={"character_sheet": {"hp": {"current": 40}}})])
    notices = progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 56 and hp["current"] == 40
    assert notices == []


def test_fail_safe_leaves_dm_max_when_class_unresolved():
    # class_rules None (a free-text class) → engine doesn't own the max; a DM write
    # to hp.max survives untouched.
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload([_op(module_data={"character_sheet": {"hp": {"max": 999}}})])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=None,
    )
    assert _sheet(payload)["hp"]["max"] == 999


def test_dm_inflated_max_overridden_with_notice():
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload([_op(module_data={"character_sheet": {"hp": {"max": 999}}})])
    notices = progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert _sheet(payload)["hp"]["max"] == 56
    assert any("Maximum health" in n for n in notices)


def test_body_level_up_grows_hp_and_bumps_current():
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 64 and hp["current"] == 64  # 8×8, +8 delta on 56


def test_body_level_up_bumps_wounded_current_by_delta():
    # Wounded (30/56) → grows to /64 with current 30+8=38, not a full heal.
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 30, "max": 56}
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 64 and hp["current"] == 38


def test_will_level_up_grows_pool_not_hp_for_caster():
    pc = _pc(
        {"body": 3, "mind": 5, "heart": 4, "will": 7},
        hp={"current": 12, "max": 12},
        magic_pool={"current": 14, "max": 14},
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice={"stat": "will", "to_level": 3},
        class_rules=MAGE,
    )
    sheet = _sheet(payload)
    assert sheet["hp"] == {"current": 12, "max": 12}  # Body unchanged → no HP growth
    assert sheet["magic_pool"] == {"current": 16, "max": 16}  # 8×2, +2 on 14


def test_non_governing_stat_level_up_does_not_heal():
    # codex: a Body-6 Warrior with a stale-low stored max (20/40) who raises MIND
    # (not Body) must NOT gain HP — reconcile max to 48 but keep current 20.
    pc = _pc(
        {"body": 6, "mind": 5, "heart": 5, "will": 5}, hp={"current": 20, "max": 40}
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice={"stat": "mind", "to_level": 3},
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 48 and hp["current"] == 20  # reconciled, not healed


def test_body_level_up_on_stale_max_heals_only_by_factor():
    # A stale 20/40 Warrior raises BODY 6→7: max → 56, but current gains exactly the
    # factor (8) from the raised point, NOT the full stale reconciliation. 20 → 28.
    pc = _pc(
        {"body": 6, "mind": 5, "heart": 5, "will": 5}, hp={"current": 20, "max": 40}
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 56 and hp["current"] == 28  # +8 (one Body × factor)


def test_dead_pc_max_not_injected():
    # codex: a stored-dead PC must NOT receive an engine-injected max — the
    # permadeath gate strips HP-restore right after, which would otherwise persist
    # an incomplete pool over the stored one via the shallow merge.
    pc = _pc({"body": 7, "mind": 5, "heart": 6, "will": 4})
    pc["status"] = "dead"
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert "hp" not in _sheet(payload)  # no max injected for a dead PC


def test_non_caster_gets_no_magic_pool():
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert "magic_pool" not in _sheet(payload)


def test_first_establishment_seeds_current_to_max():
    # A PC with stats but no hp block yet (first combat) → engine seeds full HP.
    pc = _pc({"body": 5, "mind": 5, "heart": 5, "will": 5})
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert _sheet(payload)["hp"] == {"current": 40, "max": 40}  # 5×8, seeded full


def test_establishment_with_damage_keeps_dm_current():
    # First-combat establishment that ALSO took damage: the engine sets max but
    # must keep the DM's wounded current, not seed full (codex P1).
    pc = _pc({"body": 5, "mind": 5, "heart": 5, "will": 5})  # no hp block stored
    payload = _payload([_op(module_data={"character_sheet": {"hp": {"current": 20}}})])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert _sheet(payload)["hp"] == {"current": 20, "max": 40}  # DM current kept


def test_stale_max_reconciled_without_healing():
    # A plain damage turn where the stored max is stale/low (40 < Body6×8=48):
    # the engine reconciles max → 48 but must NOT bump the DM's damaged current.
    pc = _pc(
        {"body": 6, "mind": 5, "heart": 5, "will": 5}, hp={"current": 30, "max": 40}
    )
    payload = _payload([_op(module_data={"character_sheet": {"hp": {"current": 25}}})])
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    hp = _sheet(payload)["hp"]
    assert hp["max"] == 48 and hp["current"] == 25  # reconciled, not healed


def test_known_non_caster_magic_pool_stripped():
    # A resolved Warrior owns no pool: a DM-written magic_pool is dropped from the
    # op so it can't land (codex P2).
    pc = _pc(
        {"body": 7, "mind": 5, "heart": 6, "will": 4}, hp={"current": 56, "max": 56}
    )
    payload = _payload(
        [
            _op(
                module_data={
                    "character_sheet": {"magic_pool": {"current": 5, "max": 10}}
                }
            )
        ]
    )
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=WARRIOR,
    )
    assert "magic_pool" not in _sheet(payload)


def test_free_text_class_does_not_strip_magic_pool():
    # An UNRESOLVED free-text class must NOT strip a DM-written pool (fail-safe):
    # the engine doesn't know it's a non-caster.
    pc = _pc({"body": 6, "mind": 5, "heart": 5, "will": 6})
    payload = _payload(
        [
            _op(
                module_data={
                    "character_sheet": {"magic_pool": {"current": 8, "max": 12}}
                }
            )
        ]
    )
    progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Kael",
        choice=None,
        class_rules=None,
    )
    assert _sheet(payload)["magic_pool"] == {"current": 8, "max": 12}  # preserved


# ── the shared verdict (hint + enforcement consume the same helper) ───────────


def test_vitality_verdict_matches_enforcement_for_caster():
    pc = _pc(
        {"body": 3, "mind": 5, "heart": 4, "will": 7},
        hp={"current": 12, "max": 12},
        magic_pool={"current": 14, "max": 14},
    )
    v = progression.authoritative_vitality_for_pc(
        [pc], "Kael", {"stat": "will", "to_level": 3}, MAGE
    )
    assert v["hp_max"] == 12 and v["magic_pool_max"] == 16
    assert v["strip_magic_pool"] is False
    # Will was raised → a complete grown pool for the hint to mirror (14 + 2).
    assert v["magic_pool"] == {"current": 16, "max": 16}
    assert v["magic_growth"] == 2  # Will raised → enforcement overrides current
    # Body unchanged → no HP growth, but a complete pool is still offered for a
    # hint that omits one (current unchanged from stored).
    assert v["hp_pool"] == {"current": 12, "max": 12}
    assert v["hp_growth"] == 0


def test_vitality_verdict_flags_non_caster_strip():
    pc = _pc({"body": 6, "mind": 5, "heart": 5, "will": 5})
    v = progression.authoritative_vitality_for_pc([pc], "Kael", None, WARRIOR)
    assert v["hp_max"] == 48
    assert v["magic_pool_max"] is None
    assert v["strip_magic_pool"] is True


def test_vitality_verdict_fail_safe_on_unresolved_class():
    pc = _pc({"body": 6, "mind": 5, "heart": 5, "will": 5})
    v = progression.authoritative_vitality_for_pc([pc], "Kael", None, None)
    # Engine owns nothing — and must NOT claim a non-caster strip (fail-safe).
    assert v["hp_max"] is None and v["magic_pool_max"] is None
    assert v["strip_magic_pool"] is False
    assert v["hp_pool"] is None and v["magic_pool"] is None


def test_vitality_verdict_dead_pc_owns_nothing():
    pc = _pc({"body": 7, "mind": 5, "heart": 6, "will": 4})
    pc["status"] = "dead"
    v = progression.authoritative_vitality_for_pc([pc], "Kael", None, WARRIOR)
    assert v["hp_max"] is None and v["magic_pool_max"] is None
    assert v["strip_magic_pool"] is False  # dead PC: engine owns nothing at all
    assert v["hp_pool"] is None and v["magic_pool"] is None


def test_vitality_verdict_unresolvable_pc_owns_nothing():
    v = progression.authoritative_vitality_for_pc([], "Kael", None, WARRIOR)
    assert v["hp_max"] is None and v["magic_pool_max"] is None
    assert v["strip_magic_pool"] is False
    assert v["hp_pool"] is None and v["magic_pool"] is None


# ── end-to-end chain: real class module resolution → enforcement ──────────────


def test_real_module_resolve_then_enforce_warrior():
    # The full RFC-0018 contract with the REAL four-class module (not an injected
    # dict): a default-modules world resolves "Warrior" → factor 8 and forces
    # hp.max = Body×8, no magic_pool.
    registry.clear()
    try:
        pc = _pc(
            {"body": 6, "mind": 5, "heart": 5, "will": 5},
            hp={"current": 48, "max": 48},
            name="Bran",
        )
        pc["class"] = "Warrior"
        rules = resolve_class_rules(None, pc["class"])
        payload = _payload(
            [
                {
                    "target_file": "data/state/core/entities/bran.json",
                    "operation": "update",
                    "data": {"name": "Bran"},
                }
            ]
        )
        progression.enforce_progression(
            payload,
            stored_characters=[pc],
            player_name="Bran",
            choice=None,
            class_rules=rules,
        )
        sheet = _sheet(payload)
        assert sheet["hp"]["max"] == 48  # 6×8
        assert "magic_pool" not in sheet
    finally:
        registry.clear()


def test_real_module_free_text_class_is_fail_safe():
    # A default-modules world with a free-text class (the Sal/Chez case) resolves
    # to None → enforcement leaves a DM-written hp.max untouched.
    registry.clear()
    try:
        pc = _pc({"body": 6, "mind": 5, "heart": 5, "will": 5}, name="Chez")
        pc["class"] = "chaingang boss"
        rules = resolve_class_rules(None, pc["class"])
        assert rules is None
        payload = _payload(
            [
                {
                    "target_file": "data/state/core/entities/chez.json",
                    "operation": "update",
                    "data": {
                        "name": "Chez",
                        "module_data": {"character_sheet": {"hp": {"max": 200}}},
                    },
                }
            ]
        )
        progression.enforce_progression(
            payload,
            stored_characters=[pc],
            player_name="Chez",
            choice=None,
            class_rules=rules,
        )
        assert _sheet(payload)["hp"]["max"] == 200  # DM value survives
    finally:
        registry.clear()

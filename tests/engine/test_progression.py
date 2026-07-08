"""RFC-0017 / ADR-0004 Slice 1 — engine-authoritative level + stats.

The engine, not the DM, commits `level` and the chosen `stats` raise, from the
player-enacted LevelUpChoice. A DM `<world_update>` that raises them on its own —
with no enactment, or beyond the enacted delta — is overridden.
"""

from engine import progression


def _pc(level=2, **stat_overrides):
    stats = {"body": 7, "mind": 5, "heart": 6, "will": 4}
    stats.update(stat_overrides)
    return {
        "role": "player",
        "name": "Kael",
        "level": level,
        "module_data": {
            "character_sheet": {"stats": stats, "hp": {"current": 56, "max": 56}},
            "combat": {"death_saves_failed": 1},
        },
    }


def _payload(ops):
    return {"session_id": "s", "log_entry": "x" * 10, "updates": ops}


def _op(**data):
    data.setdefault("name", "Kael")
    return {
        "target_file": "data/state/core/entities/kael.json",
        "operation": "update",
        "data": data,
    }


# ── pure computation ──────────────────────────────────────────────────────────


def test_authoritative_no_enactment_freezes_stored():
    level, stats = progression.authoritative_progression(2, {"body": 7}, None)
    assert level == 2 and stats == {"body": 7}


def test_authoritative_enactment_applies_delta_and_caps():
    level, stats = progression.authoritative_progression(
        2, {"body": 7, "will": 4}, {"stat": "will", "to_level": 3}
    )
    assert level == 3 and stats["will"] == 5 and stats["body"] == 7


def test_authoritative_stat_cap():
    _, stats = progression.authoritative_progression(
        9, {"body": 10}, {"stat": "body", "to_level": 10}
    )
    assert stats["body"] == 10  # already at cap, stays


def test_client_cannot_jump_levels():
    # A crafted client enacts from level 2 with a spoofed to_level=5 — the engine
    # commits exactly +1, not the client's value (gemini security-high).
    level, _ = progression.authoritative_progression(
        2, {"body": 7}, {"stat": "body", "to_level": 5}
    )
    assert level == 3


def test_level_capped_at_max():
    level, _ = progression.authoritative_progression(
        5, {"body": 7}, {"stat": "body", "to_level": 5}
    )
    assert level == 5  # re-enacting at the cap is a no-op


# ── enforcement (the dispatch-seam override) ──────────────────────────────────


def test_dm_level_stats_write_without_enactment_is_overridden_with_notice():
    payload = _payload(
        [_op(level=9, module_data={"character_sheet": {"stats": {"body": 10}}})]
    )
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    data = payload["updates"][0]["data"]
    assert data["level"] == 2  # forced back to stored
    assert data["module_data"]["character_sheet"]["stats"]["body"] == 7
    assert notices  # player is told


def test_enacted_level_up_commits_the_authorized_delta():
    payload = _payload([_op()])
    progression.enforce_progression(
        payload,
        stored_characters=[_pc()],
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
    )
    data = payload["updates"][0]["data"]
    assert data["level"] == 3
    assert data["module_data"]["character_sheet"]["stats"]["body"] == 8


def test_over_application_on_enacted_turn_is_corrected():
    # Player chose heart; the DM instead raised will and over-leveled.
    payload = _payload(
        [_op(level=5, module_data={"character_sheet": {"stats": {"will": 7}}})]
    )
    notices = progression.enforce_progression(
        payload,
        stored_characters=[_pc()],
        player_name="Kael",
        choice={"stat": "heart", "to_level": 3},
    )
    stats = payload["updates"][0]["data"]["module_data"]["character_sheet"]["stats"]
    assert payload["updates"][0]["data"]["level"] == 3
    assert stats["will"] == 4 and stats["heart"] == 7
    assert notices


def test_sibling_module_data_and_dm_hp_are_preserved():
    # hp is prompt-applied (Slice 1b) — a DM hp bump must survive; so must combat.
    payload = _payload(
        [_op(module_data={"character_sheet": {"hp": {"current": 64, "max": 64}}})]
    )
    progression.enforce_progression(
        payload,
        stored_characters=[_pc()],
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
    )
    md = payload["updates"][0]["data"]["module_data"]
    assert md["character_sheet"]["hp"] == {"current": 64, "max": 64}  # DM hp kept
    assert md["combat"] == {"death_saves_failed": 1}  # stored sibling kept


def test_enacted_with_no_pc_op_appends_the_write():
    payload = _payload([])
    progression.enforce_progression(
        payload,
        stored_characters=[_pc()],
        player_name="Kael",
        choice={"stat": "mind", "to_level": 3},
    )
    assert len(payload["updates"]) == 1
    data = payload["updates"][0]["data"]
    assert data["level"] == 3
    assert data["module_data"]["character_sheet"]["stats"]["mind"] == 6


def test_npc_writes_pass_through_untouched():
    npc_op = {
        "target_file": "data/state/core/entities/goblin.json",
        "operation": "update",
        "data": {"name": "Goblin", "level": 9},
    }
    payload = _payload([npc_op])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    assert payload["updates"][0]["data"]["level"] == 9  # NPC untouched
    assert not notices


def test_normal_pc_write_freezes_level_stats_and_preserves_siblings():
    # A turn that writes the PC (status) without touching level/stats: no notice,
    # but the stats owner still freezes level/stats to stored AND writes the full
    # stored module_data so a partial write can't let the shallow merge wipe
    # siblings (finder issue 3).
    payload = _payload([_op(status="wounded")])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    data = payload["updates"][0]["data"]
    assert data["status"] == "wounded"  # DM's narrative field preserved
    assert data["level"] == 2  # frozen to stored
    assert data["module_data"]["character_sheet"]["stats"] == {
        "body": 7,
        "mind": 5,
        "heart": 6,
        "will": 4,
    }
    assert data["module_data"]["combat"] == {"death_saves_failed": 1}  # sibling kept
    assert not notices  # the DM didn't attempt a level/stats change


def test_no_pc_op_no_enactment_is_a_noop():
    payload = _payload([])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    assert payload["updates"] == [] and not notices


def test_does_not_mutate_stored_characters():
    import copy

    stored = [_pc()]
    before = copy.deepcopy(stored)
    payload = _payload(
        [_op(module_data={"character_sheet": {"hp": {"current": 64, "max": 64}}})]
    )
    progression.enforce_progression(
        payload,
        stored_characters=stored,
        player_name="Kael",
        choice={"stat": "body", "to_level": 3},
    )
    assert stored == before  # the shared read-state is untouched


def test_malformed_stats_and_level_are_overridden():
    # A non-dict `stats` + a string `level` with no enactment must be forced back
    # to stored, not silently written (malformed-LLM-output).
    payload = _payload(
        [_op(level="99", module_data={"character_sheet": {"stats": "hacked"}})]
    )
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    data = payload["updates"][0]["data"]
    assert data["level"] == 2
    assert data["module_data"]["character_sheet"]["stats"] == {
        "body": 7,
        "mind": 5,
        "heart": 6,
        "will": 4,
    }
    assert notices


def test_create_op_imposter_pc_is_neutralized():
    # Defense-in-depth (finder issue 1): a direct-MCP `create` op impersonating the
    # PC (name match) can't grant level/stats — forced to the real stored baseline.
    # (Not LLM-reachable: fact_extractor only emits `update`.)
    op = {
        "target_file": "data/state/core/entities/0-imposter.json",
        "operation": "create",
        "data": {
            "name": "Kael",
            "role": "player",
            "level": 5,
            "module_data": {
                "character_sheet": {
                    "stats": {"body": 10, "mind": 10, "heart": 10, "will": 10}
                }
            },
        },
    }
    payload = _payload([op])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    data = payload["updates"][0]["data"]
    assert data["level"] == 2
    assert data["module_data"]["character_sheet"]["stats"] == {
        "body": 7,
        "mind": 5,
        "heart": 6,
        "will": 4,
    }
    assert notices


def test_unresolvable_pc_is_not_force_zeroed():
    # Fail-safe (finder issue 2): when the PC can't be resolved (no role=="player"
    # AND name mismatch), enforcement skips rather than forcing a real sheet to
    # level 1 / stats 0.
    mislabeled = [
        {
            "role": "hero",
            "name": "Sir Kael",  # != session player_name "Kael"
            "level": 3,
            "module_data": {
                "character_sheet": {
                    "stats": {"body": 8, "mind": 5, "heart": 6, "will": 4}
                }
            },
        }
    ]
    payload = _payload([_op(level=3)])
    notices = progression.enforce_progression(
        payload, stored_characters=mislabeled, player_name="Kael", choice=None
    )
    assert payload["updates"][0]["data"]["level"] == 3  # untouched, NOT forced to 1
    assert not notices


def test_authoritative_for_pc_resolves_and_returns_none():
    assert progression.authoritative_for_pc([_pc()], "Kael", None) == (
        2,
        {"body": 7, "mind": 5, "heart": 6, "will": 4},
    )
    assert progression.authoritative_for_pc([], "Kael", None) is None


def test_multi_op_accumulates_earlier_module_data():
    # Two PC ops in one turn: op1 bumps hp, op2 doesn't. fs-manager applies them in
    # order with a shallow merge, so op2 must carry op1's hp or it reverts it to
    # stored (codex). The last op should hold the accumulated hp.
    op1 = _op(module_data={"character_sheet": {"hp": {"current": 64, "max": 64}}})
    op2 = _op(status="wounded")
    payload = _payload([op1, op2])
    progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    last_hp = payload["updates"][-1]["data"]["module_data"]["character_sheet"]["hp"]
    assert last_hp == {"current": 64, "max": 64}  # op1's bump survives into op2


def test_malformed_payload_and_stored_degrade():
    assert (
        progression.enforce_progression(
            None, stored_characters=[], player_name="Kael", choice=None
        )
        == []
    )
    # malformed stored PC (module_data a string) must not raise
    bad = [{"role": "player", "name": "Kael", "level": 2, "module_data": "oops"}]
    payload = _payload([_op(level=9)])
    progression.enforce_progression(
        payload, stored_characters=bad, player_name="Kael", choice=None
    )
    assert payload["updates"][0]["data"]["level"] == 2

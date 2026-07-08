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


def test_normal_pc_write_without_level_stats_is_left_untouched():
    # A turn that writes the PC (status/location) but doesn't touch level/stats and
    # has no enactment must be left alone — no gratuitous module_data/combat inject.
    payload = _payload([_op(status="wounded")])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    data = payload["updates"][0]["data"]
    assert data == {"name": "Kael", "status": "wounded"}  # unchanged
    assert not notices


def test_no_pc_op_no_enactment_is_a_noop():
    payload = _payload([])
    notices = progression.enforce_progression(
        payload, stored_characters=[_pc()], player_name="Kael", choice=None
    )
    assert payload["updates"] == [] and not notices


def test_malformed_payload_and_stored_degrade():
    assert progression.enforce_progression(
        None, stored_characters=[], player_name="Kael", choice=None
    ) == []
    # malformed stored PC (module_data a string) must not raise
    bad = [{"role": "player", "name": "Kael", "level": 2, "module_data": "oops"}]
    payload = _payload([_op(level=9)])
    progression.enforce_progression(
        payload, stored_characters=bad, player_name="Kael", choice=None
    )
    assert payload["updates"][0]["data"]["level"] == 2

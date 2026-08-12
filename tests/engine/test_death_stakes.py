"""RFC-0014 death-stakes enforcement — pure-core unit tests.

Covers the engine-authoritative outcome (Q1=2a), the tamper-proof server-side
margin recompute (seam 2), and the permadeath revival gate (Q2).
"""

from __future__ import annotations

from engine.death_stakes import (
    DEATH_CLOCK_MAX,
    DeathSaveOutcome,
    apply_death_outcome,
    enforce_permadeath,
    find_player_character,
    recompute_margin,
    resolve_death_save,
    stored_death_clock,
    stored_will,
)


def _pc(status="unconscious", will=5, failed=0, name="Aria", role="player"):
    return {
        "name": name,
        "role": role,
        "status": status,
        "module_data": {
            "character_sheet": {"stats": {"will": will}, "hp": {"current": 0}},
            "combat": {"death_saves_failed": failed},
        },
    }


# ── resolve_death_save + recompute_margin ────────────────────────────────────


def test_margin_recomputed_from_rolled_and_stored_will_only():
    # rolled 50 + will 8×5 (40) − 60 = 30. Client total/margin never consulted.
    assert recompute_margin(rolled=50, will=8) == 30
    assert recompute_margin(rolled=10, will=2) == -40


def test_success_stabilizes_and_resets_clock():
    out = resolve_death_save(rolled=60, will=5, current_failed=2)  # 60+25-60=+25
    assert out == DeathSaveOutcome(
        failed=0, status="unconscious", stabilized=True, died=False, margin=25
    )


def test_failure_advances_clock_but_survives():
    out = resolve_death_save(rolled=10, will=2, current_failed=0)  # 10+10-60=-40
    assert out.failed == 1 and out.status == "unconscious" and not out.died


def test_third_failure_is_death():
    out = resolve_death_save(rolled=1, will=1, current_failed=2)  # margin<0, 2→3
    assert out.failed == DEATH_CLOCK_MAX and out.status == "dead" and out.died


def test_tamper_proof_a_bad_roll_cannot_be_saved_by_a_forged_margin():
    # A crafted client could send margin=+999, but the engine ignores it and
    # recomputes from rolled=3 + will=1 → −52 → a failure.
    out = resolve_death_save(rolled=3, will=1, current_failed=0)
    assert out.margin < 0 and out.failed == 1


# ── stored-state readers ─────────────────────────────────────────────────────


def test_stored_readers_default_safely():
    assert stored_will({}) == 0
    assert stored_death_clock({}) == 0
    assert stored_will(_pc(will=7)) == 7
    assert stored_death_clock(_pc(failed=2)) == 2


def test_find_player_anchors_on_the_session_name_not_role():
    """Entity-identity hardening: the session's PC name is the anchor, and
    `role: "player"` is NOT trusted once we know it — an imposter sorting earlier
    in filename order must not become the PC."""
    imposter = _pc(name="0-imposter", role="player")
    real = {"name": "Aria", "role": "npc"}
    assert find_player_character([imposter, real], "Aria")["name"] == "Aria"


def test_find_player_matches_on_slug_not_exact_string():
    # "O Neil" and "O'Neil" are both o_neil.json — the same entity.
    chars = [{"name": "O'Neil", "role": "npc"}]
    assert find_player_character(chars, "O Neil")["name"] == "O'Neil"


def test_find_player_returns_none_rather_than_trusting_role():
    # A known PC name that matches nothing → None (enforcement safely no-ops).
    # Falling back to role here is exactly how the imposter used to win.
    chars = [_pc(name="0-imposter", role="player")]
    assert find_player_character(chars, "Aria") is None


def test_find_player_resolves_a_role_npc_pc_entity():
    # Live-world case (`monkster`, 12 turns): the PC entity exists and matches the
    # session name but was never tagged role=player. It must still resolve.
    chars = [{"name": "monkster", "role": "npc"}]
    assert find_player_character(chars, "monkster")["name"] == "monkster"


def test_find_player_legacy_role_scan_when_no_name_is_known():
    chars = [_pc(name="Goblin", role="enemy"), _pc(name="Aria", role="player")]
    assert find_player_character(chars, "")["name"] == "Aria"


# ── apply_death_outcome (engine authority beats the DM) ──────────────────────


def test_outcome_overrides_a_conflicting_dm_status():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "alive"},  # DM tried to keep alive
            }
        ]
    }
    out = DeathSaveOutcome(
        failed=3, status="dead", stabilized=False, died=True, margin=-9
    )
    apply_death_outcome(payload, player_name="Aria", outcome=out)
    data = payload["updates"][0]["data"]
    assert data["status"] == "dead"  # engine wins
    assert data["module_data"]["combat"]["death_saves_failed"] == 3


def test_outcome_appends_op_when_dm_emitted_none():
    payload = {"updates": []}
    out = DeathSaveOutcome(
        failed=1, status="unconscious", stabilized=False, died=False, margin=-3
    )
    apply_death_outcome(payload, player_name="Aria", outcome=out)
    op = payload["updates"][0]
    assert op["target_file"].endswith("/entities/aria.json")
    assert op["data"]["status"] == "unconscious"
    assert op["data"]["module_data"]["combat"]["death_saves_failed"] == 1


def test_outcome_preserves_stored_character_sheet():
    # fs-manager shallow-merges module_data, so the death write must carry the
    # FULL sheet or `will`/stats are erased (codex P1). We pass stored_module_data.
    stored_md = {
        "character_sheet": {"stats": {"will": 8, "body": 5}, "hp": {"current": 0}}
    }
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria"},
            }
        ]
    }
    out = DeathSaveOutcome(
        failed=1, status="unconscious", stabilized=False, died=False, margin=-3
    )
    apply_death_outcome(
        payload, player_name="Aria", outcome=out, stored_module_data=stored_md
    )
    md = payload["updates"][0]["data"]["module_data"]
    assert md["character_sheet"]["stats"]["will"] == 8  # sheet preserved
    assert md["combat"]["death_saves_failed"] == 1  # clock added


def test_outcome_wins_across_multiple_ops():
    # The Fact-Extractor can emit multiple ops for one entity, run in order; a
    # later DM op must not un-dead a rolled death (codex P1) — set on every op.
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "alive"},
            },
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "alive"},
            },
        ]
    }
    out = DeathSaveOutcome(
        failed=3, status="dead", stabilized=False, died=True, margin=-9
    )
    apply_death_outcome(payload, player_name="Aria", outcome=out)
    assert all(
        op["data"]["status"] == "dead" for op in payload["updates"]
    )  # last wins → dead


def test_pure_functions_tolerate_malformed_input():
    # Non-dict module_data / character / payload must degrade, not raise.
    assert stored_will({"module_data": ["not", "a", "dict"]}) == 0
    assert stored_death_clock({"module_data": "nope"}) == 0
    assert stored_will(None) == 0
    assert find_player_character("not-a-list", "Aria") is None
    assert (
        apply_death_outcome(
            "not-a-dict",
            player_name="Aria",
            outcome=DeathSaveOutcome(0, "dead", False, True, -1),
        )
        == "not-a-dict"
    )


# ── enforce_permadeath ───────────────────────────────────────────────────────


def test_permadeath_off_is_a_noop():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "alive"},
            }
        ]
    }
    out, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="dead")],
        player_name="Aria",
        permadeath=False,
    )
    assert rej == [] and out["updates"][0]["data"]["status"] == "alive"


def test_permadeath_noop_when_stored_pc_not_dead():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "alive"},
            }
        ]
    }
    out, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="unconscious")],
        player_name="Aria",
        permadeath=True,
    )
    assert rej == []  # dying/reviving an un-dead PC is not gated


def test_permadeath_status_gate_is_an_allowlist():
    # A prose-y status that isn't in the old denylist must still be blocked.
    for word in ("stable", "conscious", "recovering", "awake", "injured"):
        payload = {
            "updates": [
                {
                    "target_file": "data/state/core/entities/aria.json",
                    "operation": "update",
                    "data": {"name": "Aria", "status": word},
                }
            ]
        }
        _, rej = enforce_permadeath(
            payload,
            stored_characters=[_pc(status="dead")],
            player_name="Aria",
            permadeath=True,
        )
        assert "status" not in payload["updates"][0]["data"], f"{word} slipped past"
        assert rej


def test_permadeath_status_dead_is_allowed_to_stand():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {"name": "Aria", "status": "dead"},
            }
        ]
    }
    _, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="dead")],
        player_name="Aria",
        permadeath=True,
    )
    assert payload["updates"][0]["data"]["status"] == "dead" and rej == []


def test_permadeath_blocks_renamed_player_revival():
    # A rename/clone under a new name/slug dodges the name match — the role
    # "player" catch closes it.
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria_the_reborn.json",
                "operation": "update",
                "data": {
                    "name": "Aria the Reborn",
                    "role": "player",
                    "status": "alive",
                    "health": 100,
                },
            }
        ]
    }
    _, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="dead")],
        player_name="Aria",
        permadeath=True,
    )
    data = payload["updates"][0]["data"]
    assert "status" not in data and "health" not in data and rej


def test_permadeath_blocks_hp_max_and_clock_reset():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {
                    "name": "Aria",
                    "module_data": {
                        "character_sheet": {"hp": {"max": 100}},
                        "combat": {"death_saves_failed": 0},
                    },
                },
            }
        ]
    }
    _, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="dead")],
        player_name="Aria",
        permadeath=True,
    )
    md = payload["updates"][0]["data"]["module_data"]
    assert "max" not in md["character_sheet"]["hp"]  # hp.max drop
    assert "death_saves_failed" not in md["combat"]  # clock-reset drop
    assert rej


def test_permadeath_refuses_status_revival_and_hp_restore():
    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/aria.json",
                "operation": "update",
                "data": {
                    "name": "Aria",
                    "status": "alive",  # revival attempt
                    "health": 50,  # HP restore attempt
                    "module_data": {"character_sheet": {"hp": {"current": 30}}},
                },
            }
        ]
    }
    out, rej = enforce_permadeath(
        payload,
        stored_characters=[_pc(status="dead")],
        player_name="Aria",
        permadeath=True,
    )
    data = out["updates"][0]["data"]
    assert "status" not in data  # revival dropped
    assert "health" not in data  # flat HP restore dropped
    assert (
        "current" not in data["module_data"]["character_sheet"]["hp"]
    )  # module HP dropped
    assert any("Revival refused" in r for r in rej)

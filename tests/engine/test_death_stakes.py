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


def test_find_player_prefers_role_then_name():
    chars = [_pc(name="Goblin", role="enemy"), _pc(name="Aria", role="player")]
    assert find_player_character(chars, "someone")["name"] == "Aria"
    chars2 = [{"name": "Aria", "role": "npc"}]  # no role=player → fall back to name
    assert find_player_character(chars2, "aria")["name"] == "Aria"


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

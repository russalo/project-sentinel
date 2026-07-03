"""RFC-0014 death-stakes — backend orchestration (the /api/stream seam).

Proves the wiring the pure-core tests can't: that a `death_save` resolve turn
routes to engine-authoritative resolution and that the committed outcome +
permadeath gate reach the dispatched payload — overriding the DM.
"""

import json
from pathlib import Path

PC = "Aria"
SESSION_DEATH = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
SESSION_PERMA = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"


def _prime_session(data_dir: Path, session_id: str, *, permadeath: bool) -> None:
    d = data_dir / "state" / "core" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_name": "Test World",
                "started_at": "2026-07-02T00:00:00Z",
                "turns": [],
                "active": True,
                "world_id": "7c0ffee0-0000-4000-8000-000000000000",
                "player_character_name": PC,
                "permadeath": permadeath,
            }
        ),
        encoding="utf-8",
    )


def _prime_pc(data_dir: Path, *, status: str, will: int = 1, failed: int = 0) -> None:
    d = data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    (d / "aria.json").write_text(
        json.dumps(
            {
                "name": PC,
                "role": "player",
                "status": status,
                "module_data": {
                    "character_sheet": {"stats": {"will": will}, "hp": {"current": 0}},
                    "combat": {"death_saves_failed": failed},
                },
            }
        ),
        encoding="utf-8",
    )


def _pc_op(payload: dict) -> dict | None:
    for op in payload.get("updates", []):
        if str(op.get("target_file", "")).endswith("/entities/aria.json"):
            return op
    return None


def test_engine_overrides_dm_on_a_fatal_death_save(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # Clock already at 2; a failing save (rolled 1 + will 1×5 − 60 = −54) is the
    # third strike → dead, no matter what the DM narrates.
    _prime_session(tmp_data_dir, SESSION_DEATH, permadeath=False)
    _prime_pc(tmp_data_dir, status="unconscious", will=1, failed=2)

    # The DM (wrongly) tries to keep Aria alive.
    fake_openai.chat.completions.set_stream_tokens(
        [
            "She staggers... ",
            '<world_update>{"characters":[{"name":"Aria","action":"upsert",'
            '"status":"alive"}]}</world_update>',
        ]
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "hold on",
            "sessionId": SESSION_DEATH,
            "roll": {
                "kind": "death_save",
                "stat": "will",
                "rolled": 1,
                "bonus": 5,
                "total": 6,
                "target": 60,
                "margin": 999,  # a forged favorable margin — must be ignored
                "openEnded": None,
            },
        },
    )
    assert resp.status_code == 200
    _ = resp.text  # drain the generator

    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op is not None
    assert op["data"]["status"] == "dead"  # engine wins over the DM's "alive"
    assert op["data"]["module_data"]["combat"]["death_saves_failed"] == 3


SESSION_BYPASS = "cccccccc-3333-4333-8333-cccccccccccc"
SESSION_ALIVE = "dddddddd-4444-4444-8444-dddddddddddd"
SESSION_SHEET = "eeeeeeee-5555-4555-8555-eeeeeeeeeeee"


def test_death_save_derived_from_stored_status_not_client_kind(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # Bypass attempt: PC is unconscious (clock 2), client sends kind="skill" to
    # dodge engine authority. The backend derives the death save from STORED
    # status, so the third failure still lands as `dead`.
    _prime_session(tmp_data_dir, SESSION_BYPASS, permadeath=False)
    _prime_pc(tmp_data_dir, status="unconscious", will=1, failed=2)
    fake_openai.chat.completions.set_stream_tokens(["...she fades from the light..."])
    resp = client.post(
        "/api/stream",
        json={
            "action": "hang on",
            "sessionId": SESSION_BYPASS,
            "roll": {
                "kind": "skill",
                "stat": "will",
                "rolled": 1,
                "bonus": 5,
                "total": 6,
                "target": 60,
                "margin": 0,
            },  # forged kind ignored
        },
    )
    assert resp.status_code == 200
    body = resp.text
    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op is not None and op["data"]["status"] == "dead"
    # The SSE world_update must carry the committed death even though the DM
    # emitted no <world_update> block (the mirror adds a PC entry) — codex P2.
    assert '"world_update"' in body and '"dead"' in body


def test_no_death_save_when_pc_not_unconscious(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # False-trigger: PC is alive, client sends kind="death_save". The engine must
    # NOT resolve a death save — the DM's narration stands.
    _prime_session(tmp_data_dir, SESSION_ALIVE, permadeath=False)
    _prime_pc(tmp_data_dir, status="alive", will=5, failed=0)
    fake_openai.chat.completions.set_stream_tokens(
        [
            '<world_update>{"characters":[{"name":"Aria","action":"upsert",'
            '"status":"alive"}]}</world_update>'
        ]
    )
    resp = client.post(
        "/api/stream",
        json={
            "action": "swing sword",
            "sessionId": SESSION_ALIVE,
            "roll": {
                "kind": "death_save",
                "stat": "will",
                "rolled": 1,
                "bonus": 25,
                "total": 26,
                "target": 60,
                "margin": -34,
            },
        },
    )
    assert resp.status_code == 200
    _ = resp.text
    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op is not None and op["data"]["status"] == "alive"
    assert "combat" not in op["data"].get("module_data", {})


def test_death_save_preserves_stored_character_sheet(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # A stabilizing save must not erase the sheet: the dispatched op carries the
    # full module_data so fs-manager's shallow merge keeps stats.
    _prime_session(tmp_data_dir, SESSION_SHEET, permadeath=False)
    _prime_pc(tmp_data_dir, status="unconscious", will=8, failed=0)
    fake_openai.chat.completions.set_stream_tokens(["...a shallow, ragged breath..."])
    resp = client.post(
        "/api/stream",
        json={
            "action": "cling",
            "sessionId": SESSION_SHEET,
            "roll": {
                "kind": "death_save",
                "stat": "will",
                "rolled": 50,
                "bonus": 40,
                "total": 90,
                "target": 60,
                "margin": 30,
            },
        },
    )
    assert resp.status_code == 200
    _ = resp.text
    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op is not None
    assert (
        op["data"]["module_data"]["character_sheet"]["stats"]["will"] == 8
    )  # preserved


def test_permadeath_refuses_revival_with_feedback(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    _prime_session(tmp_data_dir, SESSION_PERMA, permadeath=True)
    _prime_pc(tmp_data_dir, status="dead")

    # The DM tries to revive the permadead PC on an ordinary turn.
    fake_openai.chat.completions.set_stream_tokens(
        [
            "A warm light... ",
            '<world_update>{"characters":[{"name":"Aria","action":"upsert",'
            '"status":"alive","health":50}]}</world_update>',
        ]
    )

    resp = client.post(
        "/api/stream", json={"action": "pray for a miracle", "sessionId": SESSION_PERMA}
    )
    assert resp.status_code == 200
    body = resp.text

    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op is not None
    assert "status" not in op["data"]  # revival dropped
    assert "health" not in op["data"]  # HP restore dropped
    assert "Revival refused" in body  # surfaced to the player

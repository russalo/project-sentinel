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

"""Tests for the /api/sessions browse + export endpoints (training router)."""

import json

import engine

_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _write_session(tmp_data_dir):
    sessions = tmp_data_dir / "state" / "core" / "sessions"
    session = {
        "session_id": _UUID,
        "world_name": "Test Realm",
        "started_at": "2026-01-01T00:00:00Z",
        "active": True,
        "player_character_name": "Cowboy Bob",
        "dm_persona_name": "Oracle",
        "turns": [
            {
                "turn_number": 0,
                "player_action": "start",
                "narrative": "You arrive at the crossroads.",
                "world_updates": {
                    "world": {"tension": 3},
                    "characters": [
                        {
                            "name": "Mira",
                            "action": "upsert",
                            "status": "alive",
                            "role": "npc",
                        }
                    ],
                },
            }
        ],
    }
    (sessions / f"{_UUID}.json").write_text(json.dumps(session), encoding="utf-8")


def test_list_sessions(client, tmp_data_dir):
    _write_session(tmp_data_dir)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["sessionId"] == _UUID
    assert data[0]["worldName"] == "Test Realm"
    assert data[0]["persona"] == "Oracle"
    assert data[0]["turnCount"] == 1


def test_list_sessions_empty(client):
    assert client.get("/api/sessions").json() == []


def test_get_session(client, tmp_data_dir):
    _write_session(tmp_data_dir)
    body = client.get(f"/api/sessions/{_UUID}").json()
    assert body["sessionId"] == _UUID
    assert body["persona"] == "Oracle"
    assert len(body["turns"]) == 1


def test_get_session_missing_or_bad_id_404(client):
    assert client.get(f"/api/sessions/{_UUID}").status_code == 404
    assert (
        client.get("/api/sessions/not-a-uuid").status_code == 404
    )  # path-traversal guard


def test_export_schema_is_downloadable_and_valid(client, tmp_data_dir):
    _write_session(tmp_data_dir)
    r = client.get(f"/api/sessions/{_UUID}/export", params={"format": "schema"})
    assert r.status_code == 200
    assert ".schema.jsonl" in r.headers["content-disposition"]
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert lines
    ex = json.loads(lines[0])
    assert engine.validate(ex["target"]).ok


def test_export_chatlog_has_labels(client, tmp_data_dir):
    _write_session(tmp_data_dir)
    r = client.get(f"/api/sessions/{_UUID}/export", params={"format": "chatlog"})
    assert r.status_code == 200
    assert ".chatlog.md" in r.headers["content-disposition"]
    assert "Cowboy_Bob: " in r.text
    assert "Oracle: " in r.text


def test_export_rejects_bad_format(client, tmp_data_dir):
    _write_session(tmp_data_dir)
    r = client.get(f"/api/sessions/{_UUID}/export", params={"format": "bogus"})
    assert r.status_code == 422  # Query pattern validation

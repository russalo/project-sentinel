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


def test_list_uses_filename_stem_as_canonical_id(client, tmp_data_dir):
    # If the JSON session_id disagrees with the filename, the summary must use
    # the filename stem — that's what read_session keys off, so detail/export
    # links built from it resolve instead of 404ing.
    sessions = tmp_data_dir / "state" / "core" / "sessions"
    (sessions / f"{_UUID}.json").write_text(
        json.dumps({"session_id": "WRONG", "world_name": "W", "turns": []}),
        encoding="utf-8",
    )
    listed = client.get("/api/sessions").json()
    assert listed[0]["sessionId"] == _UUID
    # And that id resolves on the detail endpoint.
    assert client.get(f"/api/sessions/{_UUID}").status_code == 200


def test_list_orders_most_recent_first(client, tmp_data_dir):
    import os

    sessions = tmp_data_dir / "state" / "core" / "sessions"
    older = "11111111-1111-4111-8111-111111111111"
    newer = "22222222-2222-4222-8222-222222222222"
    for sid in (older, newer):
        (sessions / f"{sid}.json").write_text(
            json.dumps({"session_id": sid, "world_name": sid[:4], "turns": []}),
            encoding="utf-8",
        )
    os.utime(sessions / f"{older}.json", (1_000_000, 1_000_000))
    os.utime(sessions / f"{newer}.json", (2_000_000, 2_000_000))
    ids = [s["sessionId"] for s in client.get("/api/sessions").json()]
    assert ids == [newer, older]

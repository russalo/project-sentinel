"""Tests for POST /api/stream (SSE streaming DM turn).

The stream handler is the hot-path endpoint — every player action
goes through it. The tests verify:

- The SSE event sequence matches what useDMStream.js expects
  (``token`` events, then ``world_update``, then ``[DONE]``)
- The session must exist on disk or the endpoint rejects
- The WorldContext loader picks up prior entities from data/
- Turns are appended to the session file via the engine dispatch
- Fact-Extractor output is dispatched to fs-manager after the
  stream closes
- Errors from the LLM produce a structured ``error`` SSE event
  followed by ``[DONE]``

All engine calls are stubbed via fixtures in conftest.py.
"""

import json
from pathlib import Path

import pytest

# The Fact-Extractor self-validates session_id as format: uuid AND
# read_session rejects non-UUID paths for path-traversal defense, so
# tests that want to hit a real session file must use real UUIDs.
VALID_SESSION_ID = "11111111-2222-3333-4444-555555555555"
VALID_SESSION_ID_2 = "22222222-3333-4444-5555-666666666666"
VALID_SESSION_ID_3 = "33333333-4444-5555-6666-777777777777"
VALID_SESSION_ID_4 = "44444444-5555-6666-7777-888888888888"
VALID_SESSION_ID_5 = "55555555-6666-7777-8888-999999999999"


def _prime_session(data_dir: Path, session_id: str, turns: list | None = None) -> None:
    """Write a minimal valid session file to disk so read_session
    returns it. Tests that need a starting session call this first."""
    session_dir = data_dir / "state" / "core" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_name": "Test World",
                "started_at": "2026-04-13T00:00:00Z",
                "turns": turns or [],
                "active": True,
            }
        ),
        encoding="utf-8",
    )


def _parse_sse_events(text: str) -> list:
    """Parse an SSE response body into a list of events.

    Each event is either a parsed JSON dict (for ``data: {...}``
    lines) or the literal string ``"[DONE]"`` for the sentinel.
    """
    events = []
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :].strip()
        if payload == "[DONE]":
            events.append("[DONE]")
        else:
            events.append(json.loads(payload))
    return events


def _dm_stream_tokens() -> list[str]:
    # A DM response split into small chunks to simulate token streaming.
    full = (
        "The fire crackles as you approach.\n"
        "<world_update>\n"
        '{"world": {"tension": 4}, "characters": [{"name": "Kael", "action": "upsert", "role": "npc", "status": "alive"}]}\n'
        "</world_update>"
    )
    return [full[i : i + 15] for i in range(0, len(full), 15)]


def test_stream_rejects_missing_session(client):
    response = client.post(
        "/api/stream", json={"action": "look around", "sessionId": "nonexistent"}
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_stream_happy_path_emits_token_world_update_and_done(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    session_id = VALID_SESSION_ID
    _prime_session(tmp_data_dir, session_id)

    fake_openai.chat.completions.set_stream_tokens(_dm_stream_tokens())

    response = client.post(
        "/api/stream",
        json={"action": "step forward", "sessionId": session_id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(response.text)
    # There should be multiple token events, then one world_update,
    # then [DONE].
    token_events = [e for e in events if isinstance(e, dict) and e.get("type") == "token"]
    world_update_events = [
        e for e in events if isinstance(e, dict) and e.get("type") == "world_update"
    ]
    assert len(token_events) >= 1
    assert len(world_update_events) == 1
    assert events[-1] == "[DONE]"

    # The world_update event carries the DM hint shape the frontend expects.
    hint = world_update_events[0]["data"]
    assert hint["world"]["tension"] == 4
    assert hint["characters"][0]["name"] == "Kael"

    # The full token stream, concatenated, reconstructs the raw
    # response the Fact-Extractor saw.
    full = "".join(e["content"] for e in token_events)
    assert "<world_update>" in full
    assert "crackles" in full


def test_stream_dispatches_fact_extractor_output_and_updates_session(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    session_id = VALID_SESSION_ID_2
    _prime_session(tmp_data_dir, session_id)

    fake_openai.chat.completions.set_stream_tokens(_dm_stream_tokens())

    response = client.post(
        "/api/stream", json={"action": "scout ahead", "sessionId": session_id}
    )
    assert response.status_code == 200

    # Consume the streaming body so all generator code runs.
    _ = response.text

    # Two fs-manager dispatches: Fact-Extractor payload + session-file update.
    assert len(fake_dispatch_log) == 2

    fe_payload = fake_dispatch_log[0]["payload"]
    fe_targets = {u["target_file"] for u in fe_payload["updates"]}
    assert "data/state/core/world/state.json" in fe_targets
    assert "data/state/core/entities/kael.json" in fe_targets

    session_payload = fake_dispatch_log[1]["payload"]
    session_file = session_payload["updates"][0]["target_file"]
    assert session_file == f"data/state/core/sessions/{session_id}.json"
    # The session-file update must include the new turn.
    appended_turns = session_payload["updates"][0]["data"]["turns"]
    assert len(appended_turns) == 1
    assert appended_turns[0]["player_action"] == "scout ahead"

    # One git-sync commit for the turn. Per ADR 0001 Phase 1, every
    # successful stream turn must commit_snapshot after the session
    # write succeeds.
    assert len(fake_commit_log) == 1
    commit = fake_commit_log[0]
    assert commit["session_id"] == session_id
    assert commit["turn_number"] == 1  # first turn after the primed turn-0 session
    assert isinstance(commit["summary"], str)
    assert len(commit["summary"]) > 0


def test_stream_handles_empty_world_update_block_gracefully(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """If the DM emits no block, the world_update event is an empty
    dict and no Fact-Extractor dispatch happens. The session-file
    update still happens so the turn is recorded."""
    session_id = VALID_SESSION_ID_3
    _prime_session(tmp_data_dir, session_id)

    fake_openai.chat.completions.set_stream_tokens(
        ["A long ", "silence ", "follows."]
    )

    response = client.post(
        "/api/stream", json={"action": "wait", "sessionId": session_id}
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    world_updates = [e for e in events if isinstance(e, dict) and e.get("type") == "world_update"]
    assert len(world_updates) == 1
    assert world_updates[0]["data"] == {}

    # Only the session-file update dispatched — no Fact-Extractor payload.
    assert len(fake_dispatch_log) == 1
    target = fake_dispatch_log[0]["payload"]["updates"][0]["target_file"]
    assert "sessions" in target


def test_stream_passes_prior_turns_as_recent_context(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """Prior turns in the session file should show up in the DM's
    WorldContext.recent_turns. We verify by checking the messages
    the fake OpenAI receives."""
    session_id = VALID_SESSION_ID_4
    prior_turns = [
        {
            "turn_number": 0,
            "player_action": "[Session Start]",
            "narrative": "A dark tavern awaits.",
        },
        {
            "turn_number": 1,
            "player_action": "order a drink",
            "narrative": "The barkeep slides a cup to you.",
        },
    ]
    _prime_session(tmp_data_dir, session_id, turns=prior_turns)

    fake_openai.chat.completions.set_stream_tokens(["Next turn."])

    client.post(
        "/api/stream", json={"action": "look around", "sessionId": session_id}
    )

    # One create call to OpenAI — inspect its messages.
    assert len(fake_openai.chat.completions.calls) == 1
    call = fake_openai.chat.completions.calls[0]
    user_message = call["messages"][1]["content"]
    assert "order a drink" in user_message
    assert "barkeep slides a cup" in user_message
    assert "RECENT TURNS" in user_message


def test_stream_error_emits_error_event_then_done(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir, monkeypatch
):
    """If the LLM call raises, the generator yields an error SSE
    event followed by [DONE]. The session file is not updated
    (the turn never really happened), and no git-sync commit fires
    because there's nothing to commit."""
    session_id = VALID_SESSION_ID_5
    _prime_session(tmp_data_dir, session_id)

    # Force the stream iterator to raise.
    def boom(**kwargs):
        raise RuntimeError("simulated LLM failure")

    monkeypatch.setattr(fake_openai.chat.completions, "create", boom)

    response = client.post(
        "/api/stream", json={"action": "break things", "sessionId": session_id}
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    assert any(
        isinstance(e, dict) and e.get("type") == "error" and "simulated" in e["content"]
        for e in events
    )
    assert events[-1] == "[DONE]"
    # No dispatches on the error path — neither fs-manager nor git-sync.
    assert fake_dispatch_log == []
    assert fake_commit_log == []


# ── path traversal defense ──────────────────────────────────────────


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../lore/core/codex/some_file",
        "../../etc/passwd",
        "abc-123",
        "notauuidatall",
    ],
)
def test_stream_rejects_malicious_session_id(
    client, fake_openai, fake_dispatch_log, malicious_id
):
    """A non-UUID session_id must be rejected as 'not found' rather
    than building a filesystem path that escapes the sessions
    directory. The caller never sees any file contents."""
    response = client.post(
        "/api/stream", json={"action": "look around", "sessionId": malicious_id}
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()
    # No OpenAI call, no dispatches.
    assert fake_openai.chat.completions.calls == []
    assert fake_dispatch_log == []


# ── session write failure during streaming ─────────────────────────


def test_stream_emits_error_when_session_write_fails(
    app, fake_openai, fake_commit_log, tmp_data_dir, monkeypatch
):
    """If the session-file append fails mid-stream, the handler
    must surface a structured error event before [DONE] so the
    frontend can show a toast. Narrative tokens have already
    streamed to the player — we don't roll those back.

    Also verifies that commit_snapshot STILL fires before the
    error path — the apply_world_update dispatch succeeded and
    wrote real state mutations to disk, so those must make it
    into the git audit trail even when the session-file append
    fails."""
    import engine
    import engine.dispatch.fs_manager as dispatcher_module
    from fastapi.testclient import TestClient

    session_id = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"
    _prime_session(tmp_data_dir, session_id)

    fake_openai.chat.completions.set_stream_tokens(_dm_stream_tokens())

    # Fail the *second* dispatch (the session-file append).
    # The first dispatch (Fact-Extractor payload) still succeeds.
    calls = {"count": 0}

    def failing_dispatch(config, payload, *, client=None, timeout=30.0):
        calls["count"] += 1
        if calls["count"] == 1:
            return engine.DispatchResult(ok=True, status_code=200, body={"success": True})
        return engine.DispatchResult(
            ok=False,
            status_code=503,
            body={"detail": "fs-manager offline"},
            error="fs-manager rejected payload (503): fs-manager offline",
        )

    monkeypatch.setattr(dispatcher_module, "apply_world_update", failing_dispatch)
    monkeypatch.setattr(engine, "apply_world_update", failing_dispatch)

    client = TestClient(app)
    response = client.post(
        "/api/stream", json={"action": "scout", "sessionId": session_id}
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    # Tokens streamed successfully; the error only surfaces after
    # the session-write attempt fails.
    token_events = [e for e in events if isinstance(e, dict) and e.get("type") == "token"]
    assert len(token_events) >= 1

    error_events = [e for e in events if isinstance(e, dict) and e.get("type") == "error"]
    assert len(error_events) == 1
    assert "Failed to save turn to session" in error_events[0]["content"]
    assert "fs-manager offline" in error_events[0]["content"]

    # Stream still closes with [DONE] so the frontend's useDMStream
    # handler finishes cleanly.
    assert events[-1] == "[DONE]"

    # Both dispatches were attempted; only the second failed.
    assert calls["count"] == 2

    # Critical: commit_snapshot MUST still fire even though the
    # session write failed. The world state from the successful
    # first dispatch is on disk; it must land in git history
    # despite the partial failure. Otherwise we introduce a
    # silent audit gap exactly where Phase 1 is trying to close one.
    assert len(fake_commit_log) == 1
    assert fake_commit_log[0]["session_id"] == session_id
    assert fake_commit_log[0]["turn_number"] == 1

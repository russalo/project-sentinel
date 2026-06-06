"""Route-level enforcement of the ADR 0003 access layer.

Token enforcement and rate limits are opt-in: the default ``test_settings`` has
them off, so every *other* backend test exercises the anonymous flow unchanged.
Here we flip them on (via ``dataclasses.replace`` on ``app.state.settings`` —
handlers read settings per-request, so this takes effect immediately) and assert
the gate bites: 401 without a token, 403 with a wrong one, 200 with the right
one, and 429 past a configured limit.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from backend.auth import world_token

SECRET = "route-test-secret"
WORLD_ID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _enforce(client, **overrides):
    client.app.state.settings = replace(client.app.state.settings, **overrides)


def _token(world_id=WORLD_ID, secret=SECRET):
    return world_token.mint(world_id, secret=secret, ttl_seconds=3600)


def _seed_session(data_dir, *, session_id=SESSION_ID, world_id=WORLD_ID):
    sessions = data_dir / "state" / "core" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_id": world_id,
                "world_name": "Gatekeep",
                "started_at": "2026-06-03T00:00:00+00:00",
                "active": True,
                "turns": [
                    {
                        "turn_number": 0,
                        "player_action": "[start]",
                        "narrative": "Begin.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _opening_response() -> str:
    return (
        "An opening unfolds. "
        '<world_update>{"world": {"currentLocation": "Gate", "tension": 1}}</world_update>'
    )


# ── Token issuance on /session/new ───────────────────────────────────


def test_session_new_issues_verifiable_token_when_enforced(client, fake_openai):
    _enforce(client, session_token_secret=SECRET)
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    r = client.post("/api/session/new", json={"worldName": "W"})
    assert r.status_code == 200
    data = r.json()
    assert data["sessionToken"]
    assert world_token.verify(data["sessionToken"], data["worldId"], secret=SECRET)


def test_session_new_omits_token_when_unenforced(client, fake_openai):
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    r = client.post("/api/session/new", json={"worldName": "W"})
    assert r.status_code == 200
    assert r.json()["sessionToken"] is None


# ── GET /api/world/{id} enforcement ──────────────────────────────────


def test_get_world_401_without_token_when_enforced(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    assert client.get(f"/api/world/{WORLD_ID}").status_code == 401


def test_get_world_403_with_wrong_token(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    r = client.get(
        f"/api/world/{WORLD_ID}",
        headers={
            "X-Sentinel-World-Token": _token(
                world_id="00000000-0000-0000-0000-000000000000"
            )
        },
    )
    assert r.status_code == 403


def test_get_world_200_with_correct_token(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    r = client.get(
        f"/api/world/{WORLD_ID}", headers={"X-Sentinel-World-Token": _token()}
    )
    assert r.status_code == 200
    assert r.json()["worldId"] == WORLD_ID


def test_get_world_anonymous_when_unenforced(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    assert client.get(f"/api/world/{WORLD_ID}").status_code == 200


# ── DELETE /api/world/{id} enforcement ───────────────────────────────


def test_delete_world_401_without_token_when_enforced(
    client, tmp_data_dir, fake_teardown_log
):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    assert client.delete(f"/api/world/{WORLD_ID}").status_code == 401
    assert fake_teardown_log == []  # never reached the teardown


def test_delete_world_200_with_correct_token(client, tmp_data_dir, fake_teardown_log):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    r = client.delete(
        f"/api/world/{WORLD_ID}", headers={"X-Sentinel-World-Token": _token()}
    )
    assert r.status_code == 200
    assert len(fake_teardown_log) == 1


# ── POST /api/stream enforcement ─────────────────────────────────────


def test_stream_401_without_token_when_enforced(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    r = client.post("/api/stream", json={"action": "look", "sessionId": SESSION_ID})
    assert r.status_code == 401


def test_stream_200_with_correct_token(client, tmp_data_dir, fake_openai):
    _seed_session(tmp_data_dir)
    _enforce(client, session_token_secret=SECRET)
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    r = client.post(
        "/api/stream",
        json={"action": "look", "sessionId": SESSION_ID},
        headers={"X-Sentinel-World-Token": _token()},
    )
    assert r.status_code == 200


# ── Rate limits ──────────────────────────────────────────────────────


def test_session_create_rate_limit(client, fake_openai):
    _enforce(client, rl_session_create_per_hour=1)
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    assert client.post("/api/session/new", json={"worldName": "W"}).status_code == 200
    assert client.post("/api/session/new", json={"worldName": "W"}).status_code == 429


def test_global_llm_ceiling(client, fake_openai):
    _enforce(client, llm_daily_ceiling=1)
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    assert client.post("/api/session/new", json={"worldName": "W"}).status_code == 200
    assert client.post("/api/session/new", json={"worldName": "W"}).status_code == 429


def test_stream_per_world_rate_limit(client, tmp_data_dir, fake_openai):
    _seed_session(tmp_data_dir)
    _enforce(client, rl_stream_per_minute=1)
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    body = {"action": "look", "sessionId": SESSION_ID}
    assert client.post("/api/stream", json=body).status_code == 200
    assert client.post("/api/stream", json=body).status_code == 429


# ── Concurrency cap (ADR 0003 access dim #3) ─────────────────────────


def test_stream_returns_503_at_concurrency_cap(client, tmp_data_dir, fake_openai):
    """When the slot semaphore is exhausted, /api/stream returns 503 + Retry-After.

    Setup: hold the only slot manually (simulating an in-flight stream that
    hasn't completed yet), then verify a fresh request is rejected. This
    isolates the cap-bite from the streaming machinery — actual generator
    teardown is covered by the unit tests on StreamSlotLimiter.
    """
    from backend.concurrency import StreamSlotLimiter

    _seed_session(tmp_data_dir)
    # Recreate the app's stream_limiter with cap=1 (mirrors what main.py
    # would do if SENTINEL_MAX_CONCURRENT_STREAMS=1 was set on startup).
    client.app.state.stream_limiter = StreamSlotLimiter(1)
    # Hold the slot — represents an in-flight stream we haven't released.
    assert client.app.state.stream_limiter.try_acquire() is True
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    body = {"action": "look", "sessionId": SESSION_ID}
    r = client.post("/api/stream", json=body)
    assert r.status_code == 503
    assert r.headers.get("retry-after") == "5"
    assert "capacity" in r.json()["detail"].lower()


def test_stream_releases_slot_after_normal_completion(
    client, tmp_data_dir, fake_openai
):
    """Slot is freed after the SSE response is consumed end-to-end.

    Verifies the `_SlotReleasingIterator.__next__` release-on-StopIteration
    path fires when the client iterates to completion. With cap=1, a second
    sequential request must succeed (not 503).
    """
    from backend.concurrency import StreamSlotLimiter

    _seed_session(tmp_data_dir)
    client.app.state.stream_limiter = StreamSlotLimiter(1)
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    body = {"action": "look", "sessionId": SESSION_ID}
    # First request: consume the SSE stream fully (drains the iterator,
    # fires release).
    r1 = client.post("/api/stream", json=body)
    assert r1.status_code == 200
    _ = r1.text  # force-drain
    # Second request: the slot should be available again
    r2 = client.post("/api/stream", json=body)
    assert r2.status_code == 200


def test_stream_503_does_not_burn_llm_budget(client, tmp_data_dir, fake_openai):
    """Capacity-rejected requests must NOT consume the daily LLM ceiling.

    Regression test for codex P1 on PR #106: enforce_llm_ceiling() was being
    called BEFORE the concurrency-acquire, so a burst of over-capacity attempts
    would each bump the daily counter without making any LLM call, eventually
    starving real turns with 429s. The fix moved the acquire BEFORE the
    ceiling check.

    Setup: cap=1 (slot held externally) + daily_ceiling=1. Send 5 streams.
    All should 503, NOT count against the ceiling. Then release + send a 6th —
    should succeed because the ceiling counter is still at 0.
    """
    from backend.concurrency import StreamSlotLimiter

    _seed_session(tmp_data_dir)
    _enforce(client, llm_daily_ceiling=1)
    client.app.state.stream_limiter = StreamSlotLimiter(1)
    # Hold the slot so all attempts 503
    assert client.app.state.stream_limiter.try_acquire() is True
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    body = {"action": "look", "sessionId": SESSION_ID}
    # 5 attempts — all should 503 (capacity), NOT 429 (ceiling)
    for _ in range(5):
        r = client.post("/api/stream", json=body)
        assert r.status_code == 503, f"expected 503, got {r.status_code}"
    # Release + one more — must succeed because the ceiling counter wasn't burned
    client.app.state.stream_limiter.release()
    r = client.post("/api/stream", json=body)
    assert r.status_code == 200, (
        f"expected 200 after release (ceiling untouched), got {r.status_code}"
    )


def test_stream_releases_slot_when_rate_limit_raises(client, tmp_data_dir, fake_openai):
    """If rate-limit/ceiling raises after the slot is acquired, the slot is freed.

    Setup: cap=1, per-world rate limit = 1 (will reject the second attempt).
    First request takes the slot AND the rate-limit window. Second request
    acquires the slot, then 429s on the rate limit. The except branch in the
    handler must release the slot so a third request can attempt.
    """
    from backend.concurrency import StreamSlotLimiter

    _seed_session(tmp_data_dir)
    _enforce(client, rl_stream_per_minute=1)
    client.app.state.stream_limiter = StreamSlotLimiter(1)
    fake_openai.chat.completions.set_stream_tokens(["A ", "turn."])
    body = {"action": "look", "sessionId": SESSION_ID}
    # First: succeeds (slot used + drained immediately by TestClient)
    r1 = client.post("/api/stream", json=body)
    assert r1.status_code == 200
    _ = r1.text  # force-drain
    # Second: acquires slot, then 429s on rate-limit. Slot MUST be released.
    r2 = client.post("/api/stream", json=body)
    assert r2.status_code == 429
    # If the slot had been leaked, this would be 503; should be 429 again.
    r3 = client.post("/api/stream", json=body)
    assert r3.status_code == 429


def test_slot_releasing_iterator_release_on_close():
    """Direct unit test of `_SlotReleasingIterator.close()` — covers the
    Starlette-teardown path (and incidentally the GEN_CREATED never-iterated
    edge case, since we call close() without ever calling next()).
    """
    from backend.concurrency import StreamSlotLimiter
    from backend.routes.stream import _SlotReleasingIterator

    lim = StreamSlotLimiter(1)
    assert lim.try_acquire() is True  # cap reached
    assert lim.try_acquire() is False

    def gen():
        yield 1
        yield 2

    it = _SlotReleasingIterator(gen(), lim)
    # Never iterate — go straight to close (simulates client disconnect
    # BEFORE first chunk read; the GEN_CREATED case Gemini flagged).
    it.close()
    # Slot must now be available
    assert lim.try_acquire() is True


def test_slot_releasing_iterator_release_on_exception():
    """Mid-stream exception during iteration releases the slot."""
    from backend.concurrency import StreamSlotLimiter
    from backend.routes.stream import _SlotReleasingIterator

    lim = StreamSlotLimiter(1)
    assert lim.try_acquire() is True

    def gen():
        yield "first"
        raise RuntimeError("planned mid-stream failure")

    it = _SlotReleasingIterator(gen(), lim)
    assert next(it) == "first"
    with pytest.raises(RuntimeError, match="planned"):
        next(it)
    # Slot released by __next__'s except path
    assert lim.try_acquire() is True


def test_slot_releasing_iterator_release_is_idempotent():
    """Multiple release paths (close + __del__ + StopIteration) must not
    over-release. The internal `_released` flag is the first line of defense;
    StreamSlotLimiter's own double-release tolerance is the second.
    """
    from backend.concurrency import StreamSlotLimiter
    from backend.routes.stream import _SlotReleasingIterator

    lim = StreamSlotLimiter(2)
    assert lim.try_acquire() is True  # use one slot
    # Now there is exactly 1 slot free
    assert lim.try_acquire() is True  # use the second
    # Cap exhausted; we now have to release one to make room for the iterator's
    # slot below.
    lim.release()
    assert lim.try_acquire() is True  # the iterator's slot

    def gen():
        yield 1

    it = _SlotReleasingIterator(gen(), lim)
    # Drain to completion (StopIteration releases)
    assert list(it) == [1]
    # Then close (would release again if not idempotent)
    it.close()
    # Then trigger __del__ via gc (would release a third time if not idempotent)
    import gc

    del it
    gc.collect()
    # If release was triple-fired, the cap counter would be corrupted.
    # We held 2 slots total + 1 in the iterator = 3 acquires; we released
    # 1 manually + 1 via iterator. Net: 1 slot still held. So one more
    # try_acquire should succeed, the next should fail.
    assert lim.try_acquire() is True
    assert lim.try_acquire() is False

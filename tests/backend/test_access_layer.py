"""Route-level enforcement of the ADR 0003 access layer.

Token enforcement and rate limits are opt-in: the default ``test_settings`` has
them off, so every *other* backend test exercises the anonymous flow unchanged.
Here we flip them on (via ``dataclasses.replace`` on ``app.state.settings`` —
handlers read settings per-request, so this takes effect immediately) and assert
the gate bites: 401 without a token, 403 with a wrong one, 200 with the right
one, and 429 past a configured limit.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from backend.auth import world_token
from backend.auth.access import extract_basic_auth_user

SECRET = "route-test-secret"
WORLD_ID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _enforce(client, **overrides):
    client.app.state.settings = replace(client.app.state.settings, **overrides)


def _token(world_id=WORLD_ID, secret=SECRET, username=None):
    return world_token.mint(
        world_id, secret=secret, ttl_seconds=3600, username=username
    )


def _basic_auth(username: str, password: str = "x") -> dict[str, str]:
    raw = f"{username}:{password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}


def _seed_session(
    data_dir,
    *,
    session_id=SESSION_ID,
    world_id=WORLD_ID,
    creator_username: str = "",
):
    sessions = data_dir / "state" / "core" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    payload = {
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
    if creator_username:
        payload["creator_username"] = creator_username
    (sessions / f"{session_id}.json").write_text(
        json.dumps(payload),
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


# ── Per-tester reauth (2026-06-08) ──────────────────────────────────


# ── extract_basic_auth_user: unit-level (no app needed) ─────────────


def _req(headers: dict[str, str] | None = None):
    """Lightweight stand-in for a FastAPI Request with just ``.headers``."""
    r = MagicMock()
    r.headers = headers or {}
    return r


def test_extract_basic_auth_user_happy_path():
    raw = base64.b64encode(b"russell:hunter2").decode("ascii")
    assert (
        extract_basic_auth_user(_req({"Authorization": f"Basic {raw}"})) == "russell"
    )


def test_extract_basic_auth_user_no_header_returns_none():
    assert extract_basic_auth_user(_req()) is None


def test_extract_basic_auth_user_wrong_scheme_returns_none():
    raw = base64.b64encode(b"russell:hunter2").decode("ascii")
    assert extract_basic_auth_user(_req({"Authorization": f"Bearer {raw}"})) is None


def test_extract_basic_auth_user_malformed_base64_returns_none():
    assert (
        extract_basic_auth_user(_req({"Authorization": "Basic !!!not-base64!!!"}))
        is None
    )


def test_extract_basic_auth_user_no_colon_returns_none():
    raw = base64.b64encode(b"nocolon").decode("ascii")
    assert extract_basic_auth_user(_req({"Authorization": f"Basic {raw}"})) is None


def test_extract_basic_auth_user_empty_username_returns_none():
    raw = base64.b64encode(b":just-a-password").decode("ascii")
    assert extract_basic_auth_user(_req({"Authorization": f"Basic {raw}"})) is None


def test_extract_basic_auth_user_username_with_dots_passes_through():
    # Free-form usernames may contain dots (e.g. "alpha.tester.3"). Confirm
    # they round-trip through the extractor unchanged — they're then bound
    # into the world-token's HMAC payload + parsed back on verify (covered
    # by the world_token tests' username-with-dots case).
    raw = base64.b64encode(b"alpha.tester.3:pw").decode("ascii")
    assert (
        extract_basic_auth_user(_req({"Authorization": f"Basic {raw}"}))
        == "alpha.tester.3"
    )


def test_extract_basic_auth_user_handles_unicode_username():
    raw = base64.b64encode("björk:hunter2".encode("utf-8")).decode("ascii")
    assert (
        extract_basic_auth_user(_req({"Authorization": f"Basic {raw}"})) == "björk"
    )


def test_extract_basic_auth_user_lowercase_basic_scheme():
    raw = base64.b64encode(b"russell:x").decode("ascii")
    # The scheme token is case-insensitive per RFC 7617; the extractor
    # normalizes via .lower().
    assert (
        extract_basic_auth_user(_req({"Authorization": f"basic {raw}"})) == "russell"
    )


# ── /session/new captures creator_username + binds the token ────────


def test_session_new_captures_creator_username_from_basic_auth(
    client, fake_openai, fake_dispatch_log
):
    """When the request carries basic_auth, the username is captured on the
    session record AND the issued token is bound to that username — so
    verify() against a different username will fail.
    """
    _enforce(client, session_token_secret=SECRET)
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    r = client.post(
        "/api/session/new",
        json={"worldName": "W"},
        headers=_basic_auth("russell"),
    )
    assert r.status_code == 200
    body = r.json()
    token = body["sessionToken"]
    world_id = body["worldId"]

    # The token verifies (with no out-of-band username — verify() reads it
    # from the wire shape).
    assert world_token.verify(token, world_id, secret=SECRET) is True

    # And it's the 3-part (username-bound) wire shape — wire shape alone is
    # enough to assert; the HMAC binding is then proven by forging a
    # username-swap below.
    assert token.count(".") == 2  # exactly two top-level dots (3 segments)
    forged_other_user = ".".join(
        [
            token.split(".")[0],
            "someone-else",
            token.split(".")[2],
        ]
    )
    assert world_token.verify(forged_other_user, world_id, secret=SECRET) is False

    # The session payload dispatched to fs-manager carries creator_username
    # in the session JSON body, so /reauth can read it later.
    session_writes = [
        d
        for d in fake_dispatch_log
        if d["payload"]["updates"][0]["target_file"].endswith(".json")
        and "/sessions/" in d["payload"]["updates"][0]["target_file"]
    ]
    assert session_writes, "expected at least one session-file dispatch"
    data = session_writes[0]["payload"]["updates"][0]["data"]
    assert data.get("creator_username") == "russell"


def test_session_new_no_basic_auth_mints_legacy_unbound_token(
    client, fake_openai, fake_dispatch_log
):
    """No Authorization header → legacy 2-part token (creator_username='').

    This preserves the anonymous tailnet flow and the cohort-pre-cutover dev
    experience: the gate decides whether basic_auth is required, the backend
    just records what arrives.
    """
    _enforce(client, session_token_secret=SECRET)
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    r = client.post("/api/session/new", json={"worldName": "W"})  # no auth header
    assert r.status_code == 200
    token = r.json()["sessionToken"]
    # Legacy wire shape: 2 segments (1 dot).
    assert token.count(".") == 1

    session_writes = [
        d
        for d in fake_dispatch_log
        if d["payload"]["updates"][0]["target_file"].endswith(".json")
        and "/sessions/" in d["payload"]["updates"][0]["target_file"]
    ]
    assert session_writes
    data = session_writes[0]["payload"]["updates"][0]["data"]
    assert data.get("creator_username", "") == ""


# ── POST /api/world/{id}/reauth ──────────────────────────────────────


def test_reauth_404_when_enforcement_off(client, tmp_data_dir):
    """No secret configured → /reauth is meaningless and surfaces 404.

    The SPA only hits /reauth on a 401, which can't happen with enforcement
    off; defensive: respond 404 (no half-state "null token" response).
    """
    _seed_session(tmp_data_dir, creator_username="russell")
    r = client.post(f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("russell"))
    assert r.status_code == 404


def test_reauth_404_on_malformed_world_id(client, tmp_data_dir):
    _enforce(client, session_token_secret=SECRET)
    r = client.post("/api/world/not-a-uuid/reauth", headers=_basic_auth("russell"))
    assert r.status_code == 404


def test_reauth_404_on_unknown_world(client, tmp_data_dir):
    _enforce(client, session_token_secret=SECRET)
    unknown = "00000000-0000-0000-0000-000000000000"
    r = client.post(f"/api/world/{unknown}/reauth", headers=_basic_auth("russell"))
    assert r.status_code == 404


def test_reauth_401_without_basic_auth(client, tmp_data_dir):
    """Enforcement on but no Authorization header → 401 (parallel to
    enforce_world_token's missing-token semantics). The SPA shouldn't reach
    this in production — Caddy will require basic_auth before the request
    arrives — but the backend defends in depth.
    """
    _seed_session(tmp_data_dir, creator_username="russell")
    _enforce(client, session_token_secret=SECRET)
    assert client.post(f"/api/world/{WORLD_ID}/reauth").status_code == 401


def test_reauth_403_when_basic_auth_user_mismatches_creator(client, tmp_data_dir):
    """johnny tries to reauth a world russell created → 403."""
    _seed_session(tmp_data_dir, creator_username="russell")
    _enforce(client, session_token_secret=SECRET)
    r = client.post(f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("johnny"))
    assert r.status_code == 403


def test_reauth_happy_path_returns_bound_token(client, tmp_data_dir):
    """Matching basic_auth → fresh username-bound token that verifies."""
    _seed_session(tmp_data_dir, creator_username="russell")
    _enforce(client, session_token_secret=SECRET)
    r = client.post(f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("russell"))
    assert r.status_code == 200
    body = r.json()
    assert body["worldId"] == WORLD_ID
    token = body["token"]
    assert token
    # The new token verifies for this world (any wire shape is fine; verify
    # self-detects). And it's the 3-part bound shape — forging a different
    # username over the same MAC must fail.
    assert world_token.verify(token, WORLD_ID, secret=SECRET) is True
    assert token.count(".") == 2
    parts = token.split(".")
    forged = f"{parts[0]}.intruder.{parts[2]}"
    assert world_token.verify(forged, WORLD_ID, secret=SECRET) is False


def test_reauth_tofu_claims_legacy_world(client, tmp_data_dir, fake_dispatch_log):
    """A legacy world has creator_username='' on disk; the first reauth
    claims it for the requesting basic_auth user. We assert: (a) 200 + bound
    token returned, (b) a fs-manager dispatch happened that carries
    creator_username='russell' in the session payload (TOFU write).
    """
    _seed_session(tmp_data_dir, creator_username="")  # legacy world
    _enforce(client, session_token_secret=SECRET)
    r = client.post(f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("russell"))
    assert r.status_code == 200, r.text
    # TOFU write went through fs-manager (we capture every dispatch).
    session_writes = [
        d
        for d in fake_dispatch_log
        if d["payload"]["updates"][0]["target_file"].endswith(".json")
        and "/sessions/" in d["payload"]["updates"][0]["target_file"]
    ]
    assert session_writes, "TOFU should have dispatched a session write"
    data = session_writes[-1]["payload"]["updates"][0]["data"]
    assert data["creator_username"] == "russell"


def test_reauth_tofu_only_first_caller_claims(client, tmp_data_dir):
    """After a TOFU claim, a second basic_auth user is 403'd (no double-claim).

    Note: this test relies on the fake dispatch log NOT actually persisting
    the claim to disk — so the second call still sees the legacy world. The
    real cross-process locking that prevents concurrent double-claim lives
    one layer down (per-world filelock in fs-manager / git-sync); here we
    just confirm the handler's *logic* refuses a mismatching second user
    when the on-disk creator_username is already set.
    """
    # Seed a world that already has a TOFU'd creator.
    _seed_session(tmp_data_dir, creator_username="russell")
    _enforce(client, session_token_secret=SECRET)
    # Russell's reauth succeeds (idempotent re-mint).
    assert (
        client.post(
            f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("russell")
        ).status_code
        == 200
    )
    # Johnny tries the same world → 403; no overwrite.
    assert (
        client.post(
            f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("johnny")
        ).status_code
        == 403
    )


def test_reauth_new_token_unlocks_world_get(client, tmp_data_dir):
    """End-to-end: a stale-token client gets 401 on /world/{id}, calls
    /reauth, then retries /world/{id} with the fresh token → 200.

    This is the production recovery flow in miniature: the SPA's
    useWorldHydration hook will do exactly this on 401.
    """
    _seed_session(tmp_data_dir, creator_username="russell")
    _enforce(client, session_token_secret=SECRET)
    # 1. No token at all → 401
    r1 = client.get(f"/api/world/{WORLD_ID}")
    assert r1.status_code == 401
    # 2. /reauth with basic_auth → returns a fresh bound token
    r2 = client.post(
        f"/api/world/{WORLD_ID}/reauth", headers=_basic_auth("russell")
    )
    assert r2.status_code == 200
    fresh = r2.json()["token"]
    # 3. Retry /world/{id} with the fresh token → 200
    r3 = client.get(
        f"/api/world/{WORLD_ID}",
        headers={"X-Sentinel-World-Token": fresh},
    )
    assert r3.status_code == 200, r3.text

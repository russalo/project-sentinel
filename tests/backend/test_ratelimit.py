"""Unit tests for the in-process rate limiter (ADR 0003 Slice B).

A fake monotonic clock makes window behavior deterministic. Covers: the limit
bites at N+1, windows reset after the period, ``limit <= 0`` disables, the
global LLM ceiling, the 429 raised by ``enforce``, and trusted-proxy
X-Forwarded-For handling (the red-team #3 spoofing fix).
"""

import pytest
from fastapi import HTTPException

from backend.ratelimit import (
    GLOBAL_LLM_KEY,
    RateLimiter,
    client_ip,
    enforce,
    enforce_llm_ceiling,
)


class _Clock:
    """Mutable monotonic stand-in: tests advance ``t`` explicitly."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_allows_up_to_limit_then_blocks():
    clock = _Clock()
    rl = RateLimiter(now=clock)
    assert rl.allow("k", 2, 60) is True
    assert rl.allow("k", 2, 60) is True
    assert rl.allow("k", 2, 60) is False  # third in-window hit blocked


def test_window_resets_after_period():
    clock = _Clock()
    rl = RateLimiter(now=clock)
    assert rl.allow("k", 1, 60) is True
    assert rl.allow("k", 1, 60) is False
    clock.t = 61  # past the window
    assert rl.allow("k", 1, 60) is True


def test_expired_windows_are_swept_to_bound_memory():
    # The dict must not grow without bound as new keys appear over time. The
    # sweep runs every _SWEEP_EVERY ops; after it, entries whose period has
    # elapsed are evicted.
    clock = _Clock()
    rl = RateLimiter(now=clock)
    n = RateLimiter._SWEEP_EVERY
    # n distinct keys (60s window) at t=0 — the loop ends exactly on a sweep
    # boundary, but nothing has expired yet, so all n remain.
    for i in range(n):
        rl.allow(f"k{i}", 1, 60)
    assert len(rl._windows) == n
    # Advance past the window; n more ops reach the next sweep boundary, which
    # evicts all the now-expired k* entries (the fresh key, created at t=61,
    # survives).
    clock.t = 61
    for _ in range(n):
        rl.allow("fresh", 1, 60)
    assert "fresh" in rl._windows
    assert len(rl._windows) == 1


def test_non_positive_limit_disables():
    rl = RateLimiter(now=_Clock())
    for _ in range(100):
        assert rl.allow("k", 0, 60) is True
        assert rl.allow("k", -5, 60) is True


def test_keys_are_independent():
    clock = _Clock()
    rl = RateLimiter(now=clock)
    assert rl.allow("a", 1, 60) is True
    assert rl.allow("b", 1, 60) is True  # different key, own window
    assert rl.allow("a", 1, 60) is False


def test_enforce_raises_429_when_exceeded():
    rl = RateLimiter(now=_Clock())
    enforce(rl, "k", 1, 60, detail="nope")  # first allowed
    with pytest.raises(HTTPException) as exc:
        enforce(rl, "k", 1, 60, detail="nope")
    assert exc.value.status_code == 429
    assert exc.value.detail == "nope"


def test_enforce_llm_ceiling_uses_global_key_and_day_window():
    clock = _Clock()
    rl = RateLimiter(now=clock)
    enforce_llm_ceiling(rl, 1)
    with pytest.raises(HTTPException) as exc:
        enforce_llm_ceiling(rl, 1)
    assert exc.value.status_code == 429
    # Disabled when ceiling <= 0, even after the counter was tripped above.
    enforce_llm_ceiling(rl, 0)
    # The counter lives under the shared global key.
    assert GLOBAL_LLM_KEY in rl._windows


def test_enforce_llm_ceiling_resets_next_day():
    clock = _Clock()
    rl = RateLimiter(now=clock)
    enforce_llm_ceiling(rl, 1)
    with pytest.raises(HTTPException):
        enforce_llm_ceiling(rl, 1)
    clock.t = 24 * 60 * 60 + 1
    enforce_llm_ceiling(rl, 1)  # new day, allowed again


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, headers=None, host="10.0.0.9"):
        self.headers = headers or {}
        self.client = _FakeClient(host) if host else None


def test_client_ip_ignores_xff_without_a_trusted_proxy():
    # Default (trusted_proxy_hops=0, no proxy in front): X-Forwarded-For is
    # client-controlled and MUST be ignored — use the socket peer. This is the
    # red-team #3 fix: an attacker can't rotate XFF to dodge the per-IP bucket.
    req = _FakeRequest(
        headers={"x-forwarded-for": "203.0.113.7, 70.0.0.1"}, host="10.0.0.9"
    )
    assert client_ip(req) == "10.0.0.9"


def test_client_ip_uses_nth_hop_from_right_behind_trusted_proxies():
    req = _FakeRequest(
        headers={"x-forwarded-for": "203.0.113.7, 70.0.0.1, 198.51.100.2"}
    )
    # One trusted proxy (e.g. Caddy) → the hop it appended (rightmost).
    assert client_ip(req, trusted_proxy_hops=1) == "198.51.100.2"
    # Two trusted proxies → the second hop from the right.
    assert client_ip(req, trusted_proxy_hops=2) == "70.0.0.1"


def test_client_ip_spoofed_leftmost_xff_cannot_move_the_key():
    # With one trusted proxy, prepending fake hops on the left changes nothing —
    # the trustworthy hop is the one the proxy appended (rightmost).
    real = _FakeRequest(headers={"x-forwarded-for": "1.1.1.1"}, host="127.0.0.1")
    spoofed = _FakeRequest(
        headers={"x-forwarded-for": "9.9.9.9, 8.8.8.8, 1.1.1.1"}, host="127.0.0.1"
    )
    assert client_ip(real, trusted_proxy_hops=1) == "1.1.1.1"
    assert client_ip(spoofed, trusted_proxy_hops=1) == "1.1.1.1"  # spoof ineffective


def test_client_ip_falls_back_to_peer_when_too_few_hops():
    # Expect 2 trusted hops but only 1 present → degraded-but-safe: socket peer.
    req = _FakeRequest(headers={"x-forwarded-for": "1.1.1.1"}, host="10.0.0.9")
    assert client_ip(req, trusted_proxy_hops=2) == "10.0.0.9"


def test_client_ip_falls_back_to_peer():
    assert client_ip(_FakeRequest(host="10.0.0.9")) == "10.0.0.9"


def test_client_ip_unknown_when_no_peer():
    assert client_ip(_FakeRequest(headers={}, host=None)) == "unknown"

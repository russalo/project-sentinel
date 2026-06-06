"""Unit tests for the stream-slot limiter (ADR 0003 access layer dim #3).

Covers: disabled (max=0) is unbounded; the cap bites at N+1; release restores
capacity; context-manager release on success + on exception; double-release
doesn't crash; ``ValueError`` on negative max; threaded race — N threads can
hold simultaneously, N+1 fails deterministically.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.concurrency import StreamSlotLimiter


# ── construction ───────────────────────────────────────────────────────


def test_zero_means_disabled():
    """max_streams=0 → limiter is a no-op (matches the SENTINEL_RL_* convention)."""
    lim = StreamSlotLimiter(0)
    assert lim.max_streams == 0
    assert lim.enabled is False
    # Many acquires in a row all succeed
    for _ in range(50):
        assert lim.try_acquire() is True


def test_negative_rejected():
    """Negative caps are a config error, not a quiet-disable."""
    with pytest.raises(ValueError):
        StreamSlotLimiter(-1)


def test_positive_enables():
    lim = StreamSlotLimiter(3)
    assert lim.max_streams == 3
    assert lim.enabled is True


# ── cap behavior ───────────────────────────────────────────────────────


def test_cap_bites_at_n_plus_one():
    """N=3: three acquires succeed, fourth fails."""
    lim = StreamSlotLimiter(3)
    assert lim.try_acquire() is True
    assert lim.try_acquire() is True
    assert lim.try_acquire() is True
    assert lim.try_acquire() is False  # cap


def test_release_restores_capacity():
    lim = StreamSlotLimiter(1)
    assert lim.try_acquire() is True
    assert lim.try_acquire() is False  # at cap
    lim.release()
    assert lim.try_acquire() is True  # capacity restored


def test_release_when_disabled_is_safe():
    """Release on disabled limiter is a no-op, not a crash."""
    lim = StreamSlotLimiter(0)
    lim.release()  # must not raise
    lim.release()  # double-release also fine on disabled


# ── double-release defense ─────────────────────────────────────────────


def test_double_release_does_not_crash():
    """A try/finally bug shouldn't 500 the route.

    BoundedSemaphore.release() raises ValueError on excess; we catch + log.
    The cap remains intact (this is the right failure shape).
    """
    lim = StreamSlotLimiter(2)
    assert lim.try_acquire() is True
    lim.release()
    lim.release()  # excess — caught + logged, does NOT raise
    # Cap still holds at 2:
    assert lim.try_acquire() is True
    assert lim.try_acquire() is True
    assert lim.try_acquire() is False


# ── context manager ────────────────────────────────────────────────────


def test_slot_context_manager_success_releases():
    lim = StreamSlotLimiter(1)
    with lim.slot() as acquired:
        assert acquired is True
        # While inside, cap is reached
        assert lim.try_acquire() is False
    # After exit, cap freed
    assert lim.try_acquire() is True


def test_slot_context_manager_exception_releases():
    """Release fires even if the with-body raises (try/finally semantics)."""
    lim = StreamSlotLimiter(1)
    with pytest.raises(RuntimeError, match="planned"):
        with lim.slot() as acquired:
            assert acquired is True
            raise RuntimeError("planned")
    # Slot must be released despite the exception
    assert lim.try_acquire() is True


def test_slot_context_manager_at_cap_does_not_release():
    """If acquire failed, no spurious release on exit (would corrupt the cap)."""
    lim = StreamSlotLimiter(1)
    lim.try_acquire()  # hold the only slot
    with lim.slot() as acquired:
        assert acquired is False  # didn't get one
    # The previously-held slot is STILL held; cap is still full
    assert lim.try_acquire() is False


def test_slot_context_manager_when_disabled_always_yields_true():
    lim = StreamSlotLimiter(0)
    for _ in range(50):
        with lim.slot() as acquired:
            assert acquired is True


# ── threading race ─────────────────────────────────────────────────────


def test_concurrent_acquires_exactly_n_succeed():
    """N=5, 10 threads racing — exactly 5 win, 5 lose.

    Verifies the BoundedSemaphore is the real mutual-exclusion primitive,
    not just an accidental serial-test artifact.
    """
    lim = StreamSlotLimiter(5)
    barrier = threading.Barrier(10)
    results: list[bool] = []
    results_lock = threading.Lock()

    def attempt():
        barrier.wait(timeout=2)  # release all 10 at once
        got = lim.try_acquire()
        with results_lock:
            results.append(got)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(attempt) for _ in range(10)]
        for f in futures:
            f.result(timeout=3)

    assert sum(results) == 5, f"expected exactly 5 acquires, got {sum(results)}"
    assert sum(1 for r in results if not r) == 5

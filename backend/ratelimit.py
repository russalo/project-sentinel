"""In-process rate limiting + a global LLM-call ceiling (ADR 0003 Slice B).

A closed-beta backstop, not adversarial defense: per-IP world creation,
per-world turns, and a global daily LLM-call ceiling as a circuit breaker. The
backend is a single process, so in-memory fixed-window counters are sufficient
(the ADR says so explicitly). Each limit is **disabled when its configured
value is <= 0**, so local / tailnet / CI runs are unthrottled unless the
operator opts in — symmetric with token enforcement.

All counter state is guarded by one lock; FastAPI runs the sync route handlers
(and the SSE generator) in a thread pool, so concurrent turns can hit the
limiter at the same instant.
"""

from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Fixed-window per-key counter. Thread-safe; monotonic-clock based."""

    # Sweep expired windows every N allow() calls so the dict can't grow without
    # bound as new per-IP / per-world keys appear over a long-running process.
    _SWEEP_EVERY = 1024

    def __init__(self, *, now=time.monotonic) -> None:
        self._now = now
        self._lock = threading.Lock()
        # key -> [window_start, count, period_seconds]; period is stored so the
        # sweep knows when each entry has expired.
        self._windows: dict[str, list[float]] = {}
        self._ops = 0

    def allow(self, key: str, limit: int, period_seconds: float) -> bool:
        """Record a hit on ``key``; return ``False`` if it would exceed ``limit``
        within the current ``period_seconds`` window.

        ``limit <= 0`` disables the limit (always allowed, no state recorded).
        """
        if limit <= 0:
            return True
        with self._lock:
            t = self._now()
            self._ops += 1
            if self._ops % self._SWEEP_EVERY == 0:
                self._sweep(t)
            window = self._windows.get(key)
            if window is None or (t - window[0]) >= period_seconds:
                self._windows[key] = [t, 1, period_seconds]
                return True
            if window[1] < limit:
                window[1] += 1
                return True
            return False

    def _sweep(self, t: float) -> None:
        """Drop windows whose period has elapsed. Caller holds the lock."""
        expired = [k for k, w in self._windows.items() if (t - w[0]) >= w[2]]
        for k in expired:
            del self._windows[k]


def enforce(
    limiter: RateLimiter,
    key: str,
    limit: int,
    period_seconds: float,
    *,
    detail: str,
) -> None:
    """Raise 429 when ``key`` exceeds ``limit`` per window; no-op when disabled."""
    if not limiter.allow(key, limit, period_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


# Shared key for the single global LLM-call circuit breaker.
GLOBAL_LLM_KEY = "__global_llm_calls__"
_DAY_SECONDS = 24 * 60 * 60


def enforce_llm_ceiling(limiter: RateLimiter, daily_ceiling: int) -> None:
    """Raise 429 once the global daily LLM-call ceiling is hit (rolling 24h).

    Called by every route that triggers an LLM call (session create, turn).
    ``daily_ceiling <= 0`` disables it.
    """
    enforce(
        limiter,
        GLOBAL_LLM_KEY,
        daily_ceiling,
        _DAY_SECONDS,
        detail="daily LLM-call ceiling reached; try again later",
    )


def client_ip(request: Request) -> str:
    """Best-effort client IP, honoring a single ``X-Forwarded-For`` hop.

    Behind the Caddy edge the socket peer is ``127.0.0.1``; the real client is
    the first entry of ``X-Forwarded-For``. Not trusted for security (a direct
    caller can spoof the header) — only for coarse per-IP rate-limiting on the
    closed beta, where the edge gate is the actual access control.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"

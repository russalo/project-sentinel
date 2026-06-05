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
    """Raise 429 once the global daily LLM-call ceiling is hit.

    Uses a fixed 24h window (the limiter resets the counter the first call after
    the window elapses — not a rolling window). Called by every route that
    triggers an LLM call (session create, turn). ``daily_ceiling <= 0`` disables.
    """
    enforce(
        limiter,
        GLOBAL_LLM_KEY,
        daily_ceiling,
        _DAY_SECONDS,
        detail="daily LLM-call ceiling reached; try again later",
    )


def client_ip(request: Request, trusted_proxy_hops: int = 0) -> str:
    """Client IP for coarse per-IP rate-limiting.

    ``trusted_proxy_hops`` (``Settings.trusted_proxy_hops``) is the number of
    trusted reverse proxies in front of the app:

    - ``0`` (default, no proxy) — use the socket peer and **ignore**
      ``X-Forwarded-For``. A direct caller can spoof XFF, so trusting it would
      let an attacker rotate the header to dodge the per-IP bucket (the cost
      backstop) — exactly the bypass the red-team confirmed (2026-06-04).
    - ``N > 0`` — XFF is ``<client-claimed…>, <proxy1>, …, <proxyN>``; each proxy
      *appends* the IP that connected to it, so the trustworthy client is the
      **Nth entry from the right** (the hop the outermost trusted proxy — e.g.
      Caddy — appended). Everything to its left is client-supplied and ignored.
      Behind a single Caddy edge, set 1 → the rightmost hop.

    Falls back to the socket peer when XFF is missing or has fewer than
    ``trusted_proxy_hops`` entries (degraded-but-safe: over-limits, never
    under-limits).

    Requires uvicorn to run with ``--no-proxy-headers`` (see the systemd unit /
    justfile): its default proxy-headers handling rewrites ``request.client`` from
    the *leftmost* (spoofable) XFF hop, which would defeat this — the app must own
    client resolution.
    """
    if trusted_proxy_hops > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            if len(hops) >= trusted_proxy_hops:
                return hops[-trusted_proxy_hops]
    return request.client.host if request.client else "unknown"

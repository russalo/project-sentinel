"""Operator-facing metrics for the closed-alpha status dashboard.

Counters live in-process — no Redis, no Prometheus, no time-series store.
"Total since restart" is the published semantic; the dashboard surfaces
``uptime_seconds`` next to every counter so an operator can read the rate
themselves. Acceptable trade-off for closed-alpha scale (~10 concurrent):
restart loses the counts, but anything load-bearing for cost / abuse already
lives in the rate-limiter's day-bucket which persists across handler calls
within a process.

Thread-safety: every counter is a plain ``int`` updated under a single
``threading.Lock`` shared by the snapshot read path. Bumps are infrequent
relative to the read; no need for atomics or per-counter locks.

What this is NOT:
- Not a request log. Per-request data goes to Python logging.
- Not an audit trail. Git-sync commits are the per-turn audit.
- Not user-facing. Operator-only; Caddy excludes ``/api/admin*`` from the
  public edge (see ``infrastructure/caddy/Caddyfile.example``).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Counters:
    """Mutable counter state. Read under the lock to get a coherent snapshot."""

    streams_served: int = 0  # /api/stream calls that got past the concurrency gate
    capacity_rejected: int = 0  # 503 — slot semaphore was full
    rate_limited: int = 0  # 429 — per-world rate or LLM ceiling tripped
    active_streams: int = 0  # currently in-flight (bumped on acquire, dec on release)


@dataclass
class AdminMetrics:
    """Thread-safe counters for the status dashboard.

    Created once at app startup (``app.state.admin_metrics``), shared by every
    handler. The lock is held only across the small critical sections — bump
    one field, or read all four for a snapshot.
    """

    _counters: _Counters = field(default_factory=_Counters)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _started_at: float = field(default_factory=time.monotonic)

    def stream_acquired(self) -> None:
        """Called when a /api/stream slot is successfully claimed."""
        with self._lock:
            self._counters.streams_served += 1
            self._counters.active_streams += 1

    def stream_released(self) -> None:
        """Called when a /api/stream slot is released (any teardown path)."""
        with self._lock:
            # Defensive clamp at 0 — a misuse here shouldn't underflow the gauge.
            if self._counters.active_streams > 0:
                self._counters.active_streams -= 1

    def capacity_rejected(self) -> None:
        """503 — concurrency cap rejected a request."""
        with self._lock:
            self._counters.capacity_rejected += 1

    def rate_limited(self) -> None:
        """429 — per-world rate limit or daily LLM ceiling tripped."""
        with self._lock:
            self._counters.rate_limited += 1

    def snapshot(self) -> dict:
        """Coherent read of all counters + derived metrics. Single lock acquire."""
        with self._lock:
            return {
                "uptime_seconds": time.monotonic() - self._started_at,
                "streams_served_total": self._counters.streams_served,
                "capacity_rejected_total": self._counters.capacity_rejected,
                "rate_limited_total": self._counters.rate_limited,
                "active_streams": self._counters.active_streams,
            }

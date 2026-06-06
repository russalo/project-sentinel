"""Concurrent-streams cap (closed-alpha access-layer dimension #3).

ADR 0003's access layer has three orthogonal dimensions for bounding cost
and abuse:

- **Rate** (`SENTINEL_RL_*`) — turns/min per world; world-creations/hour per IP.
- **Spend** (`SENTINEL_LLM_DAILY_CEILING`) — global daily LLM-call ceiling.
- **Concurrency** (this module — `SENTINEL_MAX_CONCURRENT_STREAMS`) —
  in-flight `/api/stream` requests, the count of LLM-driven turns being
  served simultaneously. This is the one closed-alpha was previously missing
  (2026-06-06): the load-smoke proved N=10 concurrent works *functionally*
  but nothing caps where the system would stop accepting more.

What this caps
--------------
A "slot" is one open `/api/stream` request from acquire-time through the
SSE generator's `finally` block (normal completion OR exception OR
client-disconnect — all release the slot). A tester reading a finished turn
doesn't hold a slot; the moment they submit an action and the backend opens
the SSE response, a slot is held until that turn's stream closes.

Behavior at cap
---------------
**Hard reject** (Russell's explicit choice 2026-06-06 over queueing):
``try_acquire()`` returns ``False`` immediately. The route raises
HTTP 503 with ``Retry-After: 5``. The decision is documented; a future
queueing mode is filed in ``docs/BACKLOG.md`` if/when alpha testers find
the 503 jarring.

When max_streams=0
------------------
Disabled — the limiter is a no-op that always acquires. Same opt-in pattern
as the other ``SENTINEL_*`` access knobs. Default in shipped config is 0
(preserves the pre-2026-06-06 behavior of "the system tries to serve
everyone"); the alpha cutover arms it to ``=10`` per
``docs/WORKSPACE.md`` § "Cutover checklist".
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


class StreamSlotLimiter:
    """Bounded count of in-flight `/api/stream` requests.

    Backed by ``threading.BoundedSemaphore`` so a double-release raises
    ``ValueError`` deterministically (caught + logged here, never propagated
    — a leaked slot is worse than an extra release, but neither should crash
    the route).
    """

    def __init__(self, max_streams: int) -> None:
        if max_streams < 0:
            raise ValueError(f"max_streams must be >= 0, got {max_streams}")
        self._max = max_streams
        # max_streams=0 → disabled; semaphore is None and try_acquire always wins
        self._sem: threading.BoundedSemaphore | None = (
            threading.BoundedSemaphore(max_streams) if max_streams > 0 else None
        )

    @property
    def max_streams(self) -> int:
        """The configured cap. 0 = disabled."""
        return self._max

    @property
    def enabled(self) -> bool:
        """True iff a positive cap is in force."""
        return self._sem is not None

    def try_acquire(self) -> bool:
        """Try to claim a slot without blocking.

        Returns True if the slot was claimed (and must be released later)
        OR if the limiter is disabled (no slot to release; release is a
        no-op anyway). Returns False only when the cap is in force AND
        all slots are held.
        """
        if self._sem is None:
            return True
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        """Release a previously-acquired slot.

        Safe to call when disabled (no-op). Safe to call from the SSE
        generator's ``finally`` block — covers normal completion,
        exceptions, and client-disconnect.

        Excess releases (double-release on the same slot) are caught:
        ``BoundedSemaphore.release()`` raises ``ValueError`` if the count
        would exceed the initial value. We log and swallow — a leaked
        permit is worse than an extra one, and the symptom of a real bug
        would surface as "users intermittently 503ed below the cap,"
        which is the correct failure shape rather than a 500.
        """
        if self._sem is None:
            return
        try:
            self._sem.release()
        except ValueError:
            # Double-release. Don't crash the route; log and continue.
            logger.warning(
                "StreamSlotLimiter.release(): excess release attempted; "
                "this indicates the caller's try/finally pairing has a bug. "
                "Cap remains intact.",
                exc_info=True,
            )

    @contextmanager
    def slot(self) -> Iterator[bool]:
        """Context manager: yields True if a slot was acquired, False otherwise.

        Pattern::

            with limiter.slot() as acquired:
                if not acquired:
                    raise HTTPException(503, ...)
                # ...do work...

        Release happens on context exit regardless of whether work raised.
        When the limiter is disabled, this always yields True with a no-op
        release.
        """
        acquired = self.try_acquire()
        try:
            yield acquired
        finally:
            if acquired:
                self.release()

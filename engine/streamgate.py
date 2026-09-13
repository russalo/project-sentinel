"""Stream-side gate keeping ``<world_update>`` markup out of the player-visible
token stream (Item 3 / playtest F3b).

Why server-side: the SPA consumes state ONLY from the structured
``world_update`` SSE event and strips raw block text with a regex that
REQUIRES the closing tag (``chatStore.js::stripWorldUpdate``, copied at
``WorldCreation.jsx`` and ``useWorldHydration.js``) — so a TRUNCATED block
(open tag, no close) rendered to the player as a raw JSON wall. Withholding
block content at the source closes exactly the case the client cannot, and
demotes the SPA's stripping to belt-and-suspenders. ``<action>`` tags and all
other narrative markup stream unchanged.

Pure and incremental — no IO, no framework; the engine boundary holds.
"""

from __future__ import annotations

_OPEN = "<world_update>"
_CLOSE = "</world_update>"


class WorldUpdateGate:
    """Incremental filter: ``feed()`` tokens in, player-safe text out.

    OUTSIDE a block, text is emitted as it arrives, minus a held tail that
    could be the start of an open tag split across token boundaries. INSIDE a
    block, everything is suppressed until the close tag. The caller keeps the
    full raw text separately for fact extraction — the gate only decides what
    streams.
    """

    def __init__(self) -> None:
        self._inside = False
        self._pending = ""

    def feed(self, token: str) -> str:
        """Absorb one token; return whatever text is now safe to display."""
        if not isinstance(token, str) or not token:
            return ""
        self._pending += token
        emitted: list[str] = []
        while True:
            if self._inside:
                idx = self._pending.find(_CLOSE)
                if idx == -1:
                    # Keep just enough tail to recognize a close tag spanning
                    # chunk boundaries; suppressed content isn't needed here.
                    self._pending = self._pending[-(len(_CLOSE) - 1) :]
                    break
                self._pending = self._pending[idx + len(_CLOSE) :]
                self._inside = False
            else:
                idx = self._pending.find(_OPEN)
                if idx != -1:
                    emitted.append(self._pending[:idx])
                    self._pending = self._pending[idx + len(_OPEN) :]
                    self._inside = True
                    continue
                hold = _partial_suffix_len(self._pending, _OPEN)
                cut = len(self._pending) - hold
                emitted.append(self._pending[:cut])
                self._pending = self._pending[cut:]
                break
        return "".join(emitted)

    def flush(self) -> str:
        """End-of-stream: the held tail, unless it is block remainder.

        Inside an unclosed block → nothing (the truncated JSON must never
        display). A held tail of >= 4 chars ("<wor") is a plausible cut-off
        open tag → dropped, matching ``fact_extractor.strip_unclosed_block``
        (threshold raised from 2 with it — prose legitimately ends "…</" or
        "…<w", the #196 swarm nit); anything shorter is returned as prose.
        """
        pending, self._pending = self._pending, ""
        if self._inside:
            return ""
        if len(pending) >= 4 and _OPEN.startswith(pending):
            return ""
        return pending


def _partial_suffix_len(text: str, tag: str) -> int:
    """Length of the longest strict prefix of ``tag`` that suffixes ``text``."""
    for length in range(min(len(text), len(tag) - 1), 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0

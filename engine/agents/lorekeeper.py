"""Lorekeeper — the engine-side (pure) half of the lore-retrieval fold.

RFC-0011 / ADR-0006. The Lorekeeper surfaces *established canon* relevant to
the current turn so the DM cites it instead of improvising (and contradicting
itself across sessions). Retrieval is done by ``poggio`` (an external
trellis-based tool) as a subprocess reading the world's ``data/`` — that IO
lives in the **backend** (``backend/state/lorekeeper.py``), per the engine
boundary contract (``engine/README.md``: no runtime side effects). This module
is the **pure render half**: given the ranked hits the backend retrieved, it
formats the DM-prompt "canon" block. No IO here.

Mirrors the roll / level-up block helpers in ``engine.agents.dm`` — a small,
tolerant renderer that degrades to ``""`` when there's nothing to inject, so a
disabled or fail-open retrieval path changes the assembled prompt not at all.
"""

from __future__ import annotations

_HEADER = (
    "\nRELEVANT CANON (established facts — cite, do not contradict or re-invent):\n"
)


def render_canon_block(hits: object) -> str:
    """Render the retrieved-canon block for the DM user message, or ``""``.

    ``hits`` is the backend's lean-projected list — each a dict shaped like
    ``{id, kind, name, source, snippet}``. Tolerant by design: a non-list, a
    non-dict element, or a hit with neither a name nor a snippet is skipped
    (never raised on), because this text lands verbatim in the prompt and the
    retrieval source is an external tool whose output we don't fully trust. An
    empty result → ``""`` (no block), so the fail-open / disabled path is
    byte-identical to a turn with no retrieval.
    """
    if not isinstance(hits, list):
        return ""
    lines: list[str] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        name = h.get("name") or h.get("id")
        snippet = str(h.get("snippet") or "").strip()
        if not name and not snippet:
            continue
        kind = h.get("kind", "?")
        label = f"{name} [{kind}]" if name else f"[{kind}]"
        line = f"- {label}: {snippet}" if snippet else f"- {label}"
        source = h.get("source")
        if source:
            line += f" (source: {source})"
        lines.append(line)
    if not lines:
        return ""
    return _HEADER + "\n".join(lines) + "\n"

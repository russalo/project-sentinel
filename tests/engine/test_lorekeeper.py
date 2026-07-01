"""Engine-side (pure) Lorekeeper renderer — RFC-0011.

``render_canon_block`` formats retrieved canon hits into the DM-prompt block.
It must degrade to ``""`` for anything empty/malformed (so the disabled /
fail-open path leaves the assembled prompt unchanged) and never raise on
untrusted external-tool output.
"""

from __future__ import annotations

from engine.agents.lorekeeper import render_canon_block

_HITS = [
    {
        "id": "chez",
        "kind": "character",
        "name": "Chez",
        "source": "data/state/core/entities/chez.json",
        "snippet": "Chaingang boss with a head full of unspoken questions",
    },
    {
        "id": "sess:t1",
        "kind": "turn",
        "name": "prior turn 1",
        "source": "data/state/core/sessions/sess.json",
        "snippet": "The millstones remember. Ask about the third son.",
    },
]


def test_renders_header_and_one_line_per_hit():
    block = render_canon_block(_HITS)
    assert "RELEVANT CANON" in block
    assert "cite, do not contradict or re-invent" in block
    assert "- Chez [character]: Chaingang boss" in block
    assert "(source: data/state/core/entities/chez.json)" in block
    assert "- prior turn 1 [turn]: The millstones remember" in block


def test_empty_or_none_renders_nothing():
    # The dormant / fail-open path: no block at all, so the prompt is unchanged.
    assert render_canon_block(None) == ""
    assert render_canon_block([]) == ""
    assert render_canon_block("not a list") == ""


def test_tolerates_malformed_hits_without_raising():
    # External-tool output is untrusted + lands verbatim in the prompt.
    assert render_canon_block(["x", 42, None, {"kind": "character"}]) == ""
    # a hit with no name but a snippet still renders (labelled by kind)
    block = render_canon_block([{"kind": "turn", "snippet": "a thing happened"}])
    assert "- [turn]: a thing happened" in block


def test_source_omitted_when_absent():
    block = render_canon_block(
        [{"id": "x", "kind": "item", "name": "Thing", "snippet": "s"}]
    )
    assert "- Thing [item]: s" in block
    assert "(source:" not in block

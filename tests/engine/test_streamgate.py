"""WorldUpdateGate — the stream-side filter that keeps <world_update> markup
off the player-visible token stream (Item 3 / playtest F3b).

The SPA's strippers require the CLOSING tag, so a truncated block used to
render as a raw JSON wall; the gate closes exactly that case at the source.
"""

from engine.streamgate import WorldUpdateGate

OPEN = "<world_update>"
CLOSE = "</world_update>"


def _run(tokens):
    """Feed tokens through a gate; return the fully-drained visible text."""
    gate = WorldUpdateGate()
    out = [gate.feed(t) for t in tokens]
    out.append(gate.flush())
    return "".join(out)


def test_plain_narrative_passes_through_verbatim():
    tokens = ["The fire ", "dims. <action>Look</action> ", "Dust settles."]
    assert _run(tokens) == "".join(tokens)  # <action> tags are NOT gated


def test_complete_block_is_suppressed_text_around_it_survives():
    tokens = ["Before. ", OPEN, '{"world": {"tension": 4}}', CLOSE, " After."]
    assert _run(tokens) == "Before.  After."


def test_open_tag_split_across_tokens_still_gates():
    # The exact chunk-boundary case: no single token contains the tag.
    tokens = ["Story. <world_", "update>", '{"secret": 1}', "</world_", "update>"]
    assert _run(tokens) == "Story. "


def test_unclosed_block_never_reaches_the_wire():
    # Playtest F3b: cut mid-JSON — everything from the open tag on is withheld.
    tokens = ["The ledger opens. ", OPEN, '{"world": {"tens']
    assert _run(tokens) == "The ledger opens. "


def test_cut_mid_close_tag_is_also_withheld():
    tokens = ["Tale. ", OPEN, '{"a": 1}', "</world_upd"]
    assert _run(tokens) == "Tale. "


def test_cut_mid_open_tag_drops_the_partial_tag_only():
    tokens = ["A road forks. ", "<world_upd"]
    assert _run(tokens) == "A road forks. "


def test_lone_angle_bracket_at_end_is_legitimate_prose():
    assert _run(["The sign reads 3 <"]) == "The sign reads 3 <"


def test_short_bracket_runs_at_end_are_prose_not_tags():
    # Threshold aligned with fact_extractor at >= 4 chars (#196 swarm nit):
    # "…</" and "…<w" are prose and must flush, not vanish.
    assert _run(["He trails off …</"]) == "He trails off …</"
    assert _run(["an aside <w"]) == "an aside <w"
    # A 4-char prefix IS a plausible cut-off tag → still dropped.
    assert _run(["A road forks. <wor"]) == "A road forks. "


def test_text_resumes_after_a_block_and_multiple_blocks_gate():
    tokens = ["A. ", OPEN, "{}", CLOSE, "B. ", OPEN, "{}", CLOSE, "C."]
    assert _run(tokens) == "A. B. C."


def test_angle_bracket_prose_mid_stream_is_not_lost():
    # "<w" is held as a possible tag start, then released once disambiguated.
    tokens = ["x <w", "ord> y"]
    assert _run(tokens) == "x <word> y"


def test_feed_is_incremental_not_batched():
    gate = WorldUpdateGate()
    first = gate.feed("Hello ")
    assert first == "Hello "  # emitted immediately, not held until flush


def test_junk_tokens_are_tolerated():
    gate = WorldUpdateGate()
    assert gate.feed("") == ""
    assert gate.feed(None) == ""  # type: ignore[arg-type]
    assert gate.flush() == ""

"""RFC-0016 — mock DM client for the deterministic deploy smoke test.

When ``Settings.dm_mode == "mock"`` the backend injects one of these fixture
clients into the DM agents (``engine.agents.dm``) in place of the live LLM. The
engine is IO-pure, so fixture loading + per-turn selection live here in the
backend; the client only satisfies the ``.chat.completions.create`` shape the DM
agents call, returning a scripted ``narrative + <world_update>`` block.

Fixture format — a JSON object::

    {"turns": [ {"turn": N, "player_action": "...", "narrative": "...",
                 "world_update": { ... } | null }, ... ]}

``turn`` 0 is the intro (``generate_intro``); turns 1..N are the ``/api/stream``
responses **in POST order** — a check-request turn and its roll-resolve turn are
SEPARATE entries, matching the real two-round-trip turn cadence (a ``check_request``
lives inside the ``world_update`` block; the resolve turn carries the roll result).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# The committed default fixture (the DM-authored death sequence, reconciled to
# the real emit shape + cadence). Overridable via SENTINEL_DM_MOCK_FIXTURE.
_DEFAULT_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "mock_dm_death_sequence.json"
)


def fixture_path(settings: Any) -> Path:
    raw = getattr(settings, "dm_mock_fixture", None)
    return Path(raw) if raw else _DEFAULT_FIXTURE


def load_turns(settings: Any) -> dict[int, dict]:
    """Load the fixture and index its turns by ``turn`` number."""
    data = json.loads(fixture_path(settings).read_text(encoding="utf-8"))
    return {int(t["turn"]): t for t in data["turns"]}


def _raw_for_turn(turn: dict) -> str:
    """Render a fixture turn as the raw DM output the fact-extractor parses."""
    narrative = turn.get("narrative", "") or ""
    world_update = turn.get("world_update")
    if world_update is None:
        return narrative
    block = json.dumps(world_update, indent=2)
    return f"{narrative}\n\n<world_update>\n{block}\n</world_update>"


def _stream_chunks(text: str, pieces: int = 24):
    """Split ``text`` into ~``pieces`` chunks so streaming exercises the token path."""
    if not text:
        return
    step = max(1, len(text) // pieces)
    for i in range(0, len(text), step):
        yield text[i : i + step]


class _MockCompletions:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    def create(self, *, stream: bool = False, **_kwargs: Any):
        # Mirrors openai's client.chat.completions.create: a response object with
        # choices[0].message.content when blocking, or an iterator of chunks whose
        # joined choices[0].delta.content reconstructs the same text when streaming.
        if stream:
            return (
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))]
                )
                for chunk in _stream_chunks(self._raw)
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._raw))]
        )


def client_for_turn(settings: Any, turn_number: int) -> Any:
    """Return a mock LLM client that emits the fixture's turn-``turn_number`` output.

    Raises ``KeyError`` when the fixture has no such turn — a mock session must not
    over-run its script (fail loud rather than silently repeat or hang). Callers
    (the DM stream) surface this as the generic "DM agent failed" SSE error.
    """
    turn = load_turns(settings)[int(turn_number)]
    raw = _raw_for_turn(turn)
    return SimpleNamespace(chat=SimpleNamespace(completions=_MockCompletions(raw)))

"""DM agent — generates narrative in response to player actions.

Current status: stub. This module will wrap the OpenAI chat completion
call (streaming and non-streaming) that currently lives in
backend/api/dm_ai.py. Migration is deferred until the source-of-truth
and agent-topology decisions are made — see docs/BACKLOG.md.

When implemented, the streaming entry point must be a plain generator
yielding token strings. The caller (Django SSE view today, possibly
FastAPI tomorrow) wraps that generator in whatever transport it needs.
"""

from typing import Iterator

from ..types import Config, DMTurnInput, DMTurnResult


def run_turn(config: Config, turn_input: DMTurnInput) -> DMTurnResult:
    """Run a blocking DM turn and return the complete result.

    Not yet implemented — scaffolding only.
    """
    raise NotImplementedError("engine.agents.dm.run_turn is not implemented yet")


def stream_turn(config: Config, turn_input: DMTurnInput) -> Iterator[str]:
    """Stream a DM turn token-by-token.

    Callers accumulate tokens, strip the <world_update> block for the
    user-facing narrative, and pass the raw response to the Fact-Extractor.

    Not yet implemented — scaffolding only.
    """
    raise NotImplementedError("engine.agents.dm.stream_turn is not implemented yet")

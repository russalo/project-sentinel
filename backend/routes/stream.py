"""POST /api/stream — SSE streaming DM turn.

This is the endpoint the frontend's ``useDMStream`` hook hits on every
player action. It:

1. Reads the active session from disk (via state/sessions.py)
2. Builds a WorldContext from data/state/*.json (via state/world_context.py)
3. Opens an SSE response
4. Streams DM tokens live via engine.agents.dm.stream_turn
5. After the stream closes, parses the accumulated response with
   the Fact-Extractor and dispatches the result to fs-manager
6. Emits a world_update SSE event (in the DM hint shape the frontend
   expects) and a [DONE] sentinel

SSE event shapes (preserved from the Django backend so the frontend
works without changes):

  data: {"type": "token", "content": "<chunk>"}
  data: {"type": "world_update", "data": {world, characters, ...}}
  data: {"type": "error", "content": "<message>"}
  data: [DONE]

The handler does not expose ``system`` events (the frontend handles
them defensively but the old backend never emitted them either).
"""

import json
import re
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

import engine
from engine.agents import dm as dm_agent
from engine.agents import fact_extractor

from ..config import Settings
from ..engine_bridge import build_engine_config
from ..schemas import StreamRequest
from ..state import sessions as session_state
from ..state.world_context import load_world_context

router = APIRouter(prefix="/api")

_BLOCK_RE = re.compile(r"<world_update>([\s\S]*?)</world_update>")


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _parse_frontend_hint(raw: str) -> dict:
    """Pull the raw <world_update> hint block out of a DM response.

    Returns the DM's hint-shape JSON (what the frontend's worldStore
    expects), not the apply_world_update.schema.json shape.
    """
    match = _BLOCK_RE.search(raw)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post("/stream")
def stream_turn(request: Request, body: StreamRequest) -> StreamingResponse:
    # NOTE: This handler is deliberately `def`, not `async def`.
    # The generator it returns iterates engine.agents.dm.stream_turn
    # (a synchronous generator), and every dispatch inside it is
    # synchronous blocking I/O (fs-manager HTTP, file reads). FastAPI
    # runs sync handlers — and sync generators returned to
    # StreamingResponse — in a thread pool, so they don't stall the
    # event loop. An `async def` handler with an async generator
    # that drives a sync iterator internally would block the loop
    # on every token.
    settings: Settings = request.app.state.settings
    config = build_engine_config(settings)

    session = session_state.read_session(settings.data_dir, body.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session not found or inactive",
        )
    if not session.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active",
        )

    # Build the world context the DM will see for this turn.
    recent = [
        {
            "playerAction": t.get("player_action", ""),
            "narrative": t.get("narrative", ""),
        }
        for t in session.turns[-5:]
    ]
    world_context = load_world_context(
        settings.data_dir,
        session_id=body.session_id,
        recent_turns=recent,
    )

    turn_input = engine.DMTurnInput(
        session_id=body.session_id,
        player_action=body.action,
        world_context=world_context,
    )

    next_turn_number = (session.turns[-1]["turn_number"] + 1) if session.turns else 1

    def generator() -> Iterator[str]:
        buffer: list[str] = []

        try:
            for token in dm_agent.stream_turn(config, turn_input):
                buffer.append(token)
                yield _sse_event({"type": "token", "content": token})
        except Exception as exc:  # pragma: no cover - network/OpenAI failure
            yield _sse_event({"type": "error", "content": str(exc)})
            yield "data: [DONE]\n\n"
            return

        raw_response = "".join(buffer)
        narrative = _BLOCK_RE.sub("", raw_response).strip()
        frontend_hint = _parse_frontend_hint(raw_response)

        # Emit the world_update event in the shape the frontend
        # expects (DM hint shape, not the fs-manager schema shape).
        yield _sse_event({"type": "world_update", "data": frontend_hint})

        # Dispatch the canonical payload through the engine →
        # fs-manager path. Failure here is logged as an error event
        # so the frontend can surface it; the narrative has already
        # streamed to the player so we never roll back.
        extracted = fact_extractor.extract(
            raw_response,
            session_id=body.session_id,
            turn_number=next_turn_number,
        )
        if extracted.payload is not None:
            dispatch = engine.apply_world_update(config, extracted.payload)
            if not dispatch.ok:
                yield _sse_event(
                    {"type": "error", "content": f"fs-manager rejected update: {dispatch.error}"}
                )

        # Append the turn to the session file and re-serialize it.
        session.turns.append(
            {
                "id": next_turn_number + 1,
                "session_id": body.session_id,
                "turn_number": next_turn_number,
                "player_action": body.action,
                "narrative": narrative,
                "world_updates": frontend_hint,
                "created_at": "",  # created_at currently unused by the frontend
            }
        )
        session_write = session_state.write_session(
            config,
            session,
            log_entry=narrative[:200] or f"Turn {next_turn_number} completed.",
            turn_number=next_turn_number,
        )
        # If the session write fails, the narrative has already been
        # streamed to the player and the game is in a half-persisted
        # state: the world-state dispatch (above) succeeded, but the
        # per-session turn log and counter didn't advance. Surface
        # this as a structured error event so the frontend can show
        # the toast; we still emit [DONE] so the stream closes
        # cleanly. The next turn will regenerate from whatever
        # `recent_turns` the stale session file has.
        if not session_write.ok:
            yield _sse_event(
                {
                    "type": "error",
                    "content": f"Failed to save turn to session: {session_write.error}",
                }
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

"""POST /api/session/new — create a new game session.

Blocking endpoint (not streaming) because the frontend's WorldCreation
flow calls this via ``apiClient.post`` and reads ``data.sessionId`` +
``data.turns[0].narrative`` from the response. Streaming would require
changing the frontend; the contract is blocking.

Flow
----
1. Generate a new UUID for the session
2. Build an engine.Config from backend settings
3. Run the engine's intro agent (``engine.agents.dm.generate_intro``)
   — produces an opening narrative + a <world_update> block that
   establishes the initial world state
4. Feed the raw DM response to the Fact-Extractor to produce a
   schema-valid apply_world_update payload
5. Dispatch that payload to fs-manager (writes the initial
   data/state/core/world/state.json, data/state/core/entities/*.json,
   etc.) — per ADR 0001, the canonical write path
6. Build a Session dataclass with turn 0 (the session-start entry),
   write it to data/state/core/sessions/<id>.json via the same
   engine → fs-manager path
7. Return NewSessionResponse to the frontend

Every mutation routes through the engine → fs-manager → git-sync
pipeline. The handler itself never touches the filesystem directly.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

import engine
from engine.agents import dm as dm_agent
from engine.agents import fact_extractor

from ..config import Settings
from ..engine_bridge import build_engine_config
from ..schemas import NewSessionRequest, NewSessionResponse, TurnResponse
from ..state import sessions as session_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post(
    "/session/new",
    response_model=NewSessionResponse,
    response_model_by_alias=True,
)
def new_session(request: Request, body: NewSessionRequest) -> NewSessionResponse:
    # NOTE: This handler is deliberately `def`, not `async def`.
    # Everything it calls is synchronous blocking I/O (OpenAI, fs-manager
    # HTTP, filesystem). FastAPI runs sync handlers in a thread pool
    # automatically, so they don't stall the event loop. Making this
    # `async def` would block the loop on every request.
    settings: Settings = request.app.state.settings
    config = build_engine_config(settings)

    session_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    intro_input = engine.IntroInput(
        world_name=body.world_name,
        player_name=body.player_character_name,
        player_class=body.player_character_class,
        world_seed=body.world_seed,
    )

    # 1. Run the intro through the engine.
    try:
        intro_result = dm_agent.generate_intro(config, intro_input)
    except Exception as exc:  # pragma: no cover - network/OpenAI failure
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DM agent failed during intro: {exc}",
        ) from exc

    # 2. Extract the initial world payload from the intro.
    extracted = fact_extractor.extract(
        intro_result.raw_response,
        session_id=session_id,
        turn_number=0,
    )

    # 3. Dispatch the world state through the engine → fs-manager path.
    #    Failure here does NOT abort the session — the narrative has
    #    value on its own, and the world can still evolve from the next
    #    turn forward. Log it by surfacing the error on the response
    #    as a system-like note if necessary. For now we just skip
    #    silently — observability is a later concern.
    if extracted.payload is not None:
        engine.apply_world_update(config, extracted.payload)

    # 4. Build the session record with the opening turn.
    turn_zero = {
        "id": 1,
        "session_id": session_id,
        "turn_number": 0,
        "player_action": (
            f"[Session Start] {body.player_character_name} the "
            f"{body.player_character_class} begins their journey in "
            f"{body.world_name}."
        ),
        "narrative": intro_result.narrative,
        "world_updates": _parse_hint_block_for_frontend(intro_result.raw_response),
        "created_at": started_at,
    }

    session = session_state.Session(
        session_id=session_id,
        world_name=body.world_name,
        started_at=started_at,
        turns=[turn_zero],
        active=True,
    )

    # Writing the session file is the critical durability step: if
    # this dispatch fails, the caller will get back a sessionId that
    # has no on-disk record, and every subsequent /api/stream request
    # against that ID will 400 with "session not found." Treat that
    # as a creation failure rather than silently returning success.
    write_result = session_state.write_session(
        config,
        session,
        log_entry=f"[Session Start] {body.world_name} — intro generated.",
        turn_number=0,
    )

    # Commit the snapshot via git-sync BEFORE deciding whether to
    # raise on session-write failure. Rationale: the preceding
    # apply_world_update dispatch may have already written real
    # state mutations (entities, locations, items, world state) to
    # disk. If we 502 without committing, those mutations exist on
    # the filesystem but are not in git history — a silent audit
    # gap exactly in the failure mode this code is supposed to be
    # durable against. Committing whatever is on disk before we
    # raise captures the partial success honestly: the commit will
    # include the world state that did land and exclude the
    # session file that didn't.
    commit_result = engine.commit_snapshot(
        config,
        session_id=session_id,
        turn_number=0,
        summary=f"Session start: {body.world_name}",
    )
    if not commit_result.ok:
        # Fire-and-log: the session is either created (on write
        # success below) or raising (on write failure below), and
        # in either path the commit failure is a durability concern
        # we want visible in the backend log but not a reason to
        # change response semantics. Observability plumbing can
        # promote this to a metric or an alert in a later PR.
        logger.warning(
            "commit_snapshot failed on session creation: %s",
            commit_result.error,
        )

    if not write_result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to persist new session: {write_result.error}",
        )

    return NewSessionResponse(
        session_id=session_id,
        turns=[TurnResponse(**turn_zero)],
        started_at=started_at,
        world_name=body.world_name,
    )


def _parse_hint_block_for_frontend(raw_response: str) -> dict:
    """Extract the raw <world_update> hint block (not the
    apply_world_update schema shape) from a DM response.

    The frontend's worldStore.applyUpdate expects the DM hint shape
    (``{world, characters, locations, factions, items}``), not the
    filesystem-operations contract. We parse the block a second time
    here to give the frontend what it wants without distorting the
    Fact-Extractor's output shape.
    """
    import json
    import re

    match = re.search(r"<world_update>([\s\S]*?)</world_update>", raw_response)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}

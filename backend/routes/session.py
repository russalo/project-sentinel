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

from .. import mock_dm

from ..auth.access import extract_basic_auth_user, issue_token
from ..config import Settings
from ..engine_bridge import build_engine_config
from ..presets import get_prompt_fragment
from ..ratelimit import client_ip, enforce, enforce_llm_ceiling
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

    # ADR 0003 Slice B — closed-beta backstop. Rate-limit world creation per IP
    # and gate on the global daily LLM-call ceiling BEFORE the (paid) intro
    # call. Both no-op when their configured value is <= 0 (the default).
    # 429s here are counted on admin_metrics so the dashboard sees pressure
    # across both /api/session/new and /api/stream entry points.
    limiter = request.app.state.rate_limiter
    admin_metrics = request.app.state.admin_metrics
    try:
        enforce(
            limiter,
            f"session_create:{client_ip(request, settings.trusted_proxy_hops)}",
            settings.rl_session_create_per_hour,
            60 * 60,
            detail="too many world creations; try again later",
        )
        # RFC-0016: mock DM makes no LLM call — don't charge the daily ceiling.
        if settings.dm_mode != "mock":
            enforce_llm_ceiling(limiter, settings.llm_daily_ceiling)
    except HTTPException as exc:
        if exc.status_code == 429:
            admin_metrics.rate_limited()
        raise

    session_id = str(uuid.uuid4())
    # ADR 0002: every session belongs to a world. Minted here and threaded into
    # the session record + git-sync commit messages. Per-world data isolation
    # (routing reads/writes to the world's own tree) lands in a later slice.
    world_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    # Per-tester reauth (2026-06-08): capture the basic_auth identity the edge
    # proxy authenticated this request with, so the world knows its creator and
    # the /reauth endpoint can confirm a re-mint request. None on the anonymous
    # tailnet flow (no basic_auth) → token stays unbound (legacy shape), which
    # keeps single-user dev unchanged.
    creator_username = extract_basic_auth_user(request)

    # Provision the world's git repo before any write to it (ADR 0002 Slice 3).
    # A fresh per-world repo has no HEAD, so the commit_snapshot below would
    # fail against it. Only called when the cutover is on (worlds_root set);
    # pre-cutover there is no extra round-trip, and git-sync would no-op anyway.
    # Treat a provisioning failure as fatal: writing into an un-init'd world
    # would land state on disk that never enters git history (silent audit gap).
    if settings.worlds_root:
        init_result = engine.init_world(config, world_id=world_id)
        if not init_result.ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"world provisioning failed: {init_result.error}",
            )
        # "skipped" means git-sync has no SENTINEL_WORLDS_ROOT while the backend
        # does — the two disagree on per-world mode. Treating that as success
        # would write/commit to the shared repo while the backend reads the
        # (empty) per-world tree → every turn 404s. Fail loudly on the misconfig.
        if init_result.body.get("status") == "skipped":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "world provisioning skipped — git-sync has no "
                    "SENTINEL_WORLDS_ROOT but the backend does; the services "
                    "disagree on per-world mode. Set the same value everywhere."
                ),
            )

    # Layer 2: resolve rich preset content for the four preset-backed
    # fields. Each call silently returns None when no preset file is
    # found, which lets the engine fall through to the Layer 1 bare-
    # label handling without the frontend needing to know which
    # presets exist on disk. Regions are genre-scoped (the same slug
    # can legally exist under different genres).
    preset_root = settings.data_dir / "lore" / "core" / "presets"
    genre_prompt = get_prompt_fragment(preset_root, "genres", body.genre)
    persona_prompt = get_prompt_fragment(preset_root, "personas", body.persona_id)
    mood_prompt = get_prompt_fragment(preset_root, "moods", body.mood)
    region_prompt = get_prompt_fragment(
        preset_root,
        "regions",
        body.starting_region,
        genre=body.genre,
    )

    intro_input = engine.IntroInput(
        world_name=body.world_name,
        player_name=body.player_character_name,
        player_class=body.player_character_class,
        world_seed=body.world_seed,
        genre=body.genre,
        tone=body.tone,
        starting_region=body.starting_region,
        persona_id=body.persona_id,
        persona_name=body.persona_name,
        persona_description=body.persona_description,
        mood=body.mood,
        sandbox=body.sandbox,
        permadeath=body.permadeath,
        genre_prompt=genre_prompt,
        persona_prompt=persona_prompt,
        mood_prompt=mood_prompt,
        region_prompt=region_prompt,
    )

    # 1. Run the intro through the engine.
    try:
        # RFC-0016: mock-DM mode serves the fixture's turn 0 as the intro.
        intro_client = (
            mock_dm.client_for_turn(settings, 0) if settings.dm_mode == "mock" else None
        )
        intro_result = dm_agent.generate_intro(config, intro_input, client=intro_client)
    except Exception as exc:  # pragma: no cover - network/OpenAI failure
        # Log the full traceback server-side (exc_info=True); do NOT leak it to
        # the client — the upstream string can carry the provider org id + quota
        # (red-team #4).
        logger.warning("DM intro failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="DM agent failed during intro; please retry.",
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
        engine.apply_world_update(config, extracted.payload, world_id=world_id)

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
        player_character_name=body.player_character_name,
        player_character_class=body.player_character_class,
        # Prefer the resolved persona display name; fall back to the id.
        dm_persona_name=body.persona_name or body.persona_id or "",
        persona_id=body.persona_id or "",
        mood=body.mood or "",
        world_id=world_id,
        creator_username=creator_username or "",
        # Persist permadeath so the death-stakes gate (RFC-0014) can enforce it
        # every turn, not just render it into the intro prompt.
        permadeath=body.permadeath,
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
        world_id=world_id,
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

    # ADR 0003 Slice A — mint the per-world token (None when enforcement is
    # off). The client stores it keyed by world_id and presents it on
    # world-scoped calls (/stream, /world GET+DELETE). When the request carried
    # a basic_auth identity (closed-alpha cohort), bind the token to that
    # username so /reauth can confirm a re-mint request comes from the creator;
    # otherwise mint an unbound (legacy-shape) token.
    session_token = issue_token(settings, world_id, username=creator_username)

    return NewSessionResponse(
        session_id=session_id,
        world_id=world_id,
        turns=[TurnResponse(**turn_zero)],
        started_at=started_at,
        world_name=body.world_name,
        session_token=session_token,
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

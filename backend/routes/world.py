"""World hydration endpoint (ADR 0002 Slice 4).

    GET /api/world/{world_id} → the world's current session for resume

Backs the frontend's ``/w/<world_id>`` route: a fresh browser opening that URL
has nothing stored locally, so it fetches the world's session here to rebuild
the chat scroll and continue play. Read-only; resolves the world's own tree
(or the shared tree pre-cutover) and returns the most-recent session.
"""

from __future__ import annotations

import engine
from fastapi import APIRouter, HTTPException, Request, status

from ..engine_bridge import build_engine_config
from ..state import sessions as session_state
from ..state.world_context import load_world_context
from ..state.world_root import find_world_session, iter_worlds

router = APIRouter(prefix="/api")


@router.get("/worlds")
def list_worlds(request: Request) -> list[dict]:
    """Summaries of every world for the "my worlds" picker (ADR 0002 Slice 5).

    Most-recently-played first. Each entry links to ``/w/<worldId>`` in the UI.
    Empty list when no worlds exist (the picker shows a create CTA).
    """
    settings = request.app.state.settings
    out: list[dict] = []
    for world_id, data_dir, session_id in iter_worlds(
        settings.worlds_root, default_data_dir=settings.data_dir
    ):
        session = session_state.read_session(data_dir, session_id)
        if session is None:
            continue
        out.append(
            {
                "worldId": world_id,
                "worldName": session.world_name,
                "persona": session.dm_persona_name,
                "character": session.player_character_name,
                "turnCount": len(session.turns or []),
                "startedAt": session.started_at,
            }
        )
    return out


@router.delete("/world/{world_id}")
def delete_world(world_id: str, request: Request) -> dict:
    """Permanently delete a world (ADR 0002 Slice 5 — hard delete).

    Resolves the world's session first (404 if the world has none), then routes
    the removal through git-sync (per-world: rmtree the repo; legacy: git rm the
    session). All data mutation stays in git-sync — the backend never removes
    files directly. The frontend gates this behind a confirmation.
    """
    settings = request.app.state.settings
    found = find_world_session(
        settings.worlds_root, world_id, default_data_dir=settings.data_dir
    )
    if found is None:
        raise HTTPException(status_code=404, detail="world not found")
    _data_dir, session_id = found

    result = engine.teardown_world(
        build_engine_config(settings), world_id=world_id, session_id=session_id
    )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"world teardown failed: {result.error}",
        )
    return {"worldId": world_id, "status": result.body.get("status", "removed")}


@router.get("/world/{world_id}")
def get_world(world_id: str, request: Request) -> dict:
    """The world's current session (id + metadata + turn log), for resume.

    404 when the world has no session — a bad/unknown ``world_id`` and a
    genuinely empty world are indistinguishable to a caller and get the same
    response (the id is the only secret, same posture as session lookups).
    """
    settings = request.app.state.settings
    found = find_world_session(
        settings.worlds_root, world_id, default_data_dir=settings.data_dir
    )
    session = None
    data_dir = None
    if found is not None:
        data_dir, session_id = found
        session = session_state.read_session(data_dir, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="world not found")

    # World state for panel rehydration (ADR 0002 Slice 5). Read from the same
    # data dir the session was found in, so a resumed world shows its
    # entities/locations/factions/items, not just the narrative scroll. The
    # canonical entity dicts are flat {name, …} objects — the shape worldStore
    # already keys by name — so the frontend loads them as-is.
    #
    # Scoping note: in per-world mode (SENTINEL_WORLDS_ROOT set) data_dir is the
    # world's own tree → correctly isolated. In legacy/shared mode it's the one
    # shared tree, so this returns the global shared state — exactly what the
    # live turn loop (stream.py's load_world_context) reads in that mode too, so
    # resume panels match live panels. True per-world panel isolation is the
    # cutover's job, not something legacy mode can provide (shared-tree entities
    # aren't world-tagged). See docs/BACKLOG.md.
    ctx = load_world_context(data_dir, session_id=session.session_id)
    world_state = {
        "worldName": ctx.world_name,
        "currentLocation": ctx.current_location,
        "timeOfDay": ctx.time_of_day,
        "weather": ctx.weather,
        "tension": ctx.tension,
        "characters": ctx.characters,
        "locations": ctx.locations,
        "factions": ctx.factions,
        "items": ctx.items,
    }

    return {
        "worldId": world_id,
        "sessionId": session.session_id,
        "worldName": session.world_name,
        "persona": session.dm_persona_name,
        "personaId": session.persona_id,
        "mood": session.mood,
        "character": session.player_character_name,
        "characterClass": session.player_character_class,
        "startedAt": session.started_at,
        "turns": session.turns,
        "worldState": world_state,
    }

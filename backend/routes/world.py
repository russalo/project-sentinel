"""World hydration endpoint (ADR 0002 Slice 4).

    GET /api/world/{world_id} → the world's current session for resume

Backs the frontend's ``/w/<world_id>`` route: a fresh browser opening that URL
has nothing stored locally, so it fetches the world's session here to rebuild
the chat scroll and continue play. Read-only; resolves the world's own tree
(or the shared tree pre-cutover) and returns the most-recent session.
"""

from __future__ import annotations

import logging
import uuid

import engine
from fastapi import APIRouter, HTTPException, Request, status

from ..auth import world_token
from ..auth.access import (
    enforce_world_token,
    enforcement_enabled,
    extract_basic_auth_user,
)
from ..engine_bridge import build_engine_config
from ..state import sessions as session_state
from ..state.world_context import load_world_context
from ..state.world_root import find_world_session, iter_worlds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/worlds")
def list_worlds(request: Request) -> list[dict]:
    """Summaries of every world for the "my worlds" picker (ADR 0002 Slice 5).

    Most-recently-played first. Each entry links to ``/w/<worldId>`` in the UI.
    Empty list when no worlds exist (the picker shows a create CTA).

    Scope note (ADR 0003): this returns *every* world on the server with no
    per-tester scoping — there are no accounts in the closed-beta model, so the
    backend has no notion of "whose world this is." That is an **accepted**
    limitation under ADR 0003's threat model ("the risk at test scale is cost
    and abuse, not data confidentiality; worlds are throwaway test data, nobody's
    secrets are in them"). The world metadata here (name, character, persona,
    turn count) is non-sensitive, and the per-world token still gates *resuming*
    a world (GET /world/{id}) — knowing a world_id is not enough to open it.
    Per-tester scoping is deferred to the open-signup/accounts phase (ADR 0003
    § "Out of scope — vision"); tracked in docs/BACKLOG.md.
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
    # Validate + canonicalize the path param up front (defense in depth + a
    # clean 404 rather than a downstream 502 on a malformed id). The MCP server
    # validates again before any removal — never trusts the backend blindly.
    try:
        world_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="world not found")

    settings = request.app.state.settings
    # ADR 0003 — a destructive, world-scoped op: require the per-world token
    # (against the canonical id above). No-op when enforcement is off.
    enforce_world_token(request, settings, world_id)
    found = find_world_session(
        settings.worlds_root, world_id, default_data_dir=settings.data_dir
    )
    session_id = found[1] if found is not None else None

    # Per-world mode: the repo dir is the source of truth, so we can tear down a
    # world even if it has no session yet (an orphan from an intro that 502'd
    # mid-creation). Legacy mode has nothing to remove without a session, so a
    # missing session is a genuine 404.
    if found is None and not settings.worlds_root:
        raise HTTPException(status_code=404, detail="world not found")

    result = engine.teardown_world(
        build_engine_config(settings), world_id=world_id, session_id=session_id
    )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"world teardown failed: {result.error}",
        )
    # git-sync reports not_found when the world dir was already absent → 404.
    if result.body.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="world not found")
    return {"worldId": world_id, "status": result.body.get("status", "removed")}


@router.get("/world/{world_id}")
def get_world(world_id: str, request: Request) -> dict:
    """The world's current session (id + metadata + turn log), for resume.

    404 when the world has no session — a bad/unknown ``world_id`` and a
    genuinely empty world are indistinguishable to a caller and get the same
    response (the id is the only secret, same posture as session lookups).
    """
    # Canonicalize the path id up front (mirrors delete_world): a clean 404 on a
    # malformed id, and the token check below runs against the same canonical
    # form the token was minted with.
    try:
        world_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="world not found")

    settings = request.app.state.settings
    # ADR 0003 — resume is world-scoped; require the per-world token (no-op when
    # enforcement is off). Checked before the lookup so existence isn't leaked
    # to an unauthorized caller. The SPA holds the token (localStorage keyed by
    # world_id) from creation; a cross-browser shared link without it can't
    # resume under enforcement — intended (the URL is no longer the sole secret).
    enforce_world_token(request, settings, world_id)
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


@router.post("/world/{world_id}/reauth")
def reauth_world(world_id: str, request: Request) -> dict:
    """Re-mint a per-world token for the basic_auth'd creator (per-tester reauth).

    The SPA calls this when a world-scoped request 401s — usually because the
    tester's localStorage was cleared (private mode, browser data wipe, fresh
    device) and the world token went with it. The edge proxy (Caddy basic_auth)
    has already authenticated the request, so we trust the username it carries
    and confirm it matches the world's stored ``creator_username``. If it does,
    we mint a fresh username-bound token and return it. If it doesn't, 403.

    **TOFU for legacy worlds.** A world created before this PR (or via the
    anonymous tailnet flow, with no basic_auth header) has no
    ``creator_username``. The first authenticated /reauth claims that slot:
    we write the requesting user onto the session JSON and proceed. Acceptable
    for the closed cohort (≤10 trusted testers); risky at open-signup scale,
    so the claim is logged for audit. All TOFU writes go through fs-manager so
    concurrent reauths on the same legacy world serialize on the per-world
    cross-process lock (no double-claim).
    """
    # Canonicalize the path id (matches delete_world / get_world) — clean 404
    # on a malformed id, and the token we mint is bound to the canonical form.
    try:
        world_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="world not found")

    settings = request.app.state.settings

    # Reauth is meaningless when no token system is configured — the SPA only
    # calls it on a 401, which can't happen with enforcement off. 404 keeps the
    # surface tight and the response shape uniform (no "null token" half-state).
    if not enforcement_enabled(settings):
        raise HTTPException(status_code=404, detail="reauth unavailable")

    username = extract_basic_auth_user(request)
    if not username:
        # No basic_auth identity → we can't bind a new token to anyone. 401 so
        # the edge proxy (or the browser) prompts for credentials, matching the
        # missing-token semantics on the world-scoped routes.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing basic_auth credentials",
        )

    found = find_world_session(
        settings.worlds_root, world_id, default_data_dir=settings.data_dir
    )
    if found is None:
        raise HTTPException(status_code=404, detail="world not found")
    data_dir, session_id = found
    session = session_state.read_session(data_dir, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="world not found")

    stored_creator = session.creator_username or ""

    if stored_creator:
        if stored_creator != username:
            # Owner mismatch — the world belongs to a different tester. Never
            # leak the actual creator's name; just refuse.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="not the world creator",
            )
    else:
        # TOFU: legacy world (or anonymous-creation world) — first
        # authenticated reauth claims the creator slot. Write back through the
        # engine → fs-manager → git-sync path so the claim is committed to the
        # world's repo (and serialized against any concurrent /reauth on the
        # same world by the per-world filelock).
        session.creator_username = username
        engine_config = build_engine_config(settings)
        write_result = session_state.write_session(
            engine_config,
            session,
            log_entry=f"[Reauth] creator slot claimed by {username}",
            turn_number=len(session.turns or []),
        )
        if not write_result.ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"failed to persist creator claim: {write_result.error}",
            )
        # Commit the claim through git-sync so the TOFU write enters the
        # world's git history. Symmetric with session.py's create-and-commit:
        # an audit gap on a security-relevant mutation (who owns this world)
        # would be exactly the kind of silent loss the per-world repo is
        # supposed to prevent. (gemini-high on PR #125.) Failure here is
        # logged but not fatal — the on-disk claim has already landed and
        # subsequent reauths will read it; refusing the response would leave
        # the world stuck without ANY token. The session-create path makes
        # the same trade-off (see session.py § "Fire-and-log").
        commit_result = engine.commit_snapshot(
            engine_config,
            session_id=session.session_id,
            turn_number=len(session.turns or []),
            summary=f"[Reauth] creator slot claimed by {username}",
            world_id=world_id,
        )
        if not commit_result.ok:
            logger.warning(
                "commit_snapshot failed on TOFU creator-claim for world %s: %s",
                world_id,
                commit_result.error,
            )
        logger.info(
            "reauth TOFU: world %s creator slot claimed by %s",
            world_id,
            username,
        )

    token = world_token.mint(
        world_id,
        secret=settings.session_token_secret,
        ttl_seconds=settings.session_token_ttl_seconds,
        username=username,
    )
    return {"worldId": world_id, "token": token}

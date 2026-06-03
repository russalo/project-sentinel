"""Read-only endpoints for browsing recorded sessions and exporting them as
training data. Backs the ``/data`` browser page.

    GET /api/sessions                                   → session summaries
    GET /api/sessions/{id}                              → full session (turns)
    GET /api/sessions/{id}/export?format=schema|chatlog → downloadable dataset

Reuses ``backend.datasets`` for the export shapes (same builders the CLI
``just export-training-data`` recipe uses).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from .. import datasets as ds
from ..state import sessions as session_state
from ..state.world_root import find_session_data_dir, iter_session_data_dirs

router = APIRouter(prefix="/api")

_SESSIONS_REL = "state/core/sessions"


def _safe_mtime(path) -> float:
    """Modification time, or 0 if the file vanished between glob and stat."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _session_to_dict(session: session_state.Session) -> dict:
    """The plain dict shape backend.datasets builders expect."""
    return {
        "session_id": session.session_id,
        "world_name": session.world_name,
        "dm_persona_name": session.dm_persona_name,
        "player_character_name": session.player_character_name,
        "turns": session.turns,
    }


@router.get("/sessions")
def list_sessions(request: Request) -> list[dict]:
    """Summaries of every recorded session (no turn bodies).

    Scans the shared tree, or — once SENTINEL_WORLDS_ROOT is set (ADR 0002
    Slice 3) — every provisioned world's sessions dir, so the browser keeps
    listing all sessions across worlds after the cutover.
    """
    settings = request.app.state.settings
    candidates = []
    for data_dir in iter_session_data_dirs(
        settings.worlds_root, default_data_dir=settings.data_dir
    ):
        sessions_dir = data_dir / _SESSIONS_REL
        if sessions_dir.is_dir():
            candidates.extend(sessions_dir.glob("*.json"))
    summaries: list[dict] = []
    # Most-recently-modified first, so fresh sessions surface at the top —
    # across all worlds, not just within one.
    for path in sorted(candidates, key=_safe_mtime, reverse=True):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        turns = raw.get("turns") if isinstance(raw.get("turns"), list) else []
        summaries.append(
            {
                # The filename stem is the canonical id — read_session() keys
                # off it, so using the JSON field could yield an id whose
                # detail/export links 404.
                "sessionId": path.stem,
                "worldName": raw.get("world_name", ""),
                "persona": raw.get("dm_persona_name", ""),
                "character": raw.get("player_character_name", ""),
                "turnCount": len(turns),
                "startedAt": raw.get("started_at", ""),
            }
        )
    return summaries


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    """Full session with its turn log, for the detail view."""
    settings = request.app.state.settings
    data_dir = find_session_data_dir(
        settings.worlds_root, session_id, default_data_dir=settings.data_dir
    )
    session = (
        session_state.read_session(data_dir, session_id)
        if data_dir is not None
        else None
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        # The requested id is the canonical (filename) one, consistent with
        # list_sessions; the JSON body's session_id could disagree.
        "sessionId": session_id,
        "worldName": session.world_name,
        "persona": session.dm_persona_name,
        "character": session.player_character_name,
        "startedAt": session.started_at,
        "turns": session.turns,
    }


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: str,
    request: Request,
    format: str = Query("schema", pattern="^(schema|chatlog)$"),
) -> Response:
    """Download a session as a training artifact (schema JSONL or chatlog)."""
    settings = request.app.state.settings
    data_dir = find_session_data_dir(
        settings.worlds_root, session_id, default_data_dir=settings.data_dir
    )
    session = (
        session_state.read_session(data_dir, session_id)
        if data_dir is not None
        else None
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    session_dict = _session_to_dict(session)

    if format == "schema":
        examples, _ = ds.build_schema_examples(session_dict)
        body = "".join(json.dumps(e) + "\n" for e in examples)
        filename = f"{session_id}.schema.jsonl"
        media_type = "application/x-ndjson"
    else:  # chatlog (the only other value the pattern allows)
        body = ds.build_chatlog(session_dict)
        filename = f"{session_id}.chatlog.md"
        media_type = "text/markdown"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

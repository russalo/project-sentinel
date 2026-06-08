"""Session metadata management.

Session state lives at ``data/state/core/sessions/<session_id>.json``
per ADR 0001. This module:

- Reads a session file (``read_session``) — used by the stream handler
  to look up the current world context and turn counter
- Builds a session-file payload and dispatches it via the engine →
  fs-manager path — used by the session-creation handler and the
  turn-append path inside the stream handler
- Appends a turn to an existing session, again via engine dispatch

Nothing here writes to disk directly. Every mutation goes through
``engine.apply_world_update`` so the schema gate stays honored.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import engine


_SESSIONS_REL = Path("state/core/sessions")


def _require_uuid(session_id: str) -> None:
    """Security boundary against path traversal via user-supplied IDs.

    Every session file path is built from the session_id, which on
    the read side (`read_session`, and by extension the stream
    handler) comes from untrusted request bodies. If a client sends
    e.g. ``sessionId="../lore/core/codex/some_file"``, a naive
    ``sessions/<id>.json`` join escapes the sessions directory and
    could read arbitrary JSON files elsewhere in ``data/``.

    UUID format is strict enough to reject anything with slashes,
    dots, or control characters. It also matches how session IDs
    are generated (``uuid.uuid4()`` in the session-creation handler),
    so legitimate requests always pass.
    """
    try:
        uuid.UUID(session_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"session_id is not a valid UUID: {session_id!r}") from exc


@dataclass
class Session:
    """In-memory snapshot of a session file.

    Fields mirror the JSON shape written to disk. ``turns`` is the
    full turn log — v1.0 sessions are short enough that keeping them
    in a single file is fine.
    """

    session_id: str
    world_name: str
    started_at: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    active: bool = True
    # Speaker identities, captured at creation so recorded transcripts
    # can be labelled with who actually spoke (the player's character and
    # the active DM persona) rather than generic "Player"/"DM".
    player_character_name: str = ""
    player_character_class: str = ""
    dm_persona_name: str = ""
    # Persona id + selected mood (ADR 0002 Slice 5) so a resumed world restores
    # the full persona, not just its display name. The persona's available-mood
    # *list* comes from preset metadata not stored here (tracked follow-up).
    persona_id: str = ""
    mood: str = ""
    # The world this session belongs to (ADR 0002). Additive in this slice —
    # threaded into git-sync commit messages; per-world data isolation lands
    # in a later slice. Empty on legacy sessions written before world_id.
    world_id: str = ""
    # Tester username captured from ``Authorization: Basic`` at world creation
    # (per-tester reauth, 2026-06-08). The world's /reauth endpoint uses this
    # to confirm a re-mint request comes from the creator. Empty on sessions
    # created without basic_auth (the anonymous tailnet flow) and on legacy
    # sessions written before this field existed — legacy worlds get TOFU on
    # first authenticated reauth (the creator slot is claimed atomically).
    creator_username: str = ""


def session_file_path(data_dir: Path, session_id: str) -> Path:
    """Construct the absolute path of a session JSON file.

    Validates ``session_id`` is a UUID via ``_require_uuid``; raises
    ``ValueError`` otherwise. Callers that accept session IDs from
    untrusted input (like ``read_session``) should catch the
    exception and treat it as "session not found."
    """
    _require_uuid(session_id)
    return data_dir / _SESSIONS_REL / f"{session_id}.json"


def read_session(data_dir: Path, session_id: str) -> Session | None:
    """Load a session file from disk.

    Returns None if:
      - session_id is not a valid UUID (path traversal defense)
      - the file doesn't exist on disk
      - the file is unreadable or contains malformed JSON
      - the file's top-level JSON is not an object

    All four cases are treated the same way (return None) because
    the caller's response is the same: reject the request as
    "session not found or inactive."
    """
    try:
        path = session_file_path(data_dir, session_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return Session(
        session_id=raw.get("session_id", session_id),
        world_name=raw.get("world_name", ""),
        started_at=raw.get("started_at", ""),
        turns=raw.get("turns", []) if isinstance(raw.get("turns"), list) else [],
        active=bool(raw.get("active", True)),
        player_character_name=raw.get("player_character_name", ""),
        player_character_class=raw.get("player_character_class", ""),
        dm_persona_name=raw.get("dm_persona_name", ""),
        persona_id=raw.get("persona_id", ""),
        mood=raw.get("mood", ""),
        world_id=raw.get("world_id", ""),
        creator_username=raw.get("creator_username", ""),
    )


def _build_session_payload(session: Session, log_entry: str, turn_number: int) -> dict:
    """Produce an apply_world_update payload that writes a session file.

    Session files always live under ``data/state/core/sessions/`` per
    ADR 0001, which is a namespace-gated path. Authorization is the trusted
    ``namespace`` query param the dispatcher sets (default "core"; see
    ``engine.apply_world_update``), NOT a field in this body — so it is
    intentionally absent here (red-team #7). Community pack runtimes (when they
    exist) will need a different write path entirely — session files are a core
    concept.
    """
    return {
        "session_id": session.session_id,
        "log_entry": log_entry,
        "updates": [
            {
                "target_file": f"data/state/core/sessions/{session.session_id}.json",
                "operation": "update",
                "data": {
                    "session_id": session.session_id,
                    "world_name": session.world_name,
                    "started_at": session.started_at,
                    "turns": session.turns,
                    "active": session.active,
                    "player_character_name": session.player_character_name,
                    "player_character_class": session.player_character_class,
                    "dm_persona_name": session.dm_persona_name,
                    "persona_id": session.persona_id,
                    "mood": session.mood,
                    "world_id": session.world_id,
                    "creator_username": session.creator_username,
                },
            }
        ],
        "metadata": {
            "agent": "orchestrator",
            "turn_number": turn_number,
        },
    }


def write_session(
    config: engine.Config,
    session: Session,
    log_entry: str,
    turn_number: int,
) -> engine.DispatchResult:
    """Serialize a session to disk via the engine → fs-manager path.

    Returns the DispatchResult so callers can decide how to react to
    fs-manager rejections (typically: log and continue, since the
    narrative has already been streamed to the player).
    """
    payload = _build_session_payload(
        session, log_entry=log_entry, turn_number=turn_number
    )
    # Route the session-file write to the session's own world tree (ADR 0002);
    # None → legacy shared root when the session predates world_id.
    return engine.apply_world_update(config, payload, world_id=session.world_id or None)

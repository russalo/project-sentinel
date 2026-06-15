"""System messages — operator-to-cohort communication channel (RFC 0002).

One JSON file per message under ``data/state/core/system_messages/<id>.json``,
matching the ADR 0001 canonical-state-on-disk pattern. Reads + writes go
through this module; the routes layer (``backend/routes/system_messages.py``)
calls the helpers below and handles HTTP semantics.

Schema per message::

    {
      "id":           "<uuid>",
      "published_at": "ISO-8601",
      "title":        "string",
      "body":         "minimal-markdown string",
      "category":     "info | warning | release | maintenance",
      "pinned":       false,
      "expires_at":   "ISO-8601 | null",
      "deleted_at":   "ISO-8601 | null"
    }

The active feed (``list_active()``) filters out soft-deleted + expired
messages and sorts pinned-first, then by ``published_at`` descending.

Storage is direct-to-disk (not through fs-manager) because system messages
are operator-controlled, not LLM-emitted — they have no schema-gate concern,
no per-world routing, and no cross-process write contention beyond what the
filesystem itself serializes. (The fs-manager + git-sync path is for the
world-state writes the engine generates; system messages are out-of-band.)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


VALID_CATEGORIES = {"info", "warning", "release", "maintenance"}
_SYSTEM_MESSAGES_REL = Path("state/core/system_messages")


@dataclass
class SystemMessage:
    """In-memory snapshot of a message file. The JSON shape matches the
    fields below verbatim; ``to_dict`` produces the wire shape served by
    the API."""

    id: str
    published_at: str
    title: str
    body: str
    category: str = "info"
    pinned: bool = False
    expires_at: Optional[str] = None
    deleted_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "published_at": self.published_at,
            "title": self.title,
            "body": self.body,
            "category": self.category,
            "pinned": self.pinned,
            "expires_at": self.expires_at,
            "deleted_at": self.deleted_at,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "SystemMessage":
        return cls(
            id=raw["id"],
            published_at=raw["published_at"],
            title=raw.get("title", ""),
            body=raw.get("body", ""),
            category=raw.get("category", "info"),
            pinned=bool(raw.get("pinned", False)),
            expires_at=raw.get("expires_at"),
            deleted_at=raw.get("deleted_at"),
        )


def _messages_dir(data_dir: Path) -> Path:
    return data_dir / _SYSTEM_MESSAGES_REL


def _require_uuid(message_id: str) -> None:
    """Path-traversal defense — message IDs are interpolated into file
    paths, so reject anything that isn't a well-formed UUID before any
    disk operation. Mirrors the pattern used for ``session_id`` in
    ``backend/state/sessions.py``."""
    try:
        uuid.UUID(message_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"message_id is not a valid UUID: {message_id!r}") from exc


def _message_path(data_dir: Path, message_id: str) -> Path:
    _require_uuid(message_id)
    return _messages_dir(data_dir) / f"{message_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC ``datetime``.
    Returns None for unparseable input. Accepts the ``Z`` suffix
    (which ``datetime.fromisoformat`` only accepts on 3.11+; we normalize
    it to ``+00:00`` for safety). Naive datetimes are assumed UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_expired(message: SystemMessage, now: datetime) -> bool:
    """Compare ``expires_at`` against ``now`` as parsed datetimes — not
    lexicographic strings. The string compare path was fragile across
    suffix variants (``Z`` vs ``+00:00``) and fractional seconds:
    ``"2026-06-14T20:00:00.123456+00:00" >= "2026-06-14T20:00:00Z"``
    evaluates False because ``.`` (46) < ``Z`` (90)."""
    if not message.expires_at:
        return False
    expiry = _parse_iso(message.expires_at)
    if expiry is None:
        # Unparseable expires_at — treat as never-expiring so a malformed
        # timestamp can't silently hide a message. The admin UI surfaces
        # the raw string for operator review either way.
        return False
    return now >= expiry


def read(data_dir: Path, message_id: str) -> Optional[SystemMessage]:
    """Load a single message from disk. Returns None for unknown IDs,
    malformed JSON, or non-UUID IDs (the latter being a path-traversal
    defense)."""
    try:
        path = _message_path(data_dir, message_id)
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
    try:
        return SystemMessage.from_dict(raw)
    except (KeyError, TypeError):
        return None


def list_all(data_dir: Path) -> list[SystemMessage]:
    """Every message on disk, regardless of deleted/expired state. Used
    by the admin UI which surfaces deleted messages in a separate
    section."""
    dir_path = _messages_dir(data_dir)
    if not dir_path.exists():
        return []
    out: list[SystemMessage] = []
    for f in dir_path.iterdir():
        if not f.is_file() or f.suffix != ".json":
            continue
        msg = read(data_dir, f.stem)
        if msg is not None:
            out.append(msg)
    return out


def list_active(data_dir: Path) -> list[SystemMessage]:
    """The cohort-facing feed: filters out soft-deleted + expired,
    sorts pinned-first then by ``published_at`` descending."""
    now = datetime.now(timezone.utc)
    active = [
        m
        for m in list_all(data_dir)
        if m.deleted_at is None and not _is_expired(m, now)
    ]
    # Stable sort: primary by pinned (True first), secondary by
    # published_at desc. Python's sort is stable, so apply secondary first.
    active.sort(key=lambda m: m.published_at, reverse=True)
    active.sort(
        key=lambda m: not m.pinned
    )  # False sorts before True; pinned=True wants to come first → invert
    return active


def create(
    data_dir: Path,
    *,
    title: str,
    body: str,
    category: str = "info",
    pinned: bool = False,
    expires_at: Optional[str] = None,
) -> SystemMessage:
    """Mint a new message + persist it. Server-assigns id + published_at.

    Validates category against the enum (raises ValueError on unknown).
    Empty title and empty body are accepted at the storage layer — the
    routes layer should reject them at the HTTP boundary so the operator
    gets a 400 instead of a silent no-op-feeling-create.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category {category!r} not in {sorted(VALID_CATEGORIES)}")
    message = SystemMessage(
        id=str(uuid.uuid4()),
        published_at=_now_iso(),
        title=title,
        body=body,
        category=category,
        pinned=bool(pinned),
        expires_at=expires_at,
        deleted_at=None,
    )
    _messages_dir(data_dir).mkdir(parents=True, exist_ok=True)
    path = _message_path(data_dir, message.id)
    path.write_text(json.dumps(message.to_dict(), indent=2), encoding="utf-8")
    return message


def update(
    data_dir: Path,
    message_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    category: Optional[str] = None,
    pinned: Optional[bool] = None,
    expires_at: Optional[str] = None,
    clear_expires_at: bool = False,
) -> Optional[SystemMessage]:
    """Partial update — None means "don't change this field." To CLEAR
    ``expires_at`` (turning a previously-expiring message into a permanent
    one) pass ``clear_expires_at=True`` since None-the-sentinel and
    None-the-cleared-value are otherwise indistinguishable.

    Returns the updated message, or None if not found. Raises ValueError
    on unknown category."""
    existing = read(data_dir, message_id)
    if existing is None:
        return None
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError(f"category {category!r} not in {sorted(VALID_CATEGORIES)}")
    if title is not None:
        existing.title = title
    if body is not None:
        existing.body = body
    if category is not None:
        existing.category = category
    if pinned is not None:
        existing.pinned = bool(pinned)
    if clear_expires_at:
        existing.expires_at = None
    elif expires_at is not None:
        existing.expires_at = expires_at
    path = _message_path(data_dir, message_id)
    path.write_text(json.dumps(existing.to_dict(), indent=2), encoding="utf-8")
    return existing


def soft_delete(data_dir: Path, message_id: str) -> Optional[SystemMessage]:
    """Mark a message deleted by setting ``deleted_at``. Returns the
    updated message (with deleted_at set), or None if not found. The
    message stays on disk so the admin UI can show it under
    "Deleted" — this is the audit-friendly default the RFC commits to."""
    existing = read(data_dir, message_id)
    if existing is None:
        return None
    existing.deleted_at = _now_iso()
    path = _message_path(data_dir, message_id)
    path.write_text(json.dumps(existing.to_dict(), indent=2), encoding="utf-8")
    return existing

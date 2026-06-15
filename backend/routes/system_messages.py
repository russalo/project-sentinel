"""System messages routes — operator-to-cohort channel (RFC 0002).

Four endpoints:

  - ``GET    /api/system-messages``                — cohort-facing feed
  - ``POST   /api/admin/system-messages``          — operator: create
  - ``PATCH  /api/admin/system-messages/{id}``     — operator: update
  - ``DELETE /api/admin/system-messages/{id}``     — operator: soft-delete

The admin endpoints carry NO server-side auth: they rely on the gate
topology (the public Caddyfile 404s ``/api/admin/*`` per the invariant
in ``tests/test_caddy_invariant.py``). On tailnet the same backend on
``:8001`` serves all four. Russell's call 2026-06-14 per RFC 0002:
tailnet membership is the credential.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..state import system_messages as sm_state

# Category enum stays in sync with ``sm_state.VALID_CATEGORIES``.
# Pydantic's ``Literal`` rejects unknown values at the schema gate with a
# 422 — saves the state layer from raising ValueError on a 400.
MessageCategory = Literal["info", "warning", "release", "maintenance"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system-messages"])


# ── Request bodies ─────────────────────────────────────────────────


class CreateMessageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    category: MessageCategory = "info"
    pinned: bool = False
    expires_at: Optional[str] = None


class UpdateMessageRequest(BaseModel):
    """Every field is optional — the route layer applies only what's set.
    ``clear_expires_at`` is the explicit sentinel for "remove the expiry"
    since None-the-not-set and None-the-cleared-value are otherwise
    indistinguishable across the JSON wire."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    body: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    category: Optional[MessageCategory] = None
    pinned: Optional[bool] = None
    expires_at: Optional[str] = None
    clear_expires_at: bool = False


# ── Public read endpoint ───────────────────────────────────────────


@router.get("/system-messages")
def list_messages(request: Request) -> dict:
    """Cohort-facing feed: pinned-first, then newest-first. Soft-deleted
    + expired messages are filtered out. Returns ``{messages: [...]}``."""
    settings = request.app.state.settings
    active = sm_state.list_active(settings.data_dir)
    return {"messages": [m.to_dict() for m in active]}


# ── Admin (tailnet-only) endpoints ─────────────────────────────────


@router.post("/admin/system-messages")
def create_message(request: Request, body: CreateMessageRequest) -> dict:
    settings = request.app.state.settings
    try:
        msg = sm_state.create(
            settings.data_dir,
            title=body.title,
            body=body.body,
            category=body.category,
            pinned=body.pinned,
            expires_at=body.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    logger.info("system-message created: id=%s title=%r", msg.id, msg.title[:50])
    return msg.to_dict()


@router.patch("/admin/system-messages/{message_id}")
def update_message(
    message_id: str, request: Request, body: UpdateMessageRequest
) -> dict:
    settings = request.app.state.settings
    try:
        updated = sm_state.update(
            settings.data_dir,
            message_id,
            title=body.title,
            body=body.body,
            category=body.category,
            pinned=body.pinned,
            expires_at=body.expires_at,
            clear_expires_at=body.clear_expires_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="message not found")
    logger.info("system-message updated: id=%s", message_id)
    return updated.to_dict()


@router.delete("/admin/system-messages/{message_id}")
def delete_message(message_id: str, request: Request) -> dict:
    """Soft delete — sets ``deleted_at``, leaves the file on disk.
    The admin UI can still see it under "Deleted"; the public feed
    filters it out."""
    settings = request.app.state.settings
    deleted = sm_state.soft_delete(settings.data_dir, message_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="message not found")
    logger.info("system-message soft-deleted: id=%s", message_id)
    return deleted.to_dict()


# ── Admin-side list (sees deleted + expired too) ──────────────────


@router.get("/admin/system-messages")
def list_all_messages(request: Request) -> dict:
    """Admin-side list — surfaces ALL messages including soft-deleted +
    expired ones so the admin UI can show them in a "Deleted" section
    + warn about upcoming/elapsed expiries. Sorted newest-first
    (no pinning sort here — the admin UI cares about temporal order)."""
    settings = request.app.state.settings
    all_msgs = sm_state.list_all(settings.data_dir)
    all_msgs.sort(key=lambda m: m.published_at, reverse=True)
    return {"messages": [m.to_dict() for m in all_msgs]}

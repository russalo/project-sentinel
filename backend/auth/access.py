"""Per-world access enforcement (ADR 0003 Slice A + per-tester reauth).

A thin layer over :mod:`backend.auth.world_token`: decide whether token
enforcement is on (driven purely by whether a signing secret is configured)
and, when on, require a valid ``X-Sentinel-World-Token`` header for the world.

Handlers call :func:`enforce_world_token` **after** they resolve the
authoritative ``world_id`` — from the session for ``/stream``, from the path for
``/world`` — so the token is always checked against the server's notion of the
world, never a client-asserted one. (A valid token for world A paired with a
session in world B therefore still fails: the check uses ``session.world_id``.)

Per-tester reauth (2026-06-08) added :func:`extract_basic_auth_user`, used by
session creation to bind a fresh token to the basic_auth identity, and by the
``/api/world/{id}/reauth`` route to confirm a re-mint request comes from the
world's creator. Edge proxies (Caddy basic_auth) have already authenticated
the password by the time the request reaches the backend; we trust the username
the header carries.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import HTTPException, Request, status

from ..config import Settings
from . import world_token

WORLD_TOKEN_HEADER = "X-Sentinel-World-Token"


def enforcement_enabled(settings: Settings) -> bool:
    """Token enforcement is on iff a signing secret is configured."""
    return bool(settings.session_token_secret)


def issue_token(
    settings: Settings, world_id: str, *, username: str | None = None
) -> str | None:
    """Mint a token for a world, or ``None`` when enforcement is off.

    Returned on the session-create response and stored client-side keyed by
    world_id. When ``username`` is provided (per-tester reauth), the resulting
    token is bound to that tester — a subsequent verify against a different
    username fails. ``username=None`` produces a legacy unbound token.
    """
    if not enforcement_enabled(settings):
        return None
    return world_token.mint(
        world_id,
        secret=settings.session_token_secret,
        ttl_seconds=settings.session_token_ttl_seconds,
        username=username,
    )


def enforce_world_token(request: Request, settings: Settings, world_id: str) -> None:
    """Raise 401/403 unless the request carries a valid token for ``world_id``.

    No-op when enforcement is disabled (no secret) — the anonymous tailnet flow.
    401 when the header is absent, 403 when it is present but invalid/expired/
    bound to a different world.
    """
    if not enforcement_enabled(settings):
        return
    token = request.headers.get(WORLD_TOKEN_HEADER)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing world session token",
        )
    if not world_token.verify(token, world_id, secret=settings.session_token_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid world session token",
        )


def extract_basic_auth_user(request: Request) -> str | None:
    """Read the username from an ``Authorization: Basic ...`` header.

    Returns ``None`` when the header is missing, isn't a Basic scheme, isn't
    well-formed base64, isn't valid UTF-8, has no ``:`` delimiter, or has an
    empty username portion. We do NOT validate the password — that's the edge
    proxy's job (Caddy basic_auth has already authenticated by the time the
    request reaches us; we trust the username it carries).

    Never raises — every malformed shape is simply ``None``.
    """
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(parts[1], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    username = decoded.split(":", 1)[0]
    return username or None

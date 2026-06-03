"""Stateless per-world session tokens (ADR 0003 Slice A).

A token authorizes turns / resume / delete on **one specific world** without
any server-side session store: it is an HMAC-SHA256 over the ``world_id`` and an
expiry, keyed by a secret from the environment. Verification recomputes the MAC
and compares in constant time, so a token minted for world A cannot be replayed
against world B, and an expired token is rejected.

Token shape (ASCII, header-safe): ``"<expiry_epoch>.<base64url(mac)>"``.

Enforcement is opt-in and lives in :mod:`backend.auth.access`: it is only
meaningful when a secret is configured (``SENTINEL_SESSION_TOKEN_SECRET``). With
no secret the backend mints no tokens and ``verify`` is never reached — the
anonymous tailnet flow is unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid


def _b64(raw: bytes) -> str:
    """URL-safe base64 without padding (keeps the token header-clean)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign(secret: str, world_id: str, expiry: int) -> str:
    msg = f"{world_id}.{expiry}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return _b64(mac)


def mint(
    world_id: str,
    *,
    secret: str,
    ttl_seconds: int,
    _now: float | None = None,
) -> str:
    """Mint a token authorizing ``world_id`` for ``ttl_seconds``.

    ``world_id`` must be a valid UUID — it is the sole subject the MAC binds to,
    so a non-UUID id would let the path layer and the token disagree. Raises
    ``ValueError`` on a bad id (fail at mint, not at verify). The id is **not**
    re-canonicalized here: callers mint with the canonical ``str(uuid4())`` they
    already hold, and verify against the canonicalized path/session world_id.
    """
    uuid.UUID(world_id)
    now = time.time() if _now is None else _now
    expiry = int(now) + int(ttl_seconds)
    return f"{expiry}.{_sign(secret, world_id, expiry)}"


def verify(
    token: str,
    world_id: str,
    *,
    secret: str,
    _now: float | None = None,
) -> bool:
    """True iff ``token`` is a well-formed, unexpired token for ``world_id``.

    Never raises — any malformed input is simply an invalid token (False), so
    callers map a falsy result straight to 403 without catching.
    """
    if not token:
        return False
    try:
        expiry_str, sig = token.split(".", 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return False
    now = time.time() if _now is None else _now
    if now > expiry:
        return False
    # Constant-time compare over the recomputed MAC for this exact world_id.
    return hmac.compare_digest(sig, _sign(secret, world_id, expiry))

"""Stateless per-world session tokens (ADR 0003 Slice A + per-tester reauth).

A token authorizes turns / resume / delete on **one specific world** without
any server-side session store: it is an HMAC-SHA256 over the ``world_id`` and an
expiry (and optionally a username for per-tester binding), keyed by a secret
from the environment. Verification recomputes the MAC and compares in constant
time, so a token minted for world A cannot be replayed against world B, and an
expired token is rejected.

Two wire shapes, both accepted concurrently so a redeploy never invalidates an
already-issued token mid-flight:

  - Legacy (unbound):     ``"<expiry>.<base64url(mac)>"``
    HMAC payload:         ``f"{world_id}.{expiry}"``
  - New (username-bound): ``"<expiry>.<username>.<base64url(mac)>"``
    HMAC payload:         ``f"{world_id}.{username}.{expiry}"``

The shapes are NOT interchangeable on the HMAC side — a legacy token will not
verify against a new-shape recomputation and vice versa — but the wire shape
self-describes which one was minted, so ``verify()`` reconstructs the correct
payload without out-of-band hints. (No basic_auth header reaches world-scoped
routes; only the /reauth route does. The token carries everything verify needs.)

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


def _sign(secret: str, world_id: str, expiry: int, username: str | None) -> str:
    """HMAC-SHA256 over the world_id, optional username, and expiry.

    Two distinct payload shapes — never a "username defaults to empty string"
    fallback, since ``f"{world_id}..{expiry}"`` with empty middle differs from
    ``f"{world_id}.{expiry}"`` by the extra delimiter, so an empty-string
    fallback in the new shape would NOT recover the legacy HMAC. PR #117's
    original spec tripped on this (codex P2); the explicit two-branch split
    here is the durable fix.
    """
    if username is None:
        msg = f"{world_id}.{expiry}".encode("utf-8")
    else:
        msg = f"{world_id}.{username}.{expiry}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return _b64(mac)


def mint(
    world_id: str,
    *,
    secret: str,
    ttl_seconds: int,
    username: str | None = None,
    _now: float | None = None,
) -> str:
    """Mint a token authorizing ``world_id`` for ``ttl_seconds``.

    ``world_id`` must be a valid UUID — it is the primary subject the MAC binds
    to. The id is **canonicalized** (``str(uuid.UUID(...))``) before signing so
    that any spelling of the same UUID (case, braces, urn) mints and verifies
    consistently; a non-UUID raises ``ValueError`` (fail at mint, not at verify).

    ``username`` (per-tester reauth) is optional. When provided, the resulting
    token additionally binds to that username — a subsequent ``verify()`` only
    succeeds against the same username. When omitted, the token is unbound
    (legacy shape) and verifies for any caller who holds it. The wire format
    self-describes which shape was minted, so verify needs no out-of-band hint.
    """
    canonical_id = str(uuid.UUID(world_id))
    now = time.time() if _now is None else _now
    # Truncate once, after adding the ttl, so a fractional `now` doesn't shave
    # up to ~1s off the intended lifetime.
    expiry = int(now + ttl_seconds)
    sig = _sign(secret, canonical_id, expiry, username)
    if username is None:
        # Legacy wire: "<expiry>.<mac>"
        return f"{expiry}.{sig}"
    # New wire: "<expiry>.<username>.<mac>"
    return f"{expiry}.{username}.{sig}"


def verify(
    token: str,
    world_id: str,
    *,
    secret: str,
    _now: float | None = None,
) -> bool:
    """True iff ``token`` is a well-formed, unexpired token for ``world_id``.

    Accepts both wire shapes — the dot-count alone is unreliable because a
    free-form username can itself contain ``.``, so the parser **peels from
    the outside in**: the MAC is always base64url (no dots in the alphabet),
    so the last dot terminates the MAC; the first dot terminates the expiry;
    anything in between is the username (possibly with dots), or empty if
    the token is the legacy 2-part shape.

    Never raises — any malformed input is simply an invalid token (False), so
    callers map a falsy result straight to 401/403 without catching.
    """
    if not token:
        return False
    # Canonicalize the same way mint() does; a non-UUID world_id is simply
    # invalid (False), never an exception.
    try:
        canonical_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError):
        return False
    # Peel from outside in (see docstring). At minimum the token must contain
    # one dot; if not, it can't be either shape.
    if "." not in token:
        return False
    body, sig = token.rsplit(".", 1)
    if not sig:
        return False
    if "." not in body:
        # Legacy shape: body == "<expiry>", sig == "<mac>"
        expiry_str = body
        username: str | None = None
    else:
        # New shape: body == "<expiry>.<username-which-may-contain-dots>"
        expiry_str, raw_username = body.split(".", 1)
        # An empty middle is illegal in the new shape — that pattern
        # (``f"{world_id}..{expiry}"``) was the codex P2 footgun PR #117 tripped
        # on, where empty-string was treated as "same as legacy" but produced
        # a different HMAC payload. We never mint it, and verify rejects it.
        if not raw_username:
            return False
        username = raw_username
    try:
        expiry = int(expiry_str)
    except (ValueError, TypeError):
        return False
    now = time.time() if _now is None else _now
    if now > expiry:
        return False
    # Constant-time compare over the recomputed MAC for this exact world_id +
    # username shape.
    return hmac.compare_digest(sig, _sign(secret, canonical_id, expiry, username))

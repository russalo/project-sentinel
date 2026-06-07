"""POST /api/feedback — in-product feedback submission.

Captures structured feedback from alpha testers (subject, body, category,
platform, browser + optional severity/repro/handle) plus auto-extracted
context (worldId, sessionId, userAgent, viewport, currentUrl, bundleHash)
and writes a JSON file to ``<SENTINEL_FEEDBACK_ROOT>/YYYY-MM-DD/<ts>-<id>.json``.

Disabled when ``settings.feedback_root`` is unset → returns HTTP 503.
Per-IP rate-limited via the shared ``RateLimiter`` when
``rl_feedback_per_hour > 0`` (0 = unlimited; don't ship 0 to prod).

Auth: NOT per-world-token gated. A tester may need to report inability to
enter a session — basic_auth at the Caddy edge is the only gate. The
endpoint itself is loopback-only on origin-core; Caddy at the edge routes
this through the same `/api/*` reverse_proxy block.

Storage shape — atomic write, never partial files visible to readers:
1. Generate a short UUID-derived id (8 chars) for the filename
2. Write to ``<root>/YYYY-MM-DD/<ts>-<id>.json.tmp``
3. ``os.replace()`` to the final ``.json`` name (POSIX-atomic on same FS)

The on-disk JSON is the raw stream; the human-curated view lives in
``docs/ALPHA_FEEDBACK.md`` after periodic triage.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import Settings
from ..ratelimit import RateLimiter, client_ip

logger = logging.getLogger(__name__)

router = APIRouter()


# Length limits — match the BACKLOG spec. Generous enough for real feedback,
# tight enough to keep submissions from being abuse payloads.
_SUBJECT_MAX = 140
_BODY_MAX = 4000
_FIELD_FREETEXT_MAX = 80  # platform, browser, handle, currentUrl, userAgent
_USER_AGENT_MAX = 500  # UAs can be long
_VIEWPORT_MAX = 16  # "WWWWxHHHH" worst case ~ 9 chars
_BUNDLE_HASH_MAX = 32

_VALID_CATEGORIES = {"bug", "ui-ux", "general", "feature"}
_VALID_SEVERITIES = {"low", "medium", "high"}
_VALID_REPRO = {"yes", "no", "sometimes"}


class FeedbackSubmission(BaseModel):
    """Incoming JSON shape — what the SPA's `pages/Feedback.jsx` POSTs."""

    # Required, user-entered
    subject: str = Field(min_length=1, max_length=_SUBJECT_MAX)
    body: str = Field(min_length=1, max_length=_BODY_MAX)
    category: Literal["bug", "ui-ux", "general", "feature"]
    platform: str = Field(max_length=_FIELD_FREETEXT_MAX)
    browser: str = Field(max_length=_FIELD_FREETEXT_MAX)

    # Optional, user-entered
    severity: Literal["low", "medium", "high"] | None = None
    reproducible: Literal["yes", "no", "sometimes"] | None = None
    handle: str | None = Field(default=None, max_length=_FIELD_FREETEXT_MAX)

    # Optional, auto-captured by SPA (null when not available)
    worldId: str | None = Field(default=None, max_length=64)
    sessionId: str | None = Field(default=None, max_length=64)
    viewport: str | None = Field(default=None, max_length=_VIEWPORT_MAX)
    currentUrl: str | None = Field(default=None, max_length=_FIELD_FREETEXT_MAX * 4)
    bundleHash: str | None = Field(default=None, max_length=_BUNDLE_HASH_MAX)


def _short_id() -> str:
    """8 lowercase hex chars from a fresh UUID4 — collision-proof at our scale."""
    return uuid.uuid4().hex[:8]


def _write_atomic(payload: dict, root: Path) -> Path:
    """Write payload as JSON to <root>/YYYY-MM-DD/<ts>-<id>.json atomically.

    Returns the final path. Caller is responsible for catching OSError and
    logging — this function does NOT swallow exceptions.
    """
    now = datetime.now(timezone.utc)
    day_dir = root / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    ts = now.strftime("%Y%m%dT%H%M%SZ")
    short = _short_id()
    final = day_dir / f"{ts}-{short}.json"
    tmp = day_dir / f"{ts}-{short}.json.tmp"

    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, final)
    return final


@router.post("/api/feedback")
async def submit_feedback(request: Request, submission: FeedbackSubmission) -> dict:
    """Accept a feedback submission, write to disk, return acknowledgment."""
    settings: Settings = request.app.state.settings
    limiter: RateLimiter = request.app.state.rate_limiter

    # Disabled when no feedback_root is configured. Surface a clear error
    # rather than letting the next code paths fail in weirder ways.
    if settings.feedback_root is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FEEDBACK_DISABLED",
                "detail": "Feedback submission is not configured on this deployment.",
            },
        )

    # Per-IP rate limit. 0 = unlimited (the limiter no-ops on limit <= 0).
    ip = client_ip(request, trusted_proxy_hops=settings.trusted_proxy_hops)
    if not limiter.allow(f"feedback:{ip}", settings.rl_feedback_per_hour, 3600):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "detail": (
                    "Too many feedback submissions from this address in the "
                    "last hour. Try again later."
                ),
                "limit_per_hour": settings.rl_feedback_per_hour,
            },
            headers={"Retry-After": "3600"},
        )

    # Build the on-disk record. submission.model_dump() captures all
    # user-entered + auto-captured fields as the tester provided them; server
    # appends submittedAt and the userAgent (read from the request header
    # rather than trusting the SPA to copy it correctly).
    user_agent = request.headers.get("user-agent", "")[:_USER_AGENT_MAX]
    record = {
        **submission.model_dump(exclude_none=False),
        "submittedAt": datetime.now(timezone.utc).isoformat(),
        "submittedAtEpoch": int(time.time()),
        "userAgent": user_agent,
        "clientIp": ip,  # post-XFF-canonicalization; useful for triage clustering
    }

    try:
        path = _write_atomic(record, settings.feedback_root)
    except OSError as exc:
        logger.exception("feedback write failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "WRITE_FAILED",
                "detail": f"Could not persist feedback: {exc.__class__.__name__}",
            },
        ) from exc

    logger.info(
        "feedback received: category=%s subject_len=%d ip=%s path=%s",
        submission.category,
        len(submission.subject),
        ip,
        path.name,
    )
    return {"status": "ok", "id": path.stem}

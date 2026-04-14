"""git-sync MCP client — HTTP wrapper for commit_snapshot.

Thin synchronous client for calling
``git-sync:8012/tools/commit_snapshot``. Takes a ``Config`` (for the
base URL) and the session/turn metadata; returns a structured
``DispatchResult`` describing success, failure mode, and the server's
response.

Design notes
------------
**Separate entry point from fs-manager dispatch.** ``commit_snapshot``
and ``apply_world_update`` are distinct dispatches rather than a
bundled atomic write-and-commit call for three reasons:

1. fs-manager writes and git-sync commits have different failure
   modes. An fs-manager rejection means the schema gate caught a
   bad payload before anything touched disk — the right response is
   to feed the error back to the DM. A git-sync failure means disk
   was already written but the audit trail step didn't land — the
   right response is to log, continue, and retry later.
2. Some callers may want to batch many ``apply_world_update`` calls
   into a single commit (a session-create flow dispatches world
   state + session metadata in two separate payloads but should
   arguably produce one commit per logical operation, not two).
3. ADR 0001's framing describes them as two dispatch calls
   explicitly, and the MCP Bridge architecture treats each server
   as an independent tool endpoint.

Same shape as fs-manager dispatch
---------------------------------
- Sync function (composes with async callers via
  ``run_in_threadpool``; composes with sync callers directly)
- Optional ``client`` keyword-only argument for test injection
  via ``httpx.MockTransport`` (no respx / pytest-httpx dep)
- Structured ``DispatchResult`` return, not exceptions — git-sync
  returning 422 on missing session_id, 500 on git failure, or a
  network error all land as ``ok=False`` with the detail in
  ``error`` / ``body``, so callers have one branch to check
- Trailing-slash normalization on ``config.git_sync_url``

"no changes" is still a success
-------------------------------
git-sync returns HTTP 200 with ``{"status": "no_changes", ...}`` when
there's nothing staged to commit (e.g. two consecutive calls with no
intervening fs-manager writes). That's a normal outcome, not a
failure — this dispatcher returns ``ok=True`` for it. Callers that
want to distinguish "committed N changes" from "committed nothing"
can inspect ``result.body["status"]`` directly.
"""

from typing import Any

import httpx

from ..types import Config
from .fs_manager import DispatchResult


def commit_snapshot(
    config: Config,
    *,
    session_id: str,
    turn_number: int,
    summary: str,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> DispatchResult:
    """POST a commit request to git-sync's /tools/commit_snapshot endpoint.

    Parameters
    ----------
    config
        Engine configuration. Only ``config.git_sync_url`` is read.
    session_id
        UUID of the active session. git-sync includes the first 8
        characters in the commit message and the full value in the
        commit body. Required — git-sync will 422 without it.
    turn_number
        Zero-based turn counter for the current session. Appears in
        the commit message as ``turn=<N>``.
    summary
        Short human-readable description of what changed this turn.
        Appears in the commit message title after ``session=... turn=...
        — <summary>``. The caller typically passes the first 200
        characters of the DM narrative.
    client
        Optional ``httpx.Client`` for test injection. Production
        callers should omit this and let the function create a fresh
        client per call. Tests inject a client backed by
        ``httpx.MockTransport`` to run without a real server.
    timeout
        Per-request timeout in seconds. Only used when constructing a
        fresh client (ignored if ``client`` is supplied).

    Returns
    -------
    DispatchResult
        ``ok=True`` on any HTTP 2xx response, including the
        ``no_changes`` shape where git-sync has nothing staged to
        commit. ``ok=False`` with ``status_code=422`` for missing
        session_id, ``ok=False`` with ``status_code=500`` for git
        failures, and ``ok=False`` with ``status_code=0`` for network
        errors or connection failures.
    """
    # Normalize the base URL so a trailing slash in config.git_sync_url
    # (e.g. "http://127.0.0.1:8012/" from an env var) doesn't produce
    # "//tools/commit_snapshot", which some routers treat as a
    # different path and return 404.
    base = config.git_sync_url.rstrip("/")
    url = f"{base}/tools/commit_snapshot"

    # Normalize the summary to a single line. Callers typically pass
    # the first N chars of DM narrative text, which contains newlines
    # — and git-sync puts the summary directly into the commit subject
    # line, where embedded newlines would break git's title/body
    # convention and produce ugly `git log` output. Collapse all
    # whitespace runs (including \r, \n, and tab) to single spaces.
    normalized_summary = " ".join(summary.split()).strip()

    payload: dict[str, Any] = {
        "session_id": session_id,
        "turn_number": turn_number,
        "summary": normalized_summary,
    }

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=timeout)

    try:
        try:
            response = client.post(url, json=payload)
        except httpx.RequestError as exc:
            return DispatchResult(
                ok=False,
                status_code=0,
                body={},
                error=f"network error: {exc}",
            )

        try:
            body = response.json()
            if not isinstance(body, dict):
                body = {"raw": body}
        except ValueError:
            body = {"raw": response.text}

        if response.is_success:
            return DispatchResult(ok=True, status_code=response.status_code, body=body)

        detail = body.get("detail", body.get("raw", "unknown error"))
        return DispatchResult(
            ok=False,
            status_code=response.status_code,
            body=body,
            error=f"git-sync rejected commit ({response.status_code}): {detail}",
        )
    finally:
        if owns_client:
            client.close()

"""fs-manager MCP client — HTTP wrapper for apply_world_update.

Thin synchronous client for calling `fs-manager:8010/tools/apply_world_update`.
Takes a `Config` (for the base URL) and a payload; returns a structured
`DispatchResult` describing success, failure mode, and the server's response.

Design notes
------------
**Sync, not async.** The engine is framework-agnostic. Sync composes
cleanly with both sync and async callers — FastAPI (which the new backend
will be) can wrap a sync call in `run_in_threadpool` when it's invoked
from an async handler. If measurement later shows the thread hop matters,
an `apply_world_update_async` variant is a drop-in addition. Don't
pre-optimize.

**Client injection via keyword-only argument.** Production code calls
`apply_world_update(config, payload)` and gets a fresh `httpx.Client` per
call. Tests pass `client=httpx.Client(transport=MockTransport(...))` to
inject a fake transport. This is the least-invasive way to make the
module mockable without dragging in respx or pytest-httpx as test
dependencies — `httpx.MockTransport` is built into httpx.

**Structured result, not exceptions.** fs-manager returning 422
(schema validation failure) or 403 (protected field violation) is a
normal control-flow case per ARCHITECTURE.md — the rejection is fed
back to the DM so it can retry. Raising would force every caller to
wrap in try/except. Network errors also land as `ok=False` with
`status_code=0` so callers have a single branch to check.

**Does not validate the payload.** Callers should run payloads through
`engine.validate()` before dispatch if they want to catch schema
violations client-side. Otherwise fs-manager will reject them
server-side with a 422. Both paths are correct — this function does
not duplicate the schema gate, it just forwards the request.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from ..types import Config


@dataclass
class DispatchResult:
    """Outcome of an MCP dispatch call.

    `ok` is True only on HTTP 2xx. `status_code` is 0 for network errors
    (couldn't reach the server at all). `body` is the parsed JSON response
    when parseable, or `{"raw": "<text>"}` when the server returned
    non-JSON. `error` is a human-readable summary when `ok` is False and
    empty when `ok` is True.
    """

    ok: bool
    status_code: int
    body: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def apply_world_update(
    config: Config,
    payload: dict[str, Any],
    *,
    world_id: str | None = None,
    namespace: str = "core",
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> DispatchResult:
    """POST a payload to fs-manager's /tools/apply_world_update endpoint.

    Parameters
    ----------
    config
        Engine configuration. Only `config.fs_manager_url` is read.
    payload
        A dict that should match `schemas/apply_world_update.schema.json`.
        This function does not validate it — pass it through
        `engine.validate()` first if you want to catch violations before
        the network round-trip.
    client
        Optional `httpx.Client` for test injection. Production callers
        should omit this and let the function create a fresh client per
        call. Tests inject a client backed by `httpx.MockTransport` to
        run without a real server.
    timeout
        Per-request timeout in seconds. Only used when constructing a
        fresh client (ignored if `client` is supplied).

    Returns
    -------
    DispatchResult
        `ok=True` on any HTTP 2xx response. `ok=False` with
        `status_code=422/403/etc.` for schema or protected-field
        violations. `ok=False` with `status_code=0` for network errors
        or connection failures.
    """
    # Normalize the base URL so a trailing slash in config.fs_manager_url
    # (e.g. "http://127.0.0.1:8010/" from an env var) doesn't produce
    # "//tools/apply_world_update", which some routers treat as a
    # different path and return 404.
    base = config.fs_manager_url.rstrip("/")
    url = f"{base}/tools/apply_world_update"

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=timeout)

    # world_id is routing metadata (which world's tree to write), not update
    # content, so it rides as a query param rather than in the schema-validated
    # body (ADR 0002). Omitted when falsy (None *or* empty string) so the
    # dispatcher agrees with fs-manager's `not world_id` fallback test — an
    # empty world_id must mean "legacy shared root", never a stray `?world_id=`
    # that the server silently re-routes.
    # namespace is the trusted, backend-set authorization scope. It is NOT carried
    # in the LLM-parsed body (the fact-extractor no longer sets it) — it rides as a
    # query param like world_id (red-team #7 / ADR 0003): the backend decides it,
    # the model can't. Default "core" is the canonical world-write path this
    # dispatcher serves; a community-pack caller passes "community". fs-manager
    # enforces it for core-gated paths.
    params: dict[str, str] = {"namespace": namespace}
    if world_id:
        params["world_id"] = world_id

    try:
        try:
            response = client.post(url, json=payload, params=params)
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
            error=f"fs-manager rejected payload ({response.status_code}): {detail}",
        )
    finally:
        if owns_client:
            client.close()

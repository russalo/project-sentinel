"""
Project Sentinel — fs-manager MCP Server

Zero-Touch filesystem handler. Validates all write payloads against
the apply_world_update JSON Schema before executing any CRUD operations
on /data. The Inference Node is never granted raw filesystem access.

Usage:
    python server.py --port 8010

Dependencies:
    pip install -r requirements.txt
"""

import argparse
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
SCHEMA_DIR = REPO_ROOT / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "apply_world_update.schema.json"

# Per-world isolation (ADR 0002). When SENTINEL_WORLDS_ROOT is set, a request
# carrying a world_id writes to that world's own tree at
# <SENTINEL_WORLDS_ROOT>/<world_id>/ instead of the legacy shared REPO_ROOT.
# Unset by default → today's single-shared-tree behavior (Slice-2 is additive;
# the cutover that sets this lives in a later slice). Read at call time so
# tests can monkeypatch it.
WORLDS_ROOT = os.environ.get("SENTINEL_WORLDS_ROOT")

# Protected fields that can never be modified by any payload.
# Enforced on BOTH create and update operations — see check_protected_fields
# and its call sites in execute_update. The check cannot be disabled by
# the caller; the previous `protected_check` opt-out has been removed.
PROTECTED_FIELDS = {
    "unique_id",
    "world_seed",
    "namespace",
    "created_at",
    "canon",
    "core_faction_id",
}

# Allowed write paths (regex must match target_file)
ALLOWED_PATH_PATTERN = re.compile(
    r"^(data/state/(core|community)/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\.json"
    r"|data/lore/(core/sessions|community/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)/[a-zA-Z0-9_-]+\.md)$"
)

# Paths that require payload-level `"namespace": "core"` authorization.
# Per ARCHITECTURE.md §2, writes to data/state/core/ and data/lore/core/
# are restricted to core-authorized payloads. The one exception is
# data/lore/core/sessions/*, which every session needs to write regardless
# of namespace — that's how community callers log their own play sessions
# to disk. The negative lookahead `(?!sessions/)` encodes that exemption.
CORE_GATED_PATH_PATTERN = re.compile(
    r"^(data/state/core/|data/lore/core/(?!sessions/))"
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("fs-manager")

# -------------------------------------------------------------------
# Schema Loading
# -------------------------------------------------------------------


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


SCHEMA = load_schema()

# jsonschema does NOT enforce `format` keywords unless you pass it a
# FormatChecker explicitly. Without this, schema-declared constraints
# like `"format": "uuid"` on session_id were silently unchecked, and
# a crafted non-UUID session_id could pass validation and reach the
# session-log append where it's interpolated into a filesystem path.
# The checker catches malformed session_ids at the schema layer — the
# _resolve_session_log_path() helper below is the second layer.
_FORMAT_CHECKER = jsonschema.FormatChecker()

# -------------------------------------------------------------------
# FastAPI App
# -------------------------------------------------------------------

app = FastAPI(
    title="Sentinel fs-manager MCP Server",
    description="Zero-Touch filesystem handler for Project Sentinel.",
    version="0.1.0",
)

# -------------------------------------------------------------------
# Validation Layer
# -------------------------------------------------------------------


def validate_payload(payload: dict) -> None:
    """Validate payload against JSON Schema. Raises HTTPException on failure.

    Uses ``_FORMAT_CHECKER`` so ``format`` keywords in the schema (notably
    ``"format": "uuid"`` on ``session_id``) are actually enforced. Without
    this, a caller could supply any string as ``session_id`` and have it
    interpolated into the session-log filesystem path — directory traversal
    waiting to happen.
    """
    try:
        jsonschema.validate(
            instance=payload,
            schema=SCHEMA,
            format_checker=_FORMAT_CHECKER,
        )
    except jsonschema.ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "detail": e.message,
                "path": list(e.path),
            },
        )
    except jsonschema.SchemaError as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "SCHEMA_ERROR", "detail": str(e)},
        )


def _resolve_session_log_path(session_id: str, root: Path | None = None) -> Path:
    """Resolve the session log path and confirm it stays inside sessions/.

    Builds ``data/lore/core/sessions/<session_id>.md`` under ``root`` (the
    world's data root; defaults to the legacy shared ``REPO_ROOT``),
    resolves it (which canonicalizes any ``..`` segments), and asserts the
    parent directory is exactly the sessions directory. Any traversal
    attempt — even one that somehow bypassed the schema's format check —
    raises 403 PATH_VIOLATION here before the file is ever opened.

    This is defense-in-depth on top of ``validate_payload``'s format
    checker: if the schema-level UUID enforcement ever regresses (or if
    a future schema change relaxes the format), the filesystem boundary
    still holds.

    Computes ``sessions_dir`` at call time rather than module load so
    tests that monkeypatch ``REPO_ROOT`` to a tmp tree pick up the new
    location automatically.
    """
    base = root if root is not None else REPO_ROOT
    sessions_dir = (base / "data" / "lore" / "core" / "sessions").resolve()
    candidate = (
        base / "data" / "lore" / "core" / "sessions" / f"{session_id}.md"
    ).resolve()
    if candidate.parent != sessions_dir:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PATH_VIOLATION",
                "detail": (
                    f"Resolved session log path {candidate!s} escapes "
                    f"sessions directory {sessions_dir!s}."
                ),
            },
        )
    return candidate


def check_protected_fields(data: Any, target_file: str) -> None:
    """Reject payloads that attempt to modify protected fields."""
    if not isinstance(data, dict):
        return
    violations = [f for f in PROTECTED_FIELDS if f in data]
    if violations:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PROTECTED_FIELD_VIOLATION",
                "detail": f"Attempted to modify protected field(s): {violations} in {target_file}",
            },
        )


def validate_path(target_file: str) -> None:
    """Ensure the target path matches the allowed pattern."""
    if not ALLOWED_PATH_PATTERN.match(target_file):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PATH_VIOLATION",
                "detail": f"target_file '{target_file}' is outside the allowed write paths.",
            },
        )


def validate_namespace(payload_namespace: str, target_file: str) -> None:
    """Enforce payload-level namespace authorization for core-gated paths.

    Per ARCHITECTURE.md §2, writes to data/state/core/ or data/lore/core/
    (excluding data/lore/core/sessions/, which every session must write)
    require the payload to declare `"namespace": "core"` at the root.
    Community payloads — those with `namespace` omitted or set to
    "community" — are sandboxed to community paths.

    Raises 403 NAMESPACE_VIOLATION if a non-core payload targets a
    core-gated path.
    """
    if not CORE_GATED_PATH_PATTERN.match(target_file):
        return
    if payload_namespace != "core":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NAMESPACE_VIOLATION",
                "detail": (
                    f"Write to core-gated path '{target_file}' "
                    f"requires payload-level 'namespace': 'core'. "
                    f"Got: {payload_namespace!r}"
                ),
            },
        )


# -------------------------------------------------------------------
# File Operations
# -------------------------------------------------------------------


def _resolve_world_root(world_id: str | None) -> Path:
    """Resolve the data root for a request (ADR 0002).

    When ``SENTINEL_WORLDS_ROOT`` is set AND a ``world_id`` is supplied, the
    root is ``<WORLDS_ROOT>/<world_id>/`` — that world's own tree. Otherwise the
    legacy shared ``REPO_ROOT`` (today's behavior; also the path when no
    world_id is given). ``REPO_ROOT``/``WORLDS_ROOT`` are read at call time so
    tests can monkeypatch them.

    ``world_id`` becomes a filesystem path component, so it is a hard security
    boundary: UUID-validated (422 on anything else — blocks ``..``/``/``), and
    the resolved root is asserted to stay directly under WORLDS_ROOT.
    """
    if not WORLDS_ROOT or not world_id:
        return REPO_ROOT
    try:
        # Canonicalize to the standard hyphenated lowercase form before it
        # becomes a path component. uuid.UUID() accepts several spellings of
        # the same value (no hyphens, braces, urn: prefix, mixed case), and
        # using the raw string would route those to *different* directories —
        # state fragmentation: two trees for one logical world.
        canonical_world_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_WORLD_ID",
                "detail": f"world_id is not a valid UUID: {world_id!r}",
            },
        )
    base = Path(WORLDS_ROOT).resolve()
    root = (base / canonical_world_id).resolve()
    if root.parent != base:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PATH_VIOLATION",
                "detail": f"Resolved world root {root!s} escapes SENTINEL_WORLDS_ROOT.",
            },
        )
    return root


def execute_update(
    target_file: str, operation: str, data: Any, root: Path | None = None
) -> dict:
    """Execute a single file operation after all validation passes.

    ``root`` is the world's data root (defaults to ``REPO_ROOT`` — the legacy
    shared tree — when not supplied). Protected-field enforcement runs
    unconditionally on both `create` and `update` operations (the previous
    per-update `protected_check` opt-out has been removed — protection is
    mandatory). `append` only takes string data, so there's no dict to check.
    """
    base = root if root is not None else REPO_ROOT
    abs_path = base / target_file
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    if operation == "create":
        if abs_path.exists():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FILE_EXISTS",
                    "detail": f"{target_file} already exists. Use 'update' to modify.",
                },
            )
        check_protected_fields(data, target_file)
        content = (
            json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
        )
        # Pin utf-8 on every read/write: payloads carry LLM-generated text
        # (emoji, smart quotes, non-ASCII names), and the project targets
        # Windows too, where the default encoding is cp1252 — an unpinned
        # write_text/open would raise UnicodeEncodeError or corrupt content.
        abs_path.write_text(content, encoding="utf-8")
        return {"status": "created", "path": target_file}

    elif operation == "update":
        check_protected_fields(data, target_file)

        if abs_path.exists() and target_file.endswith(".json"):
            existing = json.loads(abs_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(data, dict):
                existing.update(data)
                data = existing
        abs_path.write_text(
            json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data),
            encoding="utf-8",
        )
        return {"status": "updated", "path": target_file}

    elif operation == "append":
        if not isinstance(data, str):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "VALIDATION_ERROR",
                    "detail": "append operation requires string data.",
                },
            )
        with open(abs_path, "a", encoding="utf-8") as f:
            f.write("\n" + data)
        return {"status": "appended", "path": target_file}

    else:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNKNOWN_OPERATION",
                "detail": f"Unknown operation: {operation}",
            },
        )


# -------------------------------------------------------------------
# MCP Endpoints
# -------------------------------------------------------------------


@app.get("/health")
async def health():
    # `worlds_root` lets operators verify all three services agree on the
    # per-world cutover (ADR 0002): backend, fs-manager, and git-sync must all
    # have SENTINEL_WORLDS_ROOT set, or writes/reads split across trees. See
    # `docs/WORKSPACE.md` § "Per-world isolation cutover".
    return {
        "status": "ok",
        "server": "fs-manager",
        "version": "0.1.0",
        "worlds_root": bool(WORLDS_ROOT),
    }


@app.post("/tools/apply_world_update")
async def apply_world_update(request: Request):
    """
    Primary write tool. Validates and executes a batch of filesystem
    modifications as specified by the apply_world_update JSON Schema.
    """
    payload = await request.json()
    logger.info(
        f"apply_world_update — session_id={payload.get('session_id')}, "
        f"namespace={payload.get('namespace', 'community')}, "
        f"updates={len(payload.get('updates', []))}"
    )

    validate_payload(payload)

    # Per-world routing (ADR 0002): world_id is passed as a query param — it's
    # routing metadata (which world to write to), not update content, so it
    # stays out of the schema-validated body. _resolve_world_root UUID-validates
    # it and resolves the world's tree; defaults to REPO_ROOT when WORLDS_ROOT
    # is unset or no world_id is given (today's single-shared-tree behavior).
    world_root = _resolve_world_root(request.query_params.get("world_id"))

    # Payload-level namespace authorization. Default to "community" when
    # the field is absent — community is the least-privileged posture,
    # so unauthenticated or legacy payloads get the sandboxed behavior.
    payload_namespace = payload.get("namespace", "community")

    results = []
    for update in payload["updates"]:
        target_file = update["target_file"]
        operation = update["operation"]
        data = update["data"]

        validate_path(target_file)
        validate_namespace(payload_namespace, target_file)
        result = execute_update(target_file, operation, data, root=world_root)
        results.append(result)

    # Append narrative to session log. The session_id has already been
    # format-checked as a UUID by validate_payload, and _resolve_session_log_path
    # canonicalizes the path and re-verifies the parent is sessions/ —
    # a belt-and-suspenders pair so a malformed session_id can't escape
    # the sessions directory even if the schema-level check regresses.
    abs_log = _resolve_session_log_path(payload["session_id"], root=world_root)
    abs_log.parent.mkdir(parents=True, exist_ok=True)
    with open(abs_log, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n{payload['log_entry']}")

    logger.info(f"apply_world_update — success, {len(results)} operations executed.")
    return JSONResponse(
        {"success": True, "session_id": payload["session_id"], "results": results}
    )


@app.get("/tools/read_state")
async def read_state(path: str):
    """
    Read a state or lore file. Validates the path before reading.
    """
    validate_path(path)
    abs_path = REPO_ROOT / path
    if not abs_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "detail": f"{path} does not exist."},
        )

    content = abs_path.read_text(encoding="utf-8")
    if path.endswith(".json"):
        return {"path": path, "data": json.loads(content)}
    return {"path": path, "data": content}


# -------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel fs-manager MCP Server")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--dev", action="store_true", help="Enable development mode (verbose logging)"
    )
    args = parser.parse_args()

    if args.dev:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting fs-manager on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

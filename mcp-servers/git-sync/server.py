"""
Project Sentinel — git-sync MCP Server

Automated version control. Commits a snapshot of /data after each
world update, tagged with session_id and turn metadata.
Enables full rollback of world state to any prior turn.

Usage:
    python server.py --port 8012

Dependencies:
    pip install -r requirements.txt
"""

import argparse
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import git
from fastapi import FastAPI, HTTPException
import uvicorn

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("git-sync")

REPO_ROOT = Path(__file__).parent.parent.parent

# Per-world isolation (ADR 0002). When SENTINEL_WORLDS_ROOT is set, a commit
# carrying a world_id targets that world's own repo at
# <SENTINEL_WORLDS_ROOT>/<world_id>/ instead of the legacy shared REPO_ROOT.
# Unset by default → today's behavior. Read at call time (tests monkeypatch).
WORLDS_ROOT = os.environ.get("SENTINEL_WORLDS_ROOT")

app = FastAPI(
    title="Sentinel git-sync MCP Server",
    description="Automated version control for Project Sentinel world state.",
    version="0.1.0",
)


def get_repo(world_id: str | None = None) -> git.Repo:
    """Open the git repo for a request (ADR 0002).

    With ``SENTINEL_WORLDS_ROOT`` set and a ``world_id`` given, opens that
    world's own repo at ``<WORLDS_ROOT>/<world_id>/``; otherwise the legacy
    shared ``REPO_ROOT``. ``world_id`` is a path component → UUID-validated
    (422) and the resolved path is asserted under WORLDS_ROOT.
    """
    if not WORLDS_ROOT or not world_id:
        return git.Repo(REPO_ROOT)
    try:
        # Canonicalize before it becomes a path component — uuid.UUID() accepts
        # multiple spellings of the same value (no hyphens, braces, mixed case),
        # which would otherwise route to distinct repos: fragmentation, one
        # logical world split across duplicate trees. Mirrors fs-manager.
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
    repo_path = (base / canonical_world_id).resolve()
    if repo_path.parent != base:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PATH_VIOLATION",
                "detail": f"Resolved world repo {repo_path!s} escapes SENTINEL_WORLDS_ROOT.",
            },
        )
    return git.Repo(repo_path)


@app.get("/health")
async def health():
    return {"status": "ok", "server": "git-sync", "version": "0.1.0"}


@app.post("/tools/commit_snapshot")
async def commit_snapshot(body: dict):
    """
    Commit the current /data directory state to git.
    Called by the Orchestrator after every successful world update.
    """
    session_id = body.get("session_id")
    turn_number = body.get("turn_number", 0)
    summary = body.get("summary", "World state update")
    world_id = body.get("world_id")

    if not session_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_SESSION_ID", "detail": "session_id is required."},
        )

    try:
        repo = get_repo(world_id)
        repo.index.add(["data/"])

        if not repo.index.diff("HEAD"):
            return {"status": "no_changes", "message": "No changes to commit."}

        # `datetime.now(timezone.utc).isoformat(timespec='seconds')`
        # emits a fixed-length, second-precision timestamp with an
        # explicit `+00:00` offset (e.g. `2026-04-15T14:35:42+00:00`).
        # The previous trailing `Z` shorthand is dropped — both are
        # valid RFC 3339. `timespec='seconds'` keeps the format
        # consistent across logs (the default microseconds resolution
        # produces variable-length strings depending on whether
        # microseconds happen to be zero).
        # world=<id[:8]> precedes session=... when a world_id is supplied, per
        # ADR 0002's commit-message format. Omitted (not blank) when absent, so
        # legacy single-world commits keep their existing shape.
        # str() coerce before slicing: in the WORLDS_ROOT-unset path get_repo
        # skips UUID validation, so a malformed non-string world_id from a
        # direct client would otherwise raise TypeError on [:8] here.
        world_tag = f"world={str(world_id)[:8]} " if world_id else ""
        full_world_line = f"Full world_id: {world_id}\n" if world_id else ""
        commit_message = (
            f"[sentinel] {world_tag}session={session_id[:8]} turn={turn_number} — {summary}\n\n"
            f"{full_world_line}"
            f"Full session_id: {session_id}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        )

        repo.index.commit(commit_message)
        commit_hash = repo.head.commit.hexsha[:8]

        logger.info(
            f"commit_snapshot — {commit_hash} | {world_tag}session={session_id[:8]} "
            f"turn={turn_number}"
        )
        return {
            "status": "committed",
            "commit": commit_hash,
            "session_id": session_id,
            "turn_number": turn_number,
        }

    except git.InvalidGitRepositoryError:
        # Name the path that actually failed — with per-world routing the
        # missing repo is usually <WORLDS_ROOT>/<world_id>, not REPO_ROOT, and
        # a misattributed message sends operators looking in the wrong place.
        missing = f"world {world_id}" if world_id else "REPO_ROOT"
        raise HTTPException(
            status_code=500,
            detail={
                "code": "GIT_ERROR",
                "detail": f"Repository not found at {missing}.",
            },
        )
    except Exception as e:
        logger.error(f"commit_snapshot failed: {e}")
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )


@app.get("/tools/list_snapshots")
async def list_snapshots(
    session_id: str | None = None, limit: int = 20, world_id: str | None = None
):
    """List recent world state snapshots, optionally filtered by session."""
    try:
        repo = get_repo(world_id)
        commits = list(repo.iter_commits("HEAD", max_count=limit))

        results = []
        for commit in commits:
            if "[sentinel]" not in commit.message:
                continue
            if session_id and session_id[:8] not in commit.message:
                continue
            results.append(
                {
                    "hash": commit.hexsha[:8],
                    "message": commit.message.split("\n")[0],
                    "timestamp": commit.authored_datetime.isoformat(),
                }
            )
        return {"snapshots": results}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )


@app.post("/tools/rollback_to")
async def rollback_to(body: dict):
    """
    Restore /data to a prior commit. Use with caution — this rewrites world state.
    The Orchestrator should confirm with the user before calling this.
    """
    commit_hash = body.get("commit_hash")
    if not commit_hash:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_HASH", "detail": "commit_hash is required."},
        )

    try:
        repo = get_repo(body.get("world_id"))
        repo.git.checkout(commit_hash, "--", "data/")
        repo.index.add(["data/"])
        repo.index.commit(f"[sentinel] rollback to {commit_hash}")
        return {"status": "rolled_back", "to_commit": commit_hash}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel git-sync MCP Server")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    logger.info(f"Starting git-sync on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

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

app = FastAPI(
    title="Sentinel git-sync MCP Server",
    description="Automated version control for Project Sentinel world state.",
    version="0.1.0",
)


def get_repo() -> git.Repo:
    return git.Repo(REPO_ROOT)


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

    if not session_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_SESSION_ID", "detail": "session_id is required."},
        )

    try:
        repo = get_repo()
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
        commit_message = (
            f"[sentinel] session={session_id[:8]} turn={turn_number} — {summary}\n\n"
            f"Full session_id: {session_id}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        )

        repo.index.commit(commit_message)
        commit_hash = repo.head.commit.hexsha[:8]

        logger.info(
            f"commit_snapshot — {commit_hash} | session={session_id[:8]} turn={turn_number}"
        )
        return {
            "status": "committed",
            "commit": commit_hash,
            "session_id": session_id,
            "turn_number": turn_number,
        }

    except git.InvalidGitRepositoryError:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "GIT_ERROR",
                "detail": "Repository not found at REPO_ROOT.",
            },
        )
    except Exception as e:
        logger.error(f"commit_snapshot failed: {e}")
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )


@app.get("/tools/list_snapshots")
async def list_snapshots(session_id: str | None = None, limit: int = 20):
    """List recent world state snapshots, optionally filtered by session."""
    try:
        repo = get_repo()
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
        repo = get_repo()
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

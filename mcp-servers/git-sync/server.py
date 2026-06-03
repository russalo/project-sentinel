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
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import git
from fastapi import FastAPI, HTTPException
from filelock import FileLock, Timeout
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

# Hold the per-world write lock only for the disk/git operation itself (commit,
# rmtree, rollback) — sub-second — never across an LLM call, so contention is
# brief. The timeout is a fail-fast ceiling: a worker waiting longer than this
# is a sign of a stuck lock, and returning 503 beats hanging forever. Kept
# BELOW the engine dispatch HTTP timeout (30s) so a maxed-out wait surfaces as
# a clean 503 WORLD_BUSY rather than the client read-timing-out first.
_LOCK_TIMEOUT_SECONDS = 15


def _world_lock(world_id: str | None) -> "FileLock":
    """Cross-process write lock for a world's tree (ADR 0002 per-world lock).

    fs-manager and git-sync are separate processes writing the same world tree;
    backend/CLI add more. Per ADR 0002 there is "no concurrency control" today,
    so concurrent turns race on file writes *and* the git index, and a
    teardown can ``rmtree`` a tree mid-commit. A ``filelock`` on a stable path
    serializes those writers across processes.

    The lock file lives **outside** the world tree — ``<WORLDS_ROOT>/.locks/
    <canonical_world_id>.lock`` — so ``teardown_world``'s ``rmtree`` of the
    world dir can't delete a lock that is currently held. In shared mode
    (``WORLDS_ROOT`` unset, or no ``world_id``) every world writes the one
    shared repo, so a single global lock at ``<REPO_ROOT>/.sentinel-locks/
    shared.lock`` is the correct granularity (ADR 0002: a global commit lock
    serializes all worlds in the single-repo mode). ``filelock`` is portable
    (no POSIX-only ``fcntl``), satisfying the repo's cross-OS constraint.

    Globals are read at call time so tests can monkeypatch
    ``WORLDS_ROOT``/``REPO_ROOT``.
    """
    if WORLDS_ROOT and world_id:
        try:
            canonical = str(uuid.UUID(world_id))
        except (ValueError, AttributeError, TypeError):
            # Invalid id — the operation's own validation will 422; use a
            # throwaway key so locking doesn't pre-empt that nicer error.
            canonical = "invalid"
        lock_dir = Path(WORLDS_ROOT).resolve() / ".locks"
    else:
        lock_dir = Path(REPO_ROOT) / ".sentinel-locks"
        canonical = "shared"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return FileLock(str(lock_dir / f"{canonical}.lock"), timeout=_LOCK_TIMEOUT_SECONDS)


def _acquire_world_lock(world_id: str | None) -> FileLock:
    """Acquire the per-world write lock, or raise 503 if it can't be had in time."""
    lock = _world_lock(world_id)
    try:
        lock.acquire()
    except Timeout:
        raise HTTPException(
            status_code=503,
            detail={"code": "WORLD_BUSY", "detail": "world write lock busy; retry"},
        )
    return lock


def _require_world_id_when_isolated(world_id: str | None) -> None:
    """In per-world mode a write MUST carry a world_id (ADR 0002 isolation).

    With ``SENTINEL_WORLDS_ROOT`` set, a missing ``world_id`` would make
    ``get_repo``/``_world_repo_path`` fall back to the shared ``REPO_ROOT`` —
    committing world state onto the checked-out code branch (the
    master-pollution hazard) and leaking across the world boundary. Reject it
    so the fallback can only happen in legacy shared mode (WORLDS_ROOT unset),
    where it is the intended behavior. A *present* world_id is canonicalized +
    traversal-checked downstream by ``_world_repo_path``.
    """
    if WORLDS_ROOT and not world_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MISSING_WORLD_ID",
                "detail": "world_id is required when SENTINEL_WORLDS_ROOT is set.",
            },
        )


app = FastAPI(
    title="Sentinel git-sync MCP Server",
    description="Automated version control for Project Sentinel world state.",
    version="0.1.0",
)


def _world_repo_path(world_id: str) -> Path:
    """Resolve (and validate) a world's repo path under SENTINEL_WORLDS_ROOT.

    ``world_id`` is a filesystem path component, so it is a hard security
    boundary: canonicalized via ``uuid.UUID`` (422 on anything else — blocks
    ``..``/``/``), and the resolved path asserted to stay directly under the
    worlds root (403). Callers must only invoke this when ``WORLDS_ROOT`` is
    set. Does not touch disk — pure path resolution.
    """
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
    return repo_path


def get_repo(world_id: str | None = None) -> git.Repo:
    """Open the git repo for a request (ADR 0002).

    With ``SENTINEL_WORLDS_ROOT`` set and a ``world_id`` given, opens that
    world's own repo at ``<WORLDS_ROOT>/<world_id>/``; otherwise the legacy
    shared ``REPO_ROOT``. ``world_id`` is a path component → UUID-validated
    (422) and the resolved path is asserted under WORLDS_ROOT.
    """
    if not WORLDS_ROOT or not world_id:
        return git.Repo(REPO_ROOT)
    return git.Repo(_world_repo_path(world_id))


@app.get("/health")
async def health():
    # `worlds_root` lets operators verify all three services agree on the
    # per-world cutover (ADR 0002): backend, fs-manager, and git-sync must all
    # have SENTINEL_WORLDS_ROOT set, or writes/reads split across trees. See
    # `docs/WORKSPACE.md` § "Per-world isolation cutover".
    return {
        "status": "ok",
        "server": "git-sync",
        "version": "0.1.0",
        "worlds_root": bool(WORLDS_ROOT),
    }


@app.post("/tools/init_world")
async def init_world(body: dict):
    """Provision a world's git repo (ADR 0002 Slice 3).

    Called at world creation, before the first ``commit_snapshot`` for that
    world: a freshly-created per-world repo has no HEAD, so ``commit_snapshot``
    (which diffs against HEAD) would fail. This ``git init``s
    ``<WORLDS_ROOT>/<world_id>/``, lays down a baseline ``data/`` tree, sets a
    local committer identity (so it works regardless of the host's global git
    config), and makes the initial commit so a HEAD exists.

    - **Idempotent:** an already-initialized world returns ``status=exists``.
    - **No-op pre-cutover:** when ``SENTINEL_WORLDS_ROOT`` is unset, returns
      ``status=skipped`` — the legacy shared repo is already initialized, so
      there is nothing per-world to provision. (Static/shared assets —
      ``schemas/``, ``data/lore/core/presets/``, core-lore codex — are NOT
      copied here; they stay in the shared repo and are read from there.)
    """
    world_id = body.get("world_id")
    if not world_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_WORLD_ID", "detail": "world_id is required."},
        )

    if not WORLDS_ROOT:
        return {
            "status": "skipped",
            "detail": "SENTINEL_WORLDS_ROOT unset; legacy shared repo in use.",
        }

    repo_path = _world_repo_path(world_id)
    canonical = repo_path.name

    # Idempotency keys on a valid HEAD, not just .git existence: a prior call
    # that created .git but died before the initial commit leaves a repo with
    # NO HEAD, against which commit_snapshot fails forever. Such a
    # half-provisioned world must be *completed*, not reported as "exists".
    # Serialize provisioning against any concurrent commit/teardown for this
    # world (ADR 0002 per-world lock).
    lock = _acquire_world_lock(world_id)
    try:
        if (repo_path / ".git").exists():
            try:
                if git.Repo(repo_path).head.is_valid():
                    return {"status": "exists", "world_id": canonical}
            except Exception:
                pass  # corrupt/half-init repo → fall through and (re)complete it

        # Baseline: just enough for a first commit to exist. Only the mutable
        # data/ tree is per-world; a .gitkeep gives the initial commit content
        # and ensures data/ exists. fs-manager creates the deeper state/lore
        # dirs on first write.
        (repo_path / "data").mkdir(parents=True, exist_ok=True)
        (repo_path / "data" / ".gitkeep").write_text("", encoding="utf-8")

        # git.Repo.init is idempotent on an existing .git, so completing a
        # half-provisioned world reuses it rather than erroring.
        repo = git.Repo.init(repo_path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Sentinel")
            cw.set_value("user", "email", "sentinel@localhost")
        # Subprocess form (cwd=repo.working_dir) — safe when worlds are
        # provisioned concurrently; see commit_snapshot's note on the cwd race.
        repo.git.add("data/.gitkeep")
        repo.git.commit("-m", f"[sentinel] world={canonical[:8]} init")

        logger.info(f"init_world — provisioned world={canonical[:8]} at {repo_path!s}")
        return {"status": "initialized", "world_id": canonical}
    except Exception as e:
        logger.error(f"init_world failed for {canonical}: {e}")
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )
    finally:
        lock.release()


@app.post("/tools/teardown_world")
async def teardown_world(body: dict):
    """Permanently remove a world (ADR 0002 Slice 5 — hard delete).

    Symmetric with ``init_world``. **Destructive**, so ``world_id`` is
    UUID-validated and the resolved path asserted under SENTINEL_WORLDS_ROOT
    *before* any removal (an unvalidated id in an ``rmtree`` would be
    catastrophic).

    - **Per-world mode** (``SENTINEL_WORLDS_ROOT`` set): ``rmtree`` the world's
      repo at ``<WORLDS_ROOT>/<world_id>/``.
    - **Legacy/shared mode**: the world has no repo of its own — remove its
      session file (and lore session log) from the shared tree via ``git rm`` +
      commit, so the world leaves the picker. ``session_id`` (which the backend
      resolved) identifies it; shared `state/core` entities aren't world-scoped
      and are left in place (noted in BACKLOG).
    - **Idempotent:** an already-absent world returns ``status=not_found``.
    """
    world_id = body.get("world_id")
    if not world_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_WORLD_ID", "detail": "world_id is required."},
        )

    # Lock keyed by world (file in <WORLDS_ROOT>/.locks/, OUTSIDE the world tree)
    # so a teardown can't rmtree a tree mid-commit, and the lock file itself
    # survives the rmtree. (ADR 0002 per-world lock.)
    lock = _acquire_world_lock(world_id)
    try:
        if WORLDS_ROOT:
            repo_path = _world_repo_path(world_id)  # UUID + traversal validated
            # is_dir() (not exists()): a non-directory at the path → not_found,
            # not a confusing 500 from rmtree(NotADirectoryError).
            if not repo_path.is_dir():
                return {"status": "not_found", "world_id": repo_path.name}
            shutil.rmtree(repo_path)
            logger.info(f"teardown_world — removed world={repo_path.name[:8]}")
            return {"status": "removed", "world_id": repo_path.name}

        # Legacy: remove the world's session (+ lore log) via git rm + commit.
        session_id = body.get("session_id")
        if not session_id:
            return {
                "status": "not_found",
                "detail": "legacy teardown needs a session_id.",
            }
        try:
            # Canonicalize before it becomes a path component — uuid.UUID()
            # accepts non-canonical spellings; the session file is named with
            # the canonical id, so match on that.
            session_id = str(uuid.UUID(session_id))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_SESSION_ID",
                    "detail": f"session_id is not a valid UUID: {session_id!r}",
                },
            )
        repo = git.Repo(REPO_ROOT)
        rels = [
            f"data/state/core/sessions/{session_id}.json",
            f"data/lore/core/sessions/{session_id}.md",
        ]
        removed = [rel for rel in rels if (REPO_ROOT / rel).exists()]
        if not removed:
            return {"status": "not_found", "session_id": session_id}
        # Remove from the working tree first, then drop any *tracked* ones from
        # the index. `git rm <tracked> <untracked>` fails the whole command (and
        # leaves the tracked file behind) — and a session whose creating commit
        # failed (commit_snapshot is fire-and-log) is on disk but untracked. So
        # unlink unconditionally, then `git rm --cached --ignore-unmatch` to
        # de-index the tracked ones without erroring on the untracked.
        # missing_ok tolerates a file that vanished between the exists() check
        # and here (a concurrent removal).
        for rel in removed:
            (REPO_ROOT / rel).unlink(missing_ok=True)
        repo.git.rm("--cached", "--ignore-unmatch", "--", *removed)
        # Commit ONLY the teardown's own pathspecs — `git commit -m` (no paths)
        # would sweep in anything else already staged (e.g. a concurrent
        # commit_snapshot's `git add data/`). Skip the commit when those paths
        # had nothing staged (an all-untracked session — already unlinked).
        if repo.git.diff("--cached", "--name-only", "--", *removed).strip():
            repo.git.commit(
                "-m", f"[sentinel] teardown session={session_id[:8]}", "--", *removed
            )
        logger.info(f"teardown_world — removed legacy session={session_id[:8]}")
        return {"status": "removed", "session_id": session_id, "removed": removed}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"teardown_world failed for {world_id}: {e}")
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )
    finally:
        lock.release()


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
    _require_world_id_when_isolated(world_id)

    lock = _acquire_world_lock(world_id)
    try:
        repo = get_repo(world_id)
        # Stage + commit via the subprocess git (repo.git.*), NOT the in-memory
        # IndexFile (repo.index.*). GitPython's IndexFile resolves working-tree
        # paths relative to the *process* cwd, so concurrent commits to
        # different per-world repos race on cwd and fail ("No such file" on a
        # sibling world's path). The subprocess form runs each `git` with
        # cwd=repo.working_dir, so per-world commits are independent and
        # thread-safe — the isolation property the tracer soak asserts.
        repo.git.add("data/")

        if not repo.git.diff("--cached", "--name-only").strip():
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

        repo.git.commit("-m", commit_message)
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
    finally:
        lock.release()


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
    world_id = body.get("world_id")
    _require_world_id_when_isolated(world_id)

    lock = _acquire_world_lock(world_id)
    try:
        repo = get_repo(world_id)
        repo.git.checkout(commit_hash, "--", "data/")
        repo.git.add("data/")
        repo.git.commit("-m", f"[sentinel] rollback to {commit_hash}")
        return {"status": "rolled_back", "to_commit": commit_hash}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"code": "GIT_ERROR", "detail": str(e)}
        )
    finally:
        lock.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel git-sync MCP Server")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    logger.info(f"Starting git-sync on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

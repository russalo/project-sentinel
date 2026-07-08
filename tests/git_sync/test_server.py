"""Tests for ``mcp-servers/git-sync/server.py``.

Drives the real git-sync FastAPI app via TestClient against a tmp
git repo (see ``conftest.py``). Validates server behavior end-to-end
— produces real git commits, reads real history — instead of mocking
gitpython.

The existing ``tests/engine/test_dispatch_git_sync.py`` covers the
HTTP contract between the engine dispatcher and the server using
``httpx.MockTransport``; this suite covers the server's actual
internal behavior, which is the other half of the boundary.
"""

from __future__ import annotations

from pathlib import Path

import git


# ── Helpers ───────────────────────────────────────────────────────────


def _write_data_file(
    tmp_path: Path, name: str = "kael.json", contents: str = '{"name": "Kael"}'
) -> Path:
    """Write a fresh file under data/state/core/entities/ so the
    server has a real diff to commit. Returns the absolute path so
    callers can assert against it.
    """
    target = tmp_path / "data" / "state" / "core" / "entities" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents)
    return target


def _read_head_commit(tmp_path: Path) -> git.Commit:
    """Reopen the tmp git repo and return the HEAD commit object."""
    return git.Repo(tmp_path).head.commit


# ── Health / sanity ──────────────────────────────────────────────────


def test_health_endpoint_responds_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["server"] == "git-sync"


# ── Commit happy path ────────────────────────────────────────────────


def test_commit_snapshot_happy_path_returns_committed_with_hash(
    client, session_uuid, tmp_path
):
    _write_data_file(tmp_path)

    response = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 5,
            "summary": "The Shadowbeast falls to Thalia's arrow.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "committed"
    assert body["session_id"] == session_uuid
    assert body["turn_number"] == 5
    # Commit hash is truncated to 8 hex chars by the server.
    assert isinstance(body["commit"], str)
    assert len(body["commit"]) == 8
    assert all(c in "0123456789abcdef" for c in body["commit"])


def test_commit_snapshot_message_format_matches_spec(client, session_uuid, tmp_path):
    """Verify the actual commit message in the git log matches the
    documented format ``[sentinel] session=<8> turn=<N> — <summary>``.

    Reads the real commit from git history rather than trusting the
    response — the server could in principle return a `committed`
    response without the message landing correctly, and that's
    exactly the kind of bug a HTTP-only test would miss.
    """
    _write_data_file(tmp_path)

    response = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 7,
            "summary": "Kael discovers the hidden door.",
        },
    )
    assert response.status_code == 200

    head = _read_head_commit(tmp_path)
    title = head.message.split("\n")[0]

    expected_session_prefix = session_uuid[:8]
    assert title == (
        f"[sentinel] session={expected_session_prefix} "
        f"turn=7 — Kael discovers the hidden door."
    )
    # No world_id given → no world= tag (legacy single-world shape preserved).
    assert "world=" not in title


def test_commit_snapshot_message_includes_world_tag(client, session_uuid, tmp_path):
    """Per ADR 0002, a supplied world_id prefixes the title as
    ``world=<8> session=<8> ...`` and its full value lands in the body."""
    _write_data_file(tmp_path)
    world_id = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"

    response = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 2,
            "summary": "The bell tolls.",
            "world_id": world_id,
        },
    )
    assert response.status_code == 200

    head = _read_head_commit(tmp_path)
    title = head.message.split("\n")[0]
    assert title == (
        f"[sentinel] world={world_id[:8]} session={session_uuid[:8]} "
        f"turn=2 — The bell tolls."
    )
    assert f"Full world_id: {world_id}" in head.message


def test_commit_snapshot_full_session_id_appears_in_body(
    client, session_uuid, tmp_path
):
    """The title only carries the truncated session_id (8 chars).
    The full UUID has to appear in the commit body so that the audit
    trail has the unambiguous identity, not just the prefix.
    """
    _write_data_file(tmp_path)

    client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 1,
            "summary": "Anything.",
        },
    )

    head = _read_head_commit(tmp_path)
    assert f"Full session_id: {session_uuid}" in head.message


def test_commit_snapshot_includes_timestamp_in_body(client, session_uuid, tmp_path):
    """The commit body has a ``Timestamp:`` line so a reader can
    sort by time without parsing git metadata."""
    _write_data_file(tmp_path)

    client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 1,
            "summary": "Anything.",
        },
    )

    head = _read_head_commit(tmp_path)
    assert "Timestamp:" in head.message


def test_commit_snapshot_writes_real_commit_to_git_history(
    client, session_uuid, tmp_path
):
    """End-to-end check: after calling commit_snapshot, the new
    commit really exists in the git log. Catches the failure mode
    where the response says "committed" but no commit landed.
    """
    repo_before = git.Repo(tmp_path)
    head_before = repo_before.head.commit.hexsha

    _write_data_file(tmp_path)
    response = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 2,
            "summary": "Anything.",
        },
    )
    assert response.status_code == 200

    repo_after = git.Repo(tmp_path)
    head_after = repo_after.head.commit.hexsha

    assert head_after != head_before, "commit_snapshot did not advance HEAD"
    assert "[sentinel]" in repo_after.head.commit.message


# ── No-changes path ──────────────────────────────────────────────────


def test_commit_snapshot_no_changes_returns_no_changes_status(
    client, session_uuid, tmp_path
):
    """When the server is asked to commit but the working tree has
    no diff against HEAD, it must return 200 ``status="no_changes"``
    and NOT raise. The dispatcher (and the engine boundary tests)
    explicitly rely on this being a normal-success outcome.
    """
    # Crucial: do NOT write any new files. The fixture's initial
    # commit means HEAD exists; with nothing new staged, the server
    # should land in the no-diff branch.
    response = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 1,
            "summary": "Nothing changed this turn.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_changes"
    assert "message" in body


def test_commit_snapshot_no_changes_does_not_advance_head(
    client, session_uuid, tmp_path
):
    """Belt to the no_changes test: the no-diff path must not
    silently produce a commit anyway. HEAD stays where it was.
    """
    head_before = git.Repo(tmp_path).head.commit.hexsha

    client.post(
        "/tools/commit_snapshot",
        json={"session_id": session_uuid, "turn_number": 1, "summary": "X."},
    )

    head_after = git.Repo(tmp_path).head.commit.hexsha
    assert head_before == head_after


# ── Error paths ──────────────────────────────────────────────────────


def test_commit_snapshot_missing_session_id_returns_422(client):
    response = client.post(
        "/tools/commit_snapshot",
        json={"turn_number": 1, "summary": "no session id"},
    )

    assert response.status_code == 422
    body = response.json()
    # FastAPI nests detail under "detail" — match the existing dispatcher
    # contract that expects either the structured code or the message.
    detail = body["detail"]
    if isinstance(detail, dict):
        assert detail["code"] == "MISSING_SESSION_ID"
    else:
        assert "session_id is required" in str(detail)


def test_commit_snapshot_invalid_repository_returns_500_git_error(
    monkeypatch, git_sync_module, client, session_uuid, tmp_path
):
    """If REPO_ROOT points at a directory that is not a git repo,
    the server's commit_snapshot must return 500 GIT_ERROR — not
    crash, not return 200. The dispatcher relies on this being a
    structured failure so the backend can log and continue.

    The existing ``client`` fixture works after we monkeypatch
    REPO_ROOT because ``server.get_repo()`` reads the constant at
    request time, not at module import time, so the next request
    through the same client picks up the new value.
    """
    # Create a sibling tmp dir that is NOT a git repo — no .git/.
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setattr(git_sync_module, "REPO_ROOT", not_a_repo)

    response = client.post(
        "/tools/commit_snapshot",
        json={"session_id": session_uuid, "turn_number": 1, "summary": "x"},
    )

    assert response.status_code == 500
    body = response.json()
    detail = body["detail"]
    if isinstance(detail, dict):
        assert detail["code"] == "GIT_ERROR"
    else:
        assert "Repository not found" in str(detail) or "GIT_ERROR" in str(detail)


def test_git_error_body_is_sanitized(
    client, git_sync_module, monkeypatch, session_uuid
):
    """red-team #4 — a git failure must NOT leak the raw exception (GitPython's
    GitCommandError embeds the full command + verbatim git stderr, which can carry
    world paths / WORLDS_ROOT) into the HTTP body. The caller gets a generic
    message; the detail goes to the server logs."""
    import git as gitpy

    secret_path = "/srv/secret-worlds/PRIVATE_ROOT/should-not-leak"

    def boom(*args, **kwargs):
        raise gitpy.GitCommandError(
            ["git", "commit"], 128, stderr=f"fatal: cannot access {secret_path}"
        )

    monkeypatch.setattr(git_sync_module, "get_repo", boom)
    response = client.post(
        "/tools/commit_snapshot",
        json={"session_id": session_uuid, "turn_number": 1, "summary": "x"},
    )
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "GIT_ERROR"
    assert detail["detail"] == "git operation failed; see server logs"
    assert secret_path not in response.text  # the raw stderr/path is NOT in the body


# ── Per-world mode: world_id required (ADR 0002 isolation, Path A/A1) ──


def test_commit_missing_world_id_rejected_when_isolated(
    client, git_sync_module, monkeypatch, tmp_path
):
    """With SENTINEL_WORLDS_ROOT set, a commit with no world_id must 422 —
    never fall back to REPO_ROOT (which would commit world state onto the
    checked-out code branch: the master-pollution hazard)."""
    monkeypatch.setattr(git_sync_module, "WORLDS_ROOT", str(tmp_path / "worlds"))
    response = client.post(
        "/tools/commit_snapshot",
        json={"session_id": "11111111-2222-3333-4444-555555555555", "summary": "x"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MISSING_WORLD_ID"


def test_rollback_to_endpoint_removed(client):
    """rollback_to was dead code from a superseded (Orchestrator-era) design with
    the same MCP auth gap as teardown_world and zero callers — removed (red-team
    #3). The route must stay gone (404), not resurface."""
    response = client.post("/tools/rollback_to", json={"commit_hash": "abc1234"})
    assert response.status_code == 404


def test_commit_with_world_id_still_works_when_isolated(
    client, git_sync_module, monkeypatch, tmp_path
):
    """Sanity: the guard doesn't block a properly-routed per-world commit.
    init the world first (so it has a HEAD), then commit to it."""
    worlds = tmp_path / "worlds"
    monkeypatch.setattr(git_sync_module, "WORLDS_ROOT", str(worlds))
    wid = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
    init = client.post("/tools/init_world", json={"world_id": wid})
    assert init.status_code == 200
    # A real change in the world's data tree so there's something to commit.
    (worlds / wid / "data" / "note.txt").write_text("hi", encoding="utf-8")
    resp = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": "11111111-2222-3333-4444-555555555555",
            "summary": "world commit",
            "world_id": wid,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "committed"

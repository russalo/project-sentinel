"""Tests for git-sync's ``/tools/init_world`` (ADR 0002 Slice 3 provisioning).

A freshly-created per-world repo has no HEAD, so ``commit_snapshot`` (which
diffs against HEAD) fails against it — provisioning must ``git init`` + make an
initial commit first. These tests drive the real endpoint against a tmp worlds
root and assert it provisions correctly, is idempotent, no-ops pre-cutover, and
— the load-bearing case — that ``commit_snapshot`` succeeds for a world *after*
``init_world`` has run.
"""

from __future__ import annotations


import git
import pytest

WORLD_UUID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"


@pytest.fixture
def worlds_root(git_sync_module, monkeypatch, tmp_path):
    """Enable per-world routing: point the server's WORLDS_ROOT at a tmp dir."""
    root = tmp_path / "worlds"
    root.mkdir()
    monkeypatch.setattr(git_sync_module, "WORLDS_ROOT", str(root))
    return root


# ── No-op pre-cutover ─────────────────────────────────────────────────


def test_init_world_skipped_when_worlds_root_unset(
    client, git_sync_module, monkeypatch
):
    monkeypatch.setattr(git_sync_module, "WORLDS_ROOT", None)
    resp = client.post("/tools/init_world", json={"world_id": WORLD_UUID})
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ── Provisioning ──────────────────────────────────────────────────────


def test_init_world_provisions_repo_with_head(client, worlds_root):
    resp = client.post("/tools/init_world", json={"world_id": WORLD_UUID})
    assert resp.status_code == 200
    assert resp.json()["status"] == "initialized"

    world = worlds_root / WORLD_UUID
    assert (world / ".git").is_dir()
    assert (world / "data" / ".gitkeep").is_file()
    # HEAD exists with the init commit — the whole point (commit_snapshot needs it).
    repo = git.Repo(world)
    assert repo.head.is_valid()
    assert "init" in repo.head.commit.message


def test_init_world_idempotent(client, worlds_root):
    first = client.post("/tools/init_world", json={"world_id": WORLD_UUID})
    assert first.json()["status"] == "initialized"
    head_before = git.Repo(worlds_root / WORLD_UUID).head.commit.hexsha

    second = client.post("/tools/init_world", json={"world_id": WORLD_UUID})
    assert second.status_code == 200
    assert second.json()["status"] == "exists"
    # HEAD didn't move — no duplicate init commit.
    assert git.Repo(worlds_root / WORLD_UUID).head.commit.hexsha == head_before


def test_init_world_canonicalizes_world_id(client, worlds_root):
    """A no-hyphen UUID provisions the canonical hyphenated dir (no fragmentation)."""
    resp = client.post(
        "/tools/init_world", json={"world_id": WORLD_UUID.replace("-", "")}
    )
    assert resp.status_code == 200
    assert (worlds_root / WORLD_UUID / ".git").is_dir()


# ── The load-bearing integration: commit works after init ─────────────


def test_commit_snapshot_succeeds_after_init_world(client, worlds_root, session_uuid):
    """init_world → write a state file in the world tree → commit_snapshot for
    that world must succeed. Without provisioning this 500s (no HEAD)."""
    client.post("/tools/init_world", json={"world_id": WORLD_UUID})

    entity = (
        worlds_root / WORLD_UUID / "data" / "state" / "core" / "entities" / "kael.json"
    )
    entity.parent.mkdir(parents=True, exist_ok=True)
    entity.write_text('{"name": "Kael"}', encoding="utf-8")

    resp = client.post(
        "/tools/commit_snapshot",
        json={
            "session_id": session_uuid,
            "turn_number": 1,
            "summary": "Kael appears.",
            "world_id": WORLD_UUID,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "committed"
    # The commit landed in the WORLD's repo, tagged with the world.
    head = git.Repo(worlds_root / WORLD_UUID).head.commit
    assert f"world={WORLD_UUID[:8]}" in head.message


# ── Error paths ───────────────────────────────────────────────────────


def test_init_world_missing_world_id_422(client, worlds_root):
    resp = client.post("/tools/init_world", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert (detail["code"] if isinstance(detail, dict) else str(detail)).startswith(
        "MISSING_WORLD_ID"
    ) or "world_id is required" in str(detail)


@pytest.mark.parametrize("bad", ["not-a-uuid", "../../../etc", "/etc/passwd", ".."])
def test_init_world_invalid_world_id_422_and_writes_nothing(client, worlds_root, bad):
    before = sum(1 for _ in worlds_root.rglob("*"))
    resp = client.post("/tools/init_world", json={"world_id": bad})
    assert resp.status_code in (422, 403)
    # No stray directory created for a rejected id.
    assert sum(1 for _ in worlds_root.rglob("*")) == before

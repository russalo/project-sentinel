"""Cross-process per-world write lock (ADR 0002 — Path A, A1).

ADR 0002: "No concurrency control. Zero locks… concurrent turns race on file
writes *and* the single git index." A1 adds a per-world `filelock` shared by
fs-manager and git-sync. These tests load both real server modules (the
tracer-soak pattern — they share the module name ``server``, so load under
distinct names) and assert the lock's properties:

- writers to the SAME world serialize;
- DIFFERENT worlds are independent (no false contention);
- the lock file lives OUTSIDE the world tree (teardown's rmtree can't delete a
  held lock);
- non-canonical UUID spellings map to the SAME lock (no fragmentation);
- shared mode (WORLDS_ROOT unset) collapses to one global lock;
- fs-manager and git-sync derive the SAME lock path for a world (or the
  cross-process write↔commit serialization silently breaks).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from filelock import Timeout

_ROOT = Path(__file__).resolve().parent.parent
_GITSYNC = _ROOT / "mcp-servers" / "git-sync" / "server.py"
_FSMANAGER = _ROOT / "mcp-servers" / "fs-manager" / "server.py"

WID_A = "11111111-1111-1111-1111-111111111111"
WID_B = "22222222-2222-2222-2222-222222222222"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def gitsync(tmp_path, monkeypatch):
    mod = _load(_GITSYNC, "gitsync_lock_test")
    monkeypatch.setattr(mod, "WORLDS_ROOT", str(tmp_path))
    return mod


def test_same_world_serializes(gitsync):
    held = gitsync._world_lock(WID_A)
    held.acquire()
    try:
        contender = gitsync._world_lock(WID_A)
        with pytest.raises(Timeout):
            contender.acquire(timeout=0.1)
    finally:
        held.release()


def test_different_worlds_independent(gitsync):
    a = gitsync._world_lock(WID_A)
    a.acquire()
    try:
        b = gitsync._world_lock(WID_B)
        b.acquire(timeout=0.1)  # must NOT block — different world
        b.release()
    finally:
        a.release()


def test_lock_file_lives_outside_the_world_tree(gitsync, tmp_path):
    # If the lock lived under <WORLDS_ROOT>/<world_id>/, teardown_world's rmtree
    # of that dir would delete a held lock. It must be a sibling .locks/ dir.
    lock_path = Path(gitsync._world_lock(WID_A).lock_file)
    assert lock_path.parent == (tmp_path / ".locks")
    assert (tmp_path / WID_A) not in lock_path.parents


def test_non_canonical_world_id_maps_to_same_lock(gitsync):
    a = gitsync._world_lock(WID_A)
    b = gitsync._world_lock(WID_A.upper())
    c = gitsync._world_lock("{" + WID_A + "}")
    assert a.lock_file == b.lock_file == c.lock_file


def test_shared_mode_is_one_global_lock(tmp_path, monkeypatch):
    mod = _load(_GITSYNC, "gitsync_lock_test_shared")
    monkeypatch.setattr(mod, "WORLDS_ROOT", None)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)  # don't touch the real repo
    a = mod._world_lock(WID_A)
    b = mod._world_lock(WID_B)
    assert a.lock_file == b.lock_file  # all worlds collapse to one lock


def test_fs_manager_and_git_sync_agree_on_lock_path(tmp_path, monkeypatch):
    gs = _load(_GITSYNC, "gs_agree")
    fs = _load(_FSMANAGER, "fs_agree")
    monkeypatch.setattr(gs, "WORLDS_ROOT", str(tmp_path))
    monkeypatch.setattr(fs, "WORLDS_ROOT", str(tmp_path))
    assert gs._world_lock(WID_A).lock_file == fs._world_lock(WID_A).lock_file

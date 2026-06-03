"""Tests for ``backend.state.world_root.resolve_world_data_dir`` (ADR 0002 Slice 3).

The backend's per-world data-root resolver is the read-side mirror of the MCP
servers' ``_resolve_world_root``. ``world_id`` becomes a filesystem path
component, so the falsify-first cases below feed traversal / absolute-path /
non-UUID values and assert they raise ``ValueError`` (never escaping the worlds
root). Legacy behavior (env unset, or no world_id) must return the shared tree
unchanged, so the cutover is backward-compatible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.state.world_root import (
    find_session_data_dir,
    find_world_session,
    iter_session_data_dirs,
    resolve_world_data_dir,
)

WORLD_UUID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
DEFAULT = Path("/repo/data")


# ── Legacy fallback (cutover not flipped) ─────────────────────────────


def test_unset_worlds_root_returns_default():
    """Env unset (today's default) → the shared tree, world_id ignored."""
    assert resolve_world_data_dir(None, WORLD_UUID, default_data_dir=DEFAULT) == DEFAULT


def test_empty_worlds_root_returns_default():
    assert resolve_world_data_dir("", WORLD_UUID, default_data_dir=DEFAULT) == DEFAULT


def test_no_world_id_returns_default_even_when_worlds_root_set(tmp_path):
    """A session with no world_id (created pre-cutover) reads the shared tree."""
    assert (
        resolve_world_data_dir(str(tmp_path), None, default_data_dir=DEFAULT) == DEFAULT
    )
    assert (
        resolve_world_data_dir(str(tmp_path), "", default_data_dir=DEFAULT) == DEFAULT
    )


# ── Per-world routing ─────────────────────────────────────────────────


def test_routes_to_per_world_data_dir(tmp_path):
    got = resolve_world_data_dir(str(tmp_path), WORLD_UUID, default_data_dir=DEFAULT)
    assert got == (tmp_path.resolve() / WORLD_UUID / "data")
    # Stays directly under the worlds root.
    assert got.parent.parent == tmp_path.resolve()


def test_canonicalizes_non_hyphenated_uuid(tmp_path):
    """A no-hyphen UUID resolves to the SAME tree as its canonical form —
    otherwise one logical world fragments across two directories."""
    no_hyphens = WORLD_UUID.replace("-", "")
    got = resolve_world_data_dir(str(tmp_path), no_hyphens, default_data_dir=DEFAULT)
    assert got == (tmp_path.resolve() / WORLD_UUID / "data")


# ── Security: world_id is a path component ────────────────────────────


@pytest.mark.parametrize(
    "bad_world_id",
    [
        "not-a-uuid",
        "../../../etc/passwd",
        "/etc/passwd",
        "..",
        "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f/../../escape",
        "world; rm -rf /",
    ],
)
def test_invalid_world_id_raises_valueerror(tmp_path, bad_world_id):
    with pytest.raises(ValueError):
        resolve_world_data_dir(str(tmp_path), bad_world_id, default_data_dir=DEFAULT)


# ── Session-scan helpers (dataset endpoints) ──────────────────────────


def test_iter_session_data_dirs_unset_returns_default():
    assert iter_session_data_dirs(None, default_data_dir=DEFAULT) == [DEFAULT]


def test_iter_session_data_dirs_lists_each_world(tmp_path):
    (tmp_path / "world-a").mkdir()
    (tmp_path / "world-b").mkdir()
    (tmp_path / "afile").write_text("not a dir")
    got = iter_session_data_dirs(str(tmp_path), default_data_dir=DEFAULT)
    assert got == [tmp_path / "world-a" / "data", tmp_path / "world-b" / "data"]


def test_iter_session_data_dirs_missing_root_is_empty(tmp_path):
    assert (
        iter_session_data_dirs(str(tmp_path / "nope"), default_data_dir=DEFAULT) == []
    )


def test_find_session_data_dir_unset_returns_default():
    assert find_session_data_dir(None, WORLD_UUID, default_data_dir=DEFAULT) == DEFAULT


def test_find_session_data_dir_locates_world_holding_the_file(tmp_path):
    sid = "11111111-2222-3333-4444-555555555555"
    world = tmp_path / "the-world"
    sdir = world / "data" / "state" / "core" / "sessions"
    sdir.mkdir(parents=True)
    (sdir / f"{sid}.json").write_text("{}")
    # A decoy world without the file.
    (tmp_path / "other" / "data" / "state" / "core" / "sessions").mkdir(parents=True)

    got = find_session_data_dir(str(tmp_path), sid, default_data_dir=DEFAULT)
    assert got == world / "data"


def test_find_session_data_dir_missing_returns_none(tmp_path):
    sid = "11111111-2222-3333-4444-555555555555"
    (tmp_path / "w" / "data").mkdir(parents=True)
    # Not in any world tree and not in the (non-existent) default → None.
    missing_default = tmp_path / "no-default"
    assert (
        find_session_data_dir(str(tmp_path), sid, default_data_dir=missing_default)
        is None
    )


def test_find_session_data_dir_falls_back_to_shared_tree(tmp_path):
    """A pre-cutover session in the shared tree still resolves after WORLDS_ROOT
    is set — graceful migration, not a hard break."""
    sid = "11111111-2222-3333-4444-555555555555"
    worlds = tmp_path / "worlds"
    worlds.mkdir()
    # A provisioned world that does NOT hold this session.
    (worlds / "the-world" / "data" / "state" / "core" / "sessions").mkdir(parents=True)
    # The session lives in the legacy shared tree.
    shared = tmp_path / "shared-data"
    sdir = shared / "state" / "core" / "sessions"
    sdir.mkdir(parents=True)
    (sdir / f"{sid}.json").write_text("{}")

    got = find_session_data_dir(str(worlds), sid, default_data_dir=shared)
    assert got == shared


def test_find_session_data_dir_prefers_world_over_shared(tmp_path):
    """If the session is in a world tree, that wins over the shared fallback."""
    sid = "11111111-2222-3333-4444-555555555555"
    worlds = tmp_path / "worlds"
    wdir = worlds / "the-world" / "data" / "state" / "core" / "sessions"
    wdir.mkdir(parents=True)
    (wdir / f"{sid}.json").write_text("{}")
    shared = tmp_path / "shared-data"
    (shared / "state" / "core" / "sessions").mkdir(parents=True)
    (shared / "state" / "core" / "sessions" / f"{sid}.json").write_text("{}")

    got = find_session_data_dir(str(worlds), sid, default_data_dir=shared)
    assert got == worlds / "the-world" / "data"


def test_find_session_data_dir_rejects_non_uuid(tmp_path):
    assert (
        find_session_data_dir(str(tmp_path), "../escape", default_data_dir=DEFAULT)
        is None
    )


# ── find_world_session (Slice 4 hydration resolver) ───────────────────


def _seed(sessions_dir, sid, world_id=""):
    import json as _json

    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{sid}.json").write_text(
        _json.dumps({"session_id": sid, "world_id": world_id}), encoding="utf-8"
    )


def test_find_world_session_per_world_mode(tmp_path):
    """Per-world mode: the world's own tree holds only its sessions → returned."""
    worlds = tmp_path / "worlds"
    sid = "11111111-2222-3333-4444-555555555555"
    _seed(worlds / WORLD_UUID / "data" / "state" / "core" / "sessions", sid)
    got = find_world_session(str(worlds), WORLD_UUID, default_data_dir=DEFAULT)
    assert got == (worlds / WORLD_UUID / "data", sid)


def test_find_world_session_none_when_world_empty(tmp_path):
    worlds = tmp_path / "worlds"
    (worlds / WORLD_UUID / "data").mkdir(parents=True)
    assert find_world_session(str(worlds), WORLD_UUID, default_data_dir=DEFAULT) is None


def test_find_world_session_legacy_filters_by_stored_world_id(tmp_path):
    """Legacy/shared mode: filter the one sessions dir by stored world_id."""
    shared = tmp_path / "data"
    sdir = shared / "state" / "core" / "sessions"
    _seed(sdir, "11111111-2222-3333-4444-555555555555", world_id=WORLD_UUID)
    _seed(sdir, "99999999-2222-3333-4444-555555555555", world_id="other")
    got = find_world_session(None, WORLD_UUID, default_data_dir=shared)
    assert got == (shared, "11111111-2222-3333-4444-555555555555")


def test_find_world_session_bad_world_id_returns_none(tmp_path):
    assert (
        find_world_session(str(tmp_path), "../escape", default_data_dir=DEFAULT) is None
    )

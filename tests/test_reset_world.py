"""Tests for scripts/reset-world.py.

Exercises the pure filesystem reset (``reset_world``) against a temp
fixture tree — never the real repo, and never touching git. The git
commit path in ``main()`` is thin subprocess glue and is left to manual
/ CI verification.
"""

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reset-world.py"


def _load_module():
    # The script has a hyphen in its name (scripts/ convention), so it
    # can't be imported normally — load it by path.
    spec = importlib.util.spec_from_file_location("reset_world_script", _SCRIPT)
    assert spec and spec.loader, f"could not load module spec for {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reset_world_script = _load_module()


def _make_tree(root: Path) -> None:
    """Build a minimal data/ tree with playthrough cruft + canonical content."""
    state = root / "data" / "state" / "core"
    lore = root / "data" / "lore" / "core"

    for sub in ("entities", "locations", "factions", "items", "sessions", "world"):
        (state / sub).mkdir(parents=True)
        (state / sub / ".gitkeep").write_text("")

    # Per-playthrough state that a reset must remove.
    (state / "entities" / "russalo.json").write_text('{"name": "Russalo"}')
    (state / "locations" / "inn.json").write_text('{"name": "Inn"}')
    (state / "items" / "key.json").write_text("{}")
    (state / "sessions" / "abc.json").write_text("{}")
    (state / "world" / "state.json").write_text(
        '{"tension": 8, "currentLocation": "Inn"}'
    )

    for sub in ("codex", "presets", "sessions"):
        (lore / sub).mkdir(parents=True)
        (lore / sub / ".gitkeep").write_text("")
    # Canonical lore — must be preserved.
    (lore / "codex" / "trog.md").write_text("# Trog")
    (lore / "presets" / "genres").mkdir()
    (lore / "presets" / "genres" / "fantasy.toml").write_text("name = 'Fantasy'")
    # Session narrative log — must be wiped.
    (lore / "sessions" / "abc.md").write_text("session log")


def test_reset_removes_playthrough_state_but_keeps_gitkeep(tmp_path):
    _make_tree(tmp_path)
    reset_world_script.reset_world(tmp_path)

    state = tmp_path / "data" / "state" / "core"
    assert not (state / "entities" / "russalo.json").exists()
    assert not (state / "locations" / "inn.json").exists()
    assert not (state / "items" / "key.json").exists()
    assert not (state / "sessions" / "abc.json").exists()
    # The .gitkeep in every cleared dir survives so the dir stays tracked.
    for sub in ("entities", "locations", "factions", "items", "sessions"):
        assert (state / sub / ".gitkeep").exists()


def test_reset_writes_empty_world_baseline(tmp_path):
    _make_tree(tmp_path)
    reset_world_script.reset_world(tmp_path)

    world_file = tmp_path / "data" / "state" / "core" / "world" / "state.json"
    assert json.loads(world_file.read_text()) == {}


def test_reset_preserves_canonical_lore(tmp_path):
    _make_tree(tmp_path)
    reset_world_script.reset_world(tmp_path)

    lore = tmp_path / "data" / "lore" / "core"
    assert (lore / "codex" / "trog.md").read_text() == "# Trog"
    assert (lore / "presets" / "genres" / "fantasy.toml").exists()


def test_reset_wipes_lore_session_logs(tmp_path):
    _make_tree(tmp_path)
    reset_world_script.reset_world(tmp_path)

    lore_sessions = tmp_path / "data" / "lore" / "core" / "sessions"
    assert not (lore_sessions / "abc.md").exists()
    assert (lore_sessions / ".gitkeep").exists()


def test_reset_returns_removed_paths(tmp_path):
    _make_tree(tmp_path)
    removed = reset_world_script.reset_world(tmp_path)
    # russalo, inn, key, sessions/abc.json, lore sessions/abc.md = 5
    assert len(removed) == 5
    names = {p.name for p in removed}
    assert ".gitkeep" not in names


def test_reset_is_idempotent_on_already_empty_tree(tmp_path):
    _make_tree(tmp_path)
    reset_world_script.reset_world(tmp_path)
    # Second run finds nothing left to remove.
    removed = reset_world_script.reset_world(tmp_path)
    assert removed == []


# ── --world-id resolution (ADR 0002 Slice 3 lifecycle) ────────────────

WORLD_UUID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"


def _git_init(root: Path) -> None:
    import subprocess

    for args in (
        ["init"],
        ["config", "user.name", "T"],
        ["config", "user.email", "t@e"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_world_id_mode_resets_only_that_world(tmp_path):
    """`--world-id` resets <worlds-root>/<id>'s tree, not the shared repo."""
    worlds = tmp_path / "worlds"
    world = worlds / WORLD_UUID
    _make_tree(world)
    _git_init(world)  # --no-commit still stages, which needs a git repo
    # A sibling world that must be left untouched.
    other = worlds / "11111111-2222-3333-4444-555555555555"
    _make_tree(other)

    rc = reset_world_script.main(
        ["--world-id", WORLD_UUID, "--worlds-root", str(worlds), "--no-commit"]
    )
    assert rc == 0
    assert not (
        world / "data" / "state" / "core" / "entities" / "russalo.json"
    ).exists()
    # The other world is untouched.
    assert (other / "data" / "state" / "core" / "entities" / "russalo.json").exists()


def test_teardown_removes_only_that_world(tmp_path):
    """`--world-id --teardown` rmtree's the world; siblings untouched."""
    worlds = tmp_path / "worlds"
    world = worlds / WORLD_UUID
    _make_tree(world)
    other = worlds / "11111111-2222-3333-4444-555555555555"
    _make_tree(other)

    rc = reset_world_script.main(
        ["--world-id", WORLD_UUID, "--worlds-root", str(worlds), "--teardown"]
    )
    assert rc == 0
    assert not world.exists()  # the whole world tree is gone
    assert other.exists()  # sibling untouched


def test_teardown_requires_world_id(tmp_path, capsys):
    rc = reset_world_script.main(["--teardown", "--root", str(tmp_path)])
    assert rc == 2
    assert "requires --world-id" in capsys.readouterr().err


def test_teardown_rejects_traversal_world_id(tmp_path, capsys):
    victim = tmp_path / "victim"
    victim.mkdir()
    rc = reset_world_script.main(
        [
            "--world-id",
            "../victim",
            "--worlds-root",
            str(tmp_path / "worlds"),
            "--teardown",
        ]
    )
    assert rc == 2
    assert victim.exists()  # traversal id rejected, nothing removed


def test_world_id_requires_worlds_root(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SENTINEL_WORLDS_ROOT", raising=False)
    rc = reset_world_script.main(["--world-id", WORLD_UUID])
    assert rc == 2
    assert "requires --worlds-root" in capsys.readouterr().err


def test_world_id_rejects_non_uuid(tmp_path, capsys):
    rc = reset_world_script.main(
        ["--world-id", "../escape", "--worlds-root", str(tmp_path)]
    )
    assert rc == 2
    assert "not a valid UUID" in capsys.readouterr().err


def test_world_id_missing_world_is_error(tmp_path, capsys):
    rc = reset_world_script.main(
        ["--world-id", WORLD_UUID, "--worlds-root", str(tmp_path)]
    )
    assert rc == 2
    assert "not found" in capsys.readouterr().err

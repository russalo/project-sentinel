#!/usr/bin/env python3
"""Reset the canonical world state to an empty baseline.

This is the minimum-viable unblocker for isolated smoke-test runs (see
``docs/BACKLOG.md`` § "Enablers"). It lets you start a fresh world without
hand-``rm``-ing the git-tracked ``data/`` tree, so each research-loop run
begins from a clean slate instead of inheriting entities from prior
playthroughs.

It is deliberately NOT a replacement for the world-identity ADR — that work
still needs to happen and should supersede this script when it lands.

What it does (all paths relative to the repo root):

  Wipes (per-playthrough state, but keeps each dir's ``.gitkeep``):
    - data/state/core/{entities,locations,factions,items,sessions}/*
    - data/lore/core/sessions/*            (session narrative logs)
  Resets:
    - data/state/core/world/state.json     → {} (an empty baseline; the
      backend's world-context reader fills sensible defaults)
  Preserves (canonical content — never touched):
    - data/lore/core/codex/, data/lore/core/presets/, every ``.gitkeep``

By default it commits the reset with plain git (``git-sync`` is turn-tagged
and would mislabel a reset). Use ``--no-commit`` to stage without committing,
or ``--snapshot NAME`` to tag the current HEAD as ``snapshot/NAME`` first so
the run is recoverable for later comparison.

Cross-OS: pure Python + the ``git`` CLI; no shell-isms, no extra deps.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Dirs under data/state/core/ whose per-playthrough contents are cleared.
_STATE_SUBDIRS = ("entities", "locations", "factions", "items", "sessions")
# Dirs under data/lore/core/ whose contents are cleared. Only session
# narrative logs — codex/ and presets/ are canonical and left alone.
_LORE_SUBDIRS = ("sessions",)
# Names preserved when clearing a dir, so the empty dir stays git-tracked.
_KEEP = {".gitkeep"}
# Empty world baseline. The reader (backend/state/world_context.py) applies
# defaults for every missing field, so {} is a valid, neutral starting point.
_BASELINE_WORLD: dict = {}


def _reset_pathspecs() -> list[str]:
    """The exact git pathspecs reset_world() mutates.

    Used to scope ``git add``/``commit`` to the reset's domain so a reset run
    never sweeps in unrelated edits the caller may have under ``data/`` (e.g.
    in-progress canonical lore/preset/community changes).
    """
    specs = [f"data/state/core/{sub}" for sub in _STATE_SUBDIRS]
    specs += [f"data/lore/core/{sub}" for sub in _LORE_SUBDIRS]
    specs.append("data/state/core/world/state.json")
    return specs


def _repo_root(override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def _clear_dir(directory: Path) -> list[Path]:
    """Remove every entry in *directory* except names in ``_KEEP``.

    Returns the list of removed paths. A no-op for a missing directory.
    """
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    for entry in sorted(directory.iterdir()):
        if entry.name in _KEEP:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            # Files and symlinks (including symlinks to directories, which
            # shutil.rmtree would raise on) are removed with unlink().
            entry.unlink()
        removed.append(entry)
    return removed


def reset_world(root: Path) -> list[Path]:
    """Clear per-playthrough state/lore under *root* and reset world state.

    Pure filesystem — no git. Returns the removed playthrough paths.
    """
    core_state = root / "data" / "state" / "core"
    core_lore = root / "data" / "lore" / "core"

    removed: list[Path] = []
    for sub in _STATE_SUBDIRS:
        removed.extend(_clear_dir(core_state / sub))
    for sub in _LORE_SUBDIRS:
        removed.extend(_clear_dir(core_lore / sub))

    world_file = core_state / "world" / "state.json"
    world_file.parent.mkdir(parents=True, exist_ok=True)
    world_file.write_text(
        json.dumps(_BASELINE_WORLD, indent=2) + "\n", encoding="utf-8"
    )

    return removed


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        sys.exit("error: 'git' not found — install Git and ensure it is on PATH.")
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or f"git {' '.join(args)} failed\n")
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset the canonical world state to an empty baseline."
    )
    parser.add_argument(
        "--root",
        help="Repo root (defaults to the repo this script lives in). Mainly for tests.",
    )
    parser.add_argument(
        "--snapshot",
        metavar="NAME",
        help="Tag the current HEAD as 'snapshot/<NAME>' before resetting, "
        "so this run stays recoverable for comparison.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Stage the reset but do not commit it.",
    )
    args = parser.parse_args(argv)

    root = _repo_root(args.root)
    if not (root / "data" / "state" / "core").is_dir():
        print(
            f"error: {root} does not look like a Sentinel repo (no data/state/core/).",
            file=sys.stderr,
        )
        return 2

    if args.snapshot:
        tag = f"snapshot/{args.snapshot}"
        _git(root, "tag", tag)
        print(f"tagged current HEAD as {tag}")

    removed = reset_world(root)
    print(
        f"reset: removed {len(removed)} playthrough file(s); "
        "world/state.json reset to empty baseline."
    )

    # Stage / inspect / commit ONLY the reset's own paths, so a run never
    # sweeps in unrelated edits elsewhere under data/.
    specs = _reset_pathspecs()
    _git(root, "add", "--", *specs)
    if args.no_commit:
        print("staged the reset (--no-commit); review and commit when ready.")
        return 0

    if not _git(root, "status", "--porcelain", "--", *specs).stdout.strip():
        print("nothing to commit — world already at baseline.")
        return 0

    _git(
        root,
        "commit",
        "-s",
        "-m",
        "chore(world): reset to empty baseline",
        "--",
        *specs,
    )
    print("committed: chore(world): reset to empty baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

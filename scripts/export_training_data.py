#!/usr/bin/env python3
"""Export recorded mock sessions into training-ready datasets.

Reads the recorded session files under ``data/state/core/sessions/*.json``
and emits two artifacts under ``datasets/`` (gitignored):

1. ``datasets/schema/<session>.jsonl`` — one example per turn for training
   schema recognition (narrative → canonical ``apply_world_update`` payload).
2. ``datasets/chatlogs/<session>.md`` — the raw player↔DM transcript in a
   ``file-observer``-detectable speaker-labelled format.

The per-session builders live in ``backend.datasets`` (shared with the
``/api/sessions/{id}/export`` endpoint); this script is the headless/bulk
CLI over the whole sessions tree. Raw capture — no ratings or corrections.
Cross-OS: pure Python + the engine package.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Import the shared builders the same way the backend does (run from repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.datasets import (  # noqa: E402
    build_chatlog,
    build_schema_examples,
    safe_label,
)

# Re-exported so importers (and tests) can reach the builders via this module.
__all__ = ["build_chatlog", "build_schema_examples", "safe_label", "export", "main"]

_SESSIONS_REL = Path("data") / "state" / "core" / "sessions"


def export(root: Path, out: Path) -> dict:
    sessions_dir = root / _SESSIONS_REL
    schema_dir = out / "schema"
    chatlog_dir = out / "chatlogs"
    # Clear prior output so a re-run reflects exactly the current sessions —
    # no stale files left behind by deleted/renamed sessions.
    for managed in (schema_dir, chatlog_dir):
        if managed.exists():
            shutil.rmtree(managed)
        managed.mkdir(parents=True, exist_ok=True)

    stats = {"sessions": 0, "examples": 0, "skipped": 0, "chatlogs": 0}
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(session, dict) or not isinstance(session.get("turns"), list):
            continue
        if not session["turns"]:
            continue
        sid = session.get("session_id", path.stem)
        stats["sessions"] += 1

        examples, skipped = build_schema_examples(session)
        stats["examples"] += len(examples)
        stats["skipped"] += skipped
        if examples:
            (schema_dir / f"{sid}.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in examples), encoding="utf-8"
            )

        (chatlog_dir / f"{sid}.md").write_text(build_chatlog(session), encoding="utf-8")
        stats["chatlogs"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", help="Repo root (defaults to this repo).")
    parser.add_argument("--out", help="Output dir (defaults to <root>/datasets).")
    args = parser.parse_args(argv)

    root = (
        Path(args.root).resolve()
        if args.root
        else Path(__file__).resolve().parent.parent
    )
    out = Path(args.out).resolve() if args.out else root / "datasets"

    if not (root / _SESSIONS_REL).is_dir():
        print(f"error: no sessions dir at {root / _SESSIONS_REL}", file=sys.stderr)
        return 2

    stats = export(root, out)
    print(
        f"exported {stats['sessions']} session(s) → {out}:\n"
        f"  schema/   {stats['examples']} example(s) "
        f"({stats['skipped']} turn(s) skipped — no schema-valid target)\n"
        f"  chatlogs/ {stats['chatlogs']} transcript(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

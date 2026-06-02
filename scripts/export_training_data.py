#!/usr/bin/env python3
"""Export recorded mock sessions into training-ready datasets.

Reads the recorded session files under ``data/state/core/sessions/*.json``
(each holds the full turn log: player_action + narrative + the DM's
``world_updates`` hint block) and emits two artifacts under ``datasets/``:

1. ``datasets/schema/<session>.jsonl`` — one example per turn for training
   *schema recognition* (narrative → structured world state):

       {"input":  {"player_action", "narrative", "world_before"},
        "target": <apply_world_update.schema.json-valid payload>,
        "meta":   {session_id, turn, world_name, persona, character, ...}}

   The target is the CANONICAL apply_world_update payload, derived by
   reconstructing the DM's ``<world_update>`` block from the stored hint
   and running it back through ``engine.agents.fact_extractor`` (the same
   transform the live turn loop uses). Turns whose block produces no
   schema-valid payload are skipped (and counted).

2. ``datasets/chatlogs/<session>.md`` — the raw player↔DM transcript, in a
   speaker-labelled format that ``file-observer``'s chatlog detector
   recognises (``^[A-Z][a-zA-Z0-9_]{0,15}:\\s`` speaker labels + ``---``
   dividers + ``###`` header). Labels use the recorded character / persona
   names, sanitised to satisfy that regex (fallback: ``Player`` / ``DM``).

Raw capture — no ratings or corrections. Cross-OS: pure Python + the engine
package; no shell-isms.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Import the engine the same way the backend does (run from repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.agents import fact_extractor  # noqa: E402

_SESSIONS_REL = Path("data") / "state" / "core" / "sessions"
_ENTITY_KEYS = ("characters", "locations", "factions", "items")
# Mirrors file_observer.scanner.CHATLOG_SPEAKER_LABEL_RE (schema 1.3): a
# speaker label is a capitalised identifier (<=16 chars, [A-Za-z0-9_]) then
# ": ". We sanitise names to fit so the chatlog vector detects our exports.
_LABEL_MAX = 16


def safe_label(name: str | None, fallback: str) -> str:
    """Turn a display name into a file-observer-detectable speaker label."""
    if not name:
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.strip()).strip("_")
    if not cleaned:
        return fallback
    if not cleaned[0].isalpha():
        cleaned = "X" + cleaned
    cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned[:_LABEL_MAX]


def _one_line(text: str) -> str:
    """Collapse a player action to a single line (keeps the label intact)."""
    return " ".join((text or "").split())


def build_chatlog(session: dict) -> str:
    """Render a session as a speaker-labelled markdown transcript."""
    sid = session.get("session_id", "")
    world = session.get("world_name", "Unknown World")
    persona = session.get("dm_persona_name", "")
    player_label = safe_label(session.get("player_character_name"), "Player")
    dm_label = safe_label(persona, "DM")

    header = f"### {world}" + (f" — {persona}" if persona else "") + f" — {sid[:8]}"
    blocks: list[str] = [header, ""]
    for turn in session.get("turns", []):
        action = _one_line(turn.get("player_action", ""))
        narrative = (turn.get("narrative", "") or "").strip()
        if action:
            blocks.append(f"{player_label}: {action}")
            blocks.append("")
        if narrative:
            blocks.append(f"{dm_label}: {narrative}")
            blocks.append("")
        blocks.append("---")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def _known_names(seen: dict[str, set]) -> dict[str, list]:
    return {k: sorted(seen[k]) for k in _ENTITY_KEYS}


def build_schema_examples(session: dict) -> tuple[list[dict], int]:
    """Yield (examples, skipped) — one canonical schema example per turn."""
    sid = session.get("session_id", "")
    examples: list[dict] = []
    skipped = 0
    seen: dict[str, set] = {k: set() for k in _ENTITY_KEYS}

    for turn in session.get("turns", []):
        hint = turn.get("world_updates") or {}
        narrative = turn.get("narrative", "") or ""
        # Reconstruct the DM block and run the real extractor → canonical payload.
        raw = f"{narrative}\n<world_update>\n{json.dumps(hint)}\n</world_update>"
        result = fact_extractor.extract(
            raw, session_id=sid, turn_number=turn.get("turn_number", 0)
        )
        if result.payload is None:
            skipped += 1
        else:
            examples.append(
                {
                    "input": {
                        "player_action": turn.get("player_action", ""),
                        "narrative": narrative,
                        "world_before": _known_names(seen),
                    },
                    "target": result.payload,
                    "meta": {
                        "session_id": sid,
                        "turn": turn.get("turn_number", 0),
                        "world_name": session.get("world_name", ""),
                        "persona": session.get("dm_persona_name", ""),
                        "character": session.get("player_character_name", ""),
                        "created_at": turn.get("created_at", ""),
                    },
                }
            )
        # Fold this turn's entities into the running "known" set so the
        # NEXT turn's world_before reflects state before it.
        for key in _ENTITY_KEYS:
            for entity in hint.get(key, []) or []:
                if isinstance(entity, dict) and entity.get("name"):
                    seen[key].add(entity["name"])

    return examples, skipped


def export(root: Path, out: Path) -> dict:
    sessions_dir = root / _SESSIONS_REL
    schema_dir = out / "schema"
    chatlog_dir = out / "chatlogs"
    schema_dir.mkdir(parents=True, exist_ok=True)
    chatlog_dir.mkdir(parents=True, exist_ok=True)

    stats = {"sessions": 0, "examples": 0, "skipped": 0, "chatlogs": 0}
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(session, dict) or not session.get("turns"):
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

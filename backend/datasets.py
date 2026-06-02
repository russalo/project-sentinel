"""Turn recorded session files into training data.

Pure builders shared by the CLI exporter (``scripts/export_training_data.py``)
and the ``/api/sessions/{id}/export`` endpoint. Given a *session dict* (the
shape written to ``data/state/core/sessions/*.json``), produce:

  - ``build_schema_examples`` — schema-recognition examples, one per turn,
    whose ``target`` is the canonical ``apply_world_update`` payload (derived
    by replaying the DM's ``<world_update>`` hint through the Fact-Extractor).
  - ``build_chatlog`` — a file-observer-detectable speaker-labelled transcript.

No filesystem or I/O here — callers own reading sessions and writing output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from engine.agents import fact_extractor

_ENTITY_KEYS = ("characters", "locations", "factions", "items")
# Mirrors file_observer.scanner.CHATLOG_SPEAKER_LABEL_RE (schema 1.3): a speaker
# label is a capitalised identifier (<=16 chars, [A-Za-z0-9_]) then ": ". We
# sanitise names to fit so the chatlog vector detects our exports.
_LABEL_MAX = 16


def safe_label(name: str | None, fallback: str) -> str:
    """Turn a display name into a file-observer-detectable speaker label."""
    if not isinstance(name, str):
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
    examples: list[dict[str, Any]] = []
    skipped = 0
    seen: dict[str, set] = {k: set() for k in _ENTITY_KEYS}

    for turn in session.get("turns", []):
        hint = turn.get("world_updates")
        if not isinstance(hint, dict):
            hint = {}  # tolerate malformed LLM output (list/str/None)
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
        # Fold this turn's entities into the running "known" set so the NEXT
        # turn's world_before reflects state before it.
        for key in _ENTITY_KEYS:
            value = hint.get(key)
            if not isinstance(value, list):
                continue  # tolerate malformed (non-list) collections
            for entity in value:
                if isinstance(entity, dict) and entity.get("name"):
                    seen[key].add(entity["name"])

    return examples, skipped

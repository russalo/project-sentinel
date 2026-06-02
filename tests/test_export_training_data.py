"""Tests for scripts/export_training_data.py.

Runs the exporter against a fixture session tree (never the real repo) and
asserts: schema targets are apply_world_update-valid, the chatlog matches
file-observer's chatlog speaker-label contract, world_before accumulates,
and labels are sanitised for detection.
"""

import importlib.util
import json
import re
from pathlib import Path

import engine

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_training_data.py"
_UUID = "123e4567-e89b-12d3-a456-426614174000"

# Mirrors file_observer.scanner.CHATLOG_SPEAKER_LABEL_RE (schema 1.3). The real
# tool already confirms detection (manifest is_chatlog=true); this guards the
# format so a refactor can't silently break it without file-observer installed.
_SPEAKER_RE = re.compile(r"^[A-Z][a-zA-Z0-9_]{0,15}:\s", re.MULTILINE)


def _load():
    spec = importlib.util.spec_from_file_location("export_training_data", _SCRIPT)
    assert spec and spec.loader, f"could not load {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load()


def _make_tree(root: Path) -> None:
    sdir = root / "data" / "state" / "core" / "sessions"
    sdir.mkdir(parents=True)
    session = {
        "session_id": _UUID,
        "world_name": "Test Realm",
        "started_at": "",
        "active": True,
        "player_character_name": "Cowboy Bob",  # space → must sanitise to Cowboy_Bob
        "dm_persona_name": "Oracle",
        "turns": [
            {
                "turn_number": 0,
                "player_action": "[Session Start] Bob begins.",
                "narrative": "You arrive at the dusty crossroads.",
                "world_updates": {
                    "world": {"tension": 3},
                    "characters": [
                        {
                            "name": "Mira",
                            "action": "upsert",
                            "status": "alive",
                            "role": "npc",
                        }
                    ],
                },
            },
            {
                "turn_number": 1,
                "player_action": "talk to Mira",
                "narrative": "She nods slowly.",
                "world_updates": {
                    "characters": [
                        {
                            "name": "Mira",
                            "action": "upsert",
                            "status": "alive",
                            "role": "ally",
                        }
                    ]
                },
            },
        ],
    }
    (sdir / f"{_UUID}.json").write_text(json.dumps(session), encoding="utf-8")


def test_export_produces_both_artifacts(tmp_path):
    _make_tree(tmp_path)
    stats = exporter.export(tmp_path, tmp_path / "datasets")
    assert stats["sessions"] == 1
    assert (tmp_path / "datasets" / "schema" / f"{_UUID}.jsonl").exists()
    assert (tmp_path / "datasets" / "chatlogs" / f"{_UUID}.md").exists()


def test_schema_targets_validate_against_apply_world_update(tmp_path):
    _make_tree(tmp_path)
    exporter.export(tmp_path, tmp_path / "datasets")
    lines = (
        (tmp_path / "datasets" / "schema" / f"{_UUID}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 2
    for line in lines:
        ex = json.loads(line)
        result = engine.validate(ex["target"])
        assert result.ok, result.errors


def test_chatlog_matches_file_observer_speaker_contract(tmp_path):
    _make_tree(tmp_path)
    exporter.export(tmp_path, tmp_path / "datasets")
    md = (tmp_path / "datasets" / "chatlogs" / f"{_UUID}.md").read_text(
        encoding="utf-8"
    )
    # Speaker labels present and detector-shaped; spaces sanitised to underscore.
    assert "Cowboy_Bob: " in md
    assert "Oracle: " in md
    assert "### Test Realm" in md
    assert "\n---" in md
    speaker_lines = [ln for ln in md.splitlines() if ln[:1].isupper() and ": " in ln]
    assert speaker_lines
    for ln in speaker_lines:
        assert _SPEAKER_RE.match(ln), f"label not file-observer-detectable: {ln!r}"


def test_world_before_accumulates_across_turns(tmp_path):
    _make_tree(tmp_path)
    exporter.export(tmp_path, tmp_path / "datasets")
    examples = [
        json.loads(ln)
        for ln in (tmp_path / "datasets" / "schema" / f"{_UUID}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    # Turn 0 saw no prior entities; turn 1's world_before knows Mira.
    assert examples[0]["input"]["world_before"]["characters"] == []
    assert "Mira" in examples[1]["input"]["world_before"]["characters"]


def test_safe_label_sanitises_for_detector():
    assert exporter.safe_label("Cowboy Bob", "Player") == "Cowboy_Bob"
    assert exporter.safe_label("Mir Halder", "DM") == "Mir_Halder"
    assert exporter.safe_label("", "Player") == "Player"
    assert exporter.safe_label("   ", "DM") == "DM"
    # Capitalised start, <=16 chars, only [A-Za-z0-9_].
    label = exporter.safe_label("a-very-long-persona-name-here", "DM")
    assert _SPEAKER_RE.match(label + ": x") and len(label) <= 16

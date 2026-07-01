"""Backend (IO) Lorekeeper retrieval — RFC-0011.

``retrieve_canon`` subprocesses ``poggio``. Tests mock ``subprocess.run`` so
there is no live dependency (poggio isn't installable in CI). The contract
under test: dormant when disabled (no subprocess), fail-open on any failure,
and a correct lean projection + dedup of the hits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace


from backend.state import lorekeeper


def _ctx(location="Hallowrun Inn"):
    return SimpleNamespace(current_location=location)


def _settings(enabled=True, poggio_bin="poggio"):
    return SimpleNamespace(lorekeeper_enabled=enabled, poggio_bin=poggio_bin)


def _proc(stdout):
    return SimpleNamespace(stdout=stdout, returncode=0)


def test_dormant_when_disabled_does_not_subprocess(monkeypatch):
    called = []
    monkeypatch.setattr(
        lorekeeper.subprocess, "run", lambda *a, **k: called.append(a) or _proc("[]")
    )
    out = lorekeeper.retrieve_canon(
        Path("/w/data"), _ctx(), "act", _settings(enabled=False)
    )
    assert out == []
    assert called == []  # short-circuit before any IO


def test_fail_open_on_missing_binary(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("poggio not on PATH")

    monkeypatch.setattr(lorekeeper.subprocess, "run", boom)
    # No raise — degrades to [].
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_fail_open_on_nonzero_exit(monkeypatch):
    def fail(*a, **k):
        raise subprocess.CalledProcessError(1, "poggio")

    monkeypatch.setattr(lorekeeper.subprocess, "run", fail)
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_fail_open_on_bad_json(monkeypatch):
    monkeypatch.setattr(lorekeeper.subprocess, "run", lambda *a, **k: _proc("not json"))
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_lean_projection_and_world_root(monkeypatch):
    seen_cmds = []

    entity_hit = {
        "id": "chez",
        "kind": "character",
        "source": "data/state/core/entities/chez.json",
        "attrs": {"name": "Chez", "description": "Chaingang boss", "level": 1},
    }
    turn_hit = {
        "id": "sess:t1",
        "kind": "turn",
        "source": "data/state/core/sessions/sess.json",
        "snippet": "the millstones remember",
        "attrs": {"turn_number": 1, "session_id": "sess"},
    }

    def fake_run(cmd, **k):
        seen_cmds.append(cmd)
        recipe = cmd[cmd.index("--recipe") + 1]
        payload = [entity_hit] if recipe == "at-location" else [turn_hit]
        return _proc(json.dumps(payload))

    monkeypatch.setattr(lorekeeper.subprocess, "run", fake_run)
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "millstones", _settings())

    # world root is the parent of data/
    assert any("--world" in c and "/w" in c[c.index("--world") + 1] for c in seen_cmds)
    # lean shape only
    assert out[0] == {
        "id": "chez",
        "kind": "character",
        "name": "Chez",
        "source": "data/state/core/entities/chez.json",
        "snippet": "Chaingang boss",  # entity → description
    }
    turn = [h for h in out if h["kind"] == "turn"][0]
    assert turn["name"] == "prior turn 1"  # turn labelled by number
    assert turn["snippet"] == "the millstones remember"


def test_dedup_by_id_across_recipes(monkeypatch):
    dup = {"id": "chez", "kind": "character", "source": "s", "attrs": {"name": "Chez"}}
    monkeypatch.setattr(
        lorekeeper.subprocess, "run", lambda *a, **k: _proc(json.dumps([dup]))
    )
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert [h["id"] for h in out] == ["chez"]  # not duplicated across the 2 recipes


def test_nowhere_location_skips_at_location(monkeypatch):
    recipes = []
    monkeypatch.setattr(
        lorekeeper.subprocess,
        "run",
        lambda cmd, **k: recipes.append(cmd[cmd.index("--recipe") + 1]) or _proc("[]"),
    )
    lorekeeper.retrieve_canon(
        Path("/w/data"), _ctx(location="Nowhere"), "act", _settings()
    )
    assert "at-location" not in recipes  # placeholder location isn't queried

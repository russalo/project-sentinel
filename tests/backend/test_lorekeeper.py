"""Backend (IO) Lorekeeper retrieval — RFC-0011 (fold) + RFC-0012 (v0.2.0).

``retrieve_canon`` subprocesses ``poggio``. Tests mock ``subprocess.run`` so
there is no live dependency (poggio isn't installable in CI). RFC-0012: poggio
emits the **lean** hit shape directly, and the fold asserts
``poggio schema-version == 0.2`` once per process before trusting any output.
The mock therefore answers both the ``schema-version`` probe and the recipe
queries. Contract under test: dormant when disabled, schema-gated + fail-open,
and a correct lean pass-through + dedup.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.state import lorekeeper


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    # The schema-version verdict is cached per process; clear it between tests
    # so each exercises the probe fresh.
    lorekeeper._schema_ok_cache.clear()
    yield
    lorekeeper._schema_ok_cache.clear()


def _ctx(location="Hallowrun Inn"):
    return SimpleNamespace(current_location=location)


def _settings(enabled=True, poggio_bin="poggio"):
    return SimpleNamespace(lorekeeper_enabled=enabled, poggio_bin=poggio_bin)


def _proc(stdout):
    return SimpleNamespace(stdout=stdout, returncode=0)


def _mock_run(hits, *, schema="0.2", query_raises=None):
    """Build a subprocess.run stand-in: answer `schema-version` with `schema`
    (a str, or an Exception instance to raise), and recipe queries with `hits`
    (or raise `query_raises`)."""

    def run(cmd, **kwargs):
        if "schema-version" in cmd:
            if isinstance(schema, BaseException):
                raise schema
            return _proc(schema)
        if query_raises is not None:
            raise query_raises
        return _proc(json.dumps(hits))

    return run


_LEAN_ENTITY = {
    "id": "chez",
    "kind": "character",
    "name": "Chez",
    "source": "data/state/core/entities/chez.json",
    "snippet": "Chaingang boss with a head full of unspoken questions",
}
_LEAN_TURN = {
    "id": "sess:t1",
    "kind": "turn",
    "name": "prior turn 1",
    "source": "data/state/core/sessions/sess.json",
    "snippet": "the millstones remember",
}


# ── dormant + schema gate ───────────────────────────────────────────


def test_dormant_when_disabled_does_not_subprocess(monkeypatch):
    called = []
    monkeypatch.setattr(
        lorekeeper.subprocess, "run", lambda *a, **k: called.append(a) or _proc("0.2")
    )
    out = lorekeeper.retrieve_canon(
        Path("/w/data"), _ctx(), "act", _settings(enabled=False)
    )
    assert out == []
    assert called == []  # short-circuit before any IO (even the schema probe)


def test_schema_mismatch_disables_retrieval(monkeypatch):
    # A wrong/old binary reporting a different schema → no canon (fail-open loud).
    monkeypatch.setattr(
        lorekeeper.subprocess, "run", _mock_run([_LEAN_ENTITY], schema="0.1")
    )
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_schema_probe_error_disables_retrieval(monkeypatch):
    # poggio not on PATH → the probe raises → retrieval disabled, no raise.
    monkeypatch.setattr(
        lorekeeper.subprocess,
        "run",
        _mock_run([_LEAN_ENTITY], schema=FileNotFoundError("poggio not on PATH")),
    )
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_schema_probe_is_cached_once_per_process(monkeypatch):
    probes = {"n": 0}

    def run(cmd, **k):
        if "schema-version" in cmd:
            probes["n"] += 1
            return _proc("0.2")
        return _proc(json.dumps([_LEAN_ENTITY]))

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act2", _settings())
    assert probes["n"] == 1  # probed once, cached thereafter


def test_schema_probe_uses_short_timeout(monkeypatch):
    # The version probe is trivial; it must not carry the full retrieval timeout
    # (it runs synchronously in the turn path) — gemini-medium on PR #166.
    seen = {}

    def run(cmd, **kwargs):
        if "schema-version" in cmd:
            seen.update(kwargs)
            return _proc("0.2")
        return _proc(json.dumps([_LEAN_ENTITY]))

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert seen.get("timeout") == lorekeeper._SCHEMA_TIMEOUT_S
    assert lorekeeper._SCHEMA_TIMEOUT_S < lorekeeper._TIMEOUT_S


# ── recipe fail-open (schema OK) ────────────────────────────────────


def test_fail_open_on_recipe_error(monkeypatch):
    monkeypatch.setattr(
        lorekeeper.subprocess,
        "run",
        _mock_run([], query_raises=subprocess.CalledProcessError(1, "poggio")),
    )
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


def test_fail_open_on_bad_json(monkeypatch):
    def run(cmd, **k):
        return _proc("0.2" if "schema-version" in cmd else "not json")

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    assert lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings()) == []


# ── lean pass-through ───────────────────────────────────────────────


def test_lean_pass_through_and_world_root(monkeypatch):
    seen_cmds = []

    def run(cmd, **k):
        seen_cmds.append(cmd)
        if "schema-version" in cmd:
            return _proc("0.2")
        recipe = cmd[cmd.index("--recipe") + 1]
        payload = [_LEAN_ENTITY] if recipe == "at-location" else [_LEAN_TURN]
        return _proc(json.dumps(payload))

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "millstones", _settings())

    # world root is the parent of data/
    query_cmds = [c for c in seen_cmds if "query" in c]
    assert all("/w" == c[c.index("--world") + 1] for c in query_cmds)
    # lean hits pass through unchanged (no derivation, no re-truncation)
    assert out[0] == _LEAN_ENTITY
    assert any(h == _LEAN_TURN for h in out)


def test_snippet_not_re_truncated(monkeypatch):
    # poggio truncates at the source; the consumer must not double-cut. A long
    # snippet passes through verbatim.
    long_hit = {**_LEAN_ENTITY, "snippet": "x" * 300}
    monkeypatch.setattr(lorekeeper.subprocess, "run", _mock_run([long_hit]))
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert out[0]["snippet"] == "x" * 300


def test_dedup_by_id_across_recipes(monkeypatch):
    monkeypatch.setattr(lorekeeper.subprocess, "run", _mock_run([_LEAN_ENTITY]))
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert [h["id"] for h in out] == ["chez"]  # not duplicated across the 2 recipes


def test_non_scalar_id_is_skipped_not_crashed(monkeypatch):
    # A malformed hit with a list `id` must not raise TypeError: unhashable in
    # the dedup set — it's skipped (defensive guard kept from Slice 1).
    bad = {
        "id": ["bad"],
        "kind": "character",
        "name": "X",
        "source": "s",
        "snippet": "",
    }
    monkeypatch.setattr(lorekeeper.subprocess, "run", _mock_run([bad, _LEAN_ENTITY]))
    out = lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert [h["id"] for h in out] == ["chez"]  # bad skipped, good kept, no raise


def test_nowhere_location_skips_at_location(monkeypatch):
    recipes = []

    def run(cmd, **k):
        if "schema-version" in cmd:
            return _proc("0.2")
        recipes.append(cmd[cmd.index("--recipe") + 1])
        return _proc("[]")

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    lorekeeper.retrieve_canon(
        Path("/w/data"), _ctx(location="Nowhere"), "act", _settings()
    )
    assert "at-location" not in recipes  # placeholder location isn't queried


def test_query_decodes_as_utf8(monkeypatch):
    # Force UTF-8 decoding regardless of host locale (Windows CP1252 would
    # mangle non-ASCII lore) — retained from the PR #165 hardening.
    seen = {}

    def run(cmd, **kwargs):
        if "query" in cmd:
            seen.update(kwargs)
        return _proc("0.2" if "schema-version" in cmd else json.dumps([_LEAN_ENTITY]))

    monkeypatch.setattr(lorekeeper.subprocess, "run", run)
    lorekeeper.retrieve_canon(Path("/w/data"), _ctx(), "act", _settings())
    assert seen.get("encoding") == "utf-8"

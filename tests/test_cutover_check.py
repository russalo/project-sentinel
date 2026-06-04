"""Tests for scripts/cutover-check.py — the A4 pre-cutover readiness check.

Exercises the pure ``check(env, fetch=...)`` core with an injected env dict + a
fake /health fetch (no real network, no real filesystem beyond tmp). Covers the
ready path and each FAIL / WARN mode.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "cutover-check.py"


def _load():
    spec = importlib.util.spec_from_file_location("cutover_check", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load()


def _statuses(results):
    return {r["check"]: r["status"] for r in results}


def _ready_env(worlds_root: str) -> dict:
    # A fully-armed public cutover env.
    return {
        "SENTINEL_WORLDS_ROOT": worlds_root,
        "SENTINEL_SESSION_TOKEN_SECRET": "s3cret",
        "SENTINEL_LLM_DAILY_CEILING": "2000",
    }


def _both_agree(url):
    return {"worlds_root": True}


def test_ready_env_has_no_failures(tmp_path):
    env = _ready_env(str(tmp_path))
    results = cc.check(env, fetch=_both_agree)
    assert not [r for r in results if r["status"] == cc.FAIL]
    st = _statuses(results)
    assert st["SENTINEL_WORLDS_ROOT"] == cc.PASS
    assert st["fs-manager /health"] == cc.PASS
    assert st["git-sync /health"] == cc.PASS
    assert st["SENTINEL_SESSION_TOKEN_SECRET"] == cc.PASS
    assert st["rate limits"] == cc.PASS


def test_worlds_root_unset_fails(tmp_path):
    env = _ready_env("")
    results = cc.check(env, fetch=_both_agree)
    assert _statuses(results)["SENTINEL_WORLDS_ROOT"] == cc.FAIL


def test_worlds_root_nonexistent_dir_fails():
    env = _ready_env("/no/such/dir/anywhere")
    results = cc.check(env, fetch=_both_agree)
    assert _statuses(results)["SENTINEL_WORLDS_ROOT"] == cc.FAIL


def test_mcp_disagreement_fails(tmp_path):
    env = _ready_env(str(tmp_path))
    # The health URLs are IP:port — fs-manager is :8010, git-sync :8012. Make
    # fs-manager agree and git-sync disagree.
    results = cc.check(env, fetch=lambda url: {"worlds_root": ":8010" in url})
    st = _statuses(results)
    assert st["fs-manager /health"] == cc.PASS
    assert st["git-sync /health"] == cc.FAIL


def test_mcp_unreachable_fails(tmp_path):
    def boom(url):
        raise ConnectionError("refused")

    env = _ready_env(str(tmp_path))
    results = cc.check(env, fetch=boom)
    st = _statuses(results)
    assert st["fs-manager /health"] == cc.FAIL
    assert st["git-sync /health"] == cc.FAIL


def test_public_bind_optin_fails(tmp_path):
    env = _ready_env(str(tmp_path))
    env["SENTINEL_ALLOW_PUBLIC_BIND"] = "1"
    results = cc.check(env, fetch=_both_agree)
    assert _statuses(results)["SENTINEL_ALLOW_PUBLIC_BIND"] == cc.FAIL


def test_public_bind_falsey_passes(tmp_path):
    env = _ready_env(str(tmp_path))
    env["SENTINEL_ALLOW_PUBLIC_BIND"] = "0"  # falsey → not opted in
    results = cc.check(env, fetch=_both_agree)
    assert _statuses(results)["SENTINEL_ALLOW_PUBLIC_BIND"] == cc.PASS


def test_no_token_secret_warns_not_fails(tmp_path):
    env = _ready_env(str(tmp_path))
    env.pop("SENTINEL_SESSION_TOKEN_SECRET")
    results = cc.check(env, fetch=_both_agree)
    st = _statuses(results)
    assert st["SENTINEL_SESSION_TOKEN_SECRET"] == cc.WARN
    assert not [r for r in results if r["status"] == cc.FAIL]


def test_all_zero_rate_limits_warns_not_fails(tmp_path):
    env = {"SENTINEL_WORLDS_ROOT": str(tmp_path), "SENTINEL_SESSION_TOKEN_SECRET": "x"}
    results = cc.check(env, fetch=_both_agree)
    st = _statuses(results)
    assert st["rate limits"] == cc.WARN
    assert not [r for r in results if r["status"] == cc.FAIL]


def test_env_parser_handles_export_quotes_and_comments():
    text = "\n".join(
        [
            "# a comment",
            "",
            "export SENTINEL_WORLDS_ROOT=/srv/worlds",
            'SENTINEL_SESSION_TOKEN_SECRET="s3 cret"',
            "OPENAI_BASE_URL=http://h:4000/v1",  # '=' is fine in the URL, but no extra '='
            "DM_MODEL='qwen3-32b'",
        ]
    )
    env = cc._parse_env_text(text)
    assert env["SENTINEL_WORLDS_ROOT"] == "/srv/worlds"  # export stripped
    assert env["SENTINEL_SESSION_TOKEN_SECRET"] == "s3 cret"  # quotes stripped
    assert env["OPENAI_BASE_URL"] == "http://h:4000/v1"
    assert env["DM_MODEL"] == "qwen3-32b"  # single quotes stripped


def test_health_not_checked_when_worlds_root_unset():
    # No worlds_root → the cutover isn't on → don't ping (and don't add health rows).
    called = []

    def spy(url):
        called.append(url)
        return {"worlds_root": True}

    cc.check({"SENTINEL_WORLDS_ROOT": ""}, fetch=spy)
    assert called == []

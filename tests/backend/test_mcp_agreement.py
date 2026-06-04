"""Cutover config-agreement check (ADR 0002 / Path A-A2).

When the backend is in per-world mode (``SENTINEL_WORLDS_ROOT`` set), it must
refuse to start unless both MCP servers also report per-world mode — otherwise a
split-brain config silently writes to the wrong tree. ``fetch`` is injected so
these never touch the network.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.mcp_agreement import verify_world_mode_agreement


def _per_world(test_settings):
    return replace(test_settings, worlds_root="/tmp/worlds")


def test_noop_in_shared_mode_does_not_even_fetch(test_settings):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"worlds_root": True}

    verify_world_mode_agreement(test_settings, fetch=fetch)  # worlds_root=None
    assert calls == []  # shared mode → no health pings at all


def test_passes_when_both_servers_agree(test_settings):
    verify_world_mode_agreement(
        _per_world(test_settings), fetch=lambda url: {"worlds_root": True}
    )


def test_raises_when_a_server_disagrees(test_settings):
    # fs-manager reports false (git-sync true) → fs-manager named in the error.
    def fetch(url):
        return {"worlds_root": "git-sync" in url}

    with pytest.raises(RuntimeError, match="fs-manager"):
        verify_world_mode_agreement(_per_world(test_settings), fetch=fetch)


def test_raises_when_a_server_is_unreachable(test_settings):
    def fetch(url):
        raise ConnectionError("connection refused")

    with pytest.raises(RuntimeError, match="unreachable"):
        verify_world_mode_agreement(_per_world(test_settings), fetch=fetch)


def test_raises_on_non_dict_health_body(test_settings):
    with pytest.raises(RuntimeError):
        verify_world_mode_agreement(_per_world(test_settings), fetch=lambda url: "nope")


@pytest.mark.parametrize("truthy_nonbool", ["false", "true", 1, [True]])
def test_truthy_nonbool_worlds_root_is_not_agreement(test_settings, truthy_nonbool):
    # The /health contract is a real bool; a truthy non-bool (notably the string
    # "false") must not be read as agreement.
    with pytest.raises(RuntimeError):
        verify_world_mode_agreement(
            _per_world(test_settings), fetch=lambda url: {"worlds_root": truthy_nonbool}
        )

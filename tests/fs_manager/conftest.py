"""Pytest fixtures for the fs-manager MCP server tests.

Loads ``mcp-servers/fs-manager/server.py`` as a module, monkey-patches
its ``REPO_ROOT`` to point at a freshly-created ``tmp_path`` tree so
every test runs against an isolated filesystem, and returns a
``fastapi.testclient.TestClient`` wired to the app.

The fs-manager server is not a pnpm workspace package and lives
outside the standard pytest rootdir. We import it by adding its
directory to ``sys.path`` rather than making the whole mcp-servers
tree a package — that keeps the server's filesystem layout simple
and matches how it's executed in production (``python server.py``).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FS_MANAGER_DIR = REPO_ROOT / "mcp-servers" / "fs-manager"


@pytest.fixture
def fs_manager_module(monkeypatch, tmp_path):
    """Import fs-manager's ``server`` module with a tmp ``REPO_ROOT``.

    fs-manager resolves ``data/`` paths against its module-level
    ``REPO_ROOT`` at call time, so swapping that constant is enough
    to redirect every file operation into the tmp tree for the
    duration of the test. The schema stays loaded from the real
    ``schemas/`` directory because that's the contract we want to
    exercise.
    """
    # Prime sys.path so `import server` resolves to mcp-servers/fs-manager/server.py.
    # ``monkeypatch.syspath_prepend`` auto-restores sys.path after the
    # test, so unrelated tests that import other ``server`` modules
    # (there aren't any today, but forward-compat) stay isolated.
    monkeypatch.syspath_prepend(str(FS_MANAGER_DIR))

    # Fresh import each test — fs-manager's module-level state
    # (PROTECTED_FIELDS, PATH regexes, SCHEMA) must match the current
    # source on disk, not whatever an earlier test reloaded.
    if "server" in sys.modules:
        del sys.modules["server"]
    server = importlib.import_module("server")

    # Redirect the filesystem to tmp_path. The server uses REPO_ROOT
    # on every write, so changing it here makes every subsequent
    # ``abs_path = REPO_ROOT / target_file`` land under the tmp tree.
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)

    # Pre-create the canonical data/ layout so the update loop's
    # mkdir(parents=True, exist_ok=True) doesn't need to stretch
    # more than one level at a time. This is belt-and-suspenders —
    # the server creates parents on demand — but it also makes
    # intent explicit for anyone reading the tests.
    (tmp_path / "data" / "state" / "core").mkdir(parents=True)
    (tmp_path / "data" / "state" / "community").mkdir(parents=True)
    (tmp_path / "data" / "lore" / "core" / "sessions").mkdir(parents=True)
    (tmp_path / "data" / "lore" / "community").mkdir(parents=True)

    return server


@pytest.fixture
def client(fs_manager_module):
    """A TestClient bound to the fs-manager FastAPI app."""
    return TestClient(fs_manager_module.app)


@pytest.fixture
def session_uuid() -> str:
    """A stable UUID for tests that need one in the payload."""
    return "11111111-2222-3333-4444-555555555555"

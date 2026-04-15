"""Pytest fixtures for the git-sync MCP server tests.

Same shape as ``tests/fs_manager/conftest.py``: load
``mcp-servers/git-sync/server.py`` as a module, monkeypatch its
``REPO_ROOT`` constant to a freshly-initialized tmp git repo, and
return a ``fastapi.testclient.TestClient`` wired to the app.

Why a real git repo and not a mock: git-sync's whole job is to
produce real commits and read real history. Mocking ``git.Repo``
would test that we call gitpython correctly, not that gitpython
actually does what we think it does. A tmp repo is cheap (~5ms)
and exercises the real code path.

Why fresh module import per test: fs-manager's ``server.py`` and
git-sync's ``server.py`` both live under the top-level Python
module name ``server`` (each lives in its own directory). Without
clearing ``sys.modules['server']`` between tests, whichever
fixture ran first wins forever. Same defensive pattern as the
fs-manager conftest.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import git
import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GIT_SYNC_DIR = REPO_ROOT / "mcp-servers" / "git-sync"


def _init_tmp_git_repo(tmp_path: Path) -> git.Repo:
    """Create a fresh git repo at ``tmp_path`` ready for git-sync to commit into.

    Sets ``user.name`` and ``user.email`` (gitpython refuses to
    commit otherwise), creates the canonical ``data/state/core/``
    layout the server expects, and lands one initial commit so
    ``HEAD`` exists. Without that initial commit, the server's
    ``repo.index.diff("HEAD")`` check raises ``BadName`` instead
    of returning the empty diff, and every test would land in the
    InvalidGitRepositoryError branch for the wrong reason.
    """
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", "test@example.com")
        # Suppress the "init.defaultBranch" hint warning some git
        # versions emit on init; not load-bearing, just quieter logs.
        cw.set_value("init", "defaultBranch", "master")

    (tmp_path / "data" / "state" / "core").mkdir(parents=True)
    (tmp_path / "data" / "lore" / "core" / "sessions").mkdir(parents=True)

    # Initial commit so HEAD exists and the diff-vs-HEAD check has
    # something to compare against. The .gitkeep is intentionally
    # outside data/ so it doesn't show up as part of the data tree
    # the server commits later.
    keepfile = tmp_path / ".gitkeep"
    keepfile.write_text("")
    repo.index.add([".gitkeep"])
    repo.index.commit("initial commit")

    return repo


@pytest.fixture
def git_repo(tmp_path):
    """A fresh git.Repo at tmp_path with the canonical layout + HEAD."""
    return _init_tmp_git_repo(tmp_path)


@pytest.fixture
def git_sync_module(monkeypatch, tmp_path, git_repo):
    """Import git-sync's ``server`` module with REPO_ROOT pointing at tmp_path.

    Depends on ``git_repo`` so the tmp_path has a real git repo
    set up before the server module is imported and asked to read
    from it.
    """
    monkeypatch.syspath_prepend(str(GIT_SYNC_DIR))

    # Drop any cached `server` module — fs-manager and git-sync
    # both use that name for their FastAPI app file.
    if "server" in sys.modules:
        del sys.modules["server"]
    server = importlib.import_module("server")

    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    return server


@pytest.fixture
def client(git_sync_module):
    """A TestClient bound to the git-sync FastAPI app."""
    return TestClient(git_sync_module.app)


@pytest.fixture
def session_uuid() -> str:
    """A stable UUID for tests that need one in the request body."""
    return "11111111-2222-3333-4444-555555555555"

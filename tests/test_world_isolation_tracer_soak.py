"""Tracer-soak: deterministic proof of per-world isolation (ADR 0002 Slice 3).

THE cutover gate. Before ``SENTINEL_WORLDS_ROOT`` is flipped on in production,
this must prove — deterministically, in CI, never against a live LLM — that
concurrent worlds never leak into each other's trees.

How it works (per the File Observer team's tracer-soak recipe):

- Both MCP servers (fs-manager, git-sync) are loaded as real modules under
  *distinct* names (they both live at the module name ``server``, so a single
  process can normally only hold one — we sidestep that), with their
  ``WORLDS_ROOT`` pointed at a tmp worlds root and ``REPO_ROOT`` at a tmp
  *shared* tree (so a leak into the legacy shared tree is also detectable).
- The DM is **stubbed with a per-world token**: each world's writes carry only
  that world's token (its own ``world_id``). No LLM, no randomness, no sleeps.
- N worlds each run several turns through the **real engine→MCP dispatch path**
  (``engine.init_world`` / ``apply_world_update`` / ``commit_snapshot`` with an
  injected client that bridges to the live server apps), hammered concurrently.
- Assertions: every world's tree contains ONLY its own token; no token leaks
  into another world or into the shared tree; the backend read path
  (``resolve_world_data_dir`` + ``load_world_context``) sees only that world's
  state; each world's git repo holds its own ``world=<id[:8]>`` commit.

If this ever goes red, the cutover is unsafe — do not set SENTINEL_WORLDS_ROOT.
"""

from __future__ import annotations

import importlib.util
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import git
import httpx
import pytest
from fastapi.testclient import TestClient

import engine
from backend.state.world_context import load_world_context
from backend.state.world_root import resolve_world_data_dir

REPO = Path(__file__).resolve().parent.parent
N_WORLDS = 8
ROUNDS = 3


def _load_server(rel_path: str, mod_name: str):
    """Load a server.py under a unique module name (both live at `server`)."""
    spec = importlib.util.spec_from_file_location(mod_name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def soak_env(tmp_path, monkeypatch):
    """Live fs-manager + git-sync apps wired to a tmp worlds root + shared tree."""
    worlds_root = tmp_path / "worlds"
    worlds_root.mkdir()

    # A git-init'd shared tree as the legacy REPO_ROOT — if any write leaks to
    # the shared root instead of a world tree, it lands here and we catch it.
    shared = tmp_path / "shared"
    (shared / "data" / "state" / "core").mkdir(parents=True)
    (shared / "data" / "lore" / "core" / "sessions").mkdir(parents=True)
    shared_repo = git.Repo.init(shared)
    with shared_repo.config_writer() as cw:
        cw.set_value("user", "name", "Shared")
        cw.set_value("user", "email", "shared@localhost")
    (shared / ".gitkeep").write_text("")
    shared_repo.index.add([".gitkeep"])
    shared_repo.index.commit("shared init")

    fs = _load_server("mcp-servers/fs-manager/server.py", "fs_soak_server")
    gs = _load_server("mcp-servers/git-sync/server.py", "git_soak_server")
    for mod in (fs, gs):
        monkeypatch.setattr(mod, "WORLDS_ROOT", str(worlds_root))
        monkeypatch.setattr(mod, "REPO_ROOT", shared)

    return {
        "worlds_root": worlds_root,
        "shared": shared,
        "fs_app": fs.app,
        "git_app": gs.app,
    }


def _bridge_client(fs_app, git_app) -> httpx.Client:
    """A sync httpx.Client that forwards engine dispatch to the live apps.

    Routes by host: ``fs-manager.test`` → fs-manager app, else git-sync app.
    Each call gets fresh TestClients so concurrent worker threads don't share
    one client's portal.
    """
    fs_tc = TestClient(fs_app)
    git_tc = TestClient(git_app)

    def handler(request: httpx.Request) -> httpx.Response:
        tc = fs_tc if request.url.host == "fs-manager.test" else git_tc
        path = request.url.raw_path.decode("ascii")  # path + ?query
        fwd = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        r = tc.request(request.method, path, content=request.content, headers=fwd)
        return httpx.Response(
            r.status_code,
            content=r.content,
            headers={"content-type": r.headers.get("content-type", "application/json")},
        )

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="")


def _config() -> engine.Config:
    return engine.Config(
        openai_api_key="test-key",
        fs_manager_url="http://fs-manager.test",
        git_sync_url="http://git-sync.test",
    )


def _entity_payload(session_id: str, token: str, slug: str) -> dict:
    """A schema-valid apply_world_update that writes one token-bearing entity."""
    return {
        "namespace": "core",
        "session_id": session_id,
        "log_entry": f"tracer turn for {token}",
        "updates": [
            {
                "target_file": f"data/state/core/entities/{slug}.json",
                "operation": "create",
                "data": {"name": token, "token": token, "status": "alive"},
            }
        ],
    }


def test_tracer_soak_no_cross_world_leak(soak_env):
    config = _config()
    worlds_root: Path = soak_env["worlds_root"]
    shared: Path = soak_env["shared"]

    # Each world's token is its own world_id — a leak = one world's id appearing
    # in another world's tree.
    worlds = [str(uuid.uuid4()) for _ in range(N_WORLDS)]
    sessions = {wid: str(uuid.uuid4()) for wid in worlds}

    def run_world(world_id: str) -> None:
        client = _bridge_client(soak_env["fs_app"], soak_env["git_app"])
        try:
            init = engine.init_world(config, world_id=world_id, client=client)
            assert init.ok, init.error
            for r in range(ROUNDS):
                disp = engine.apply_world_update(
                    config,
                    _entity_payload(sessions[world_id], world_id, f"ent_{r}"),
                    world_id=world_id,
                    client=client,
                )
                assert disp.ok, disp.error
                commit = engine.commit_snapshot(
                    config,
                    session_id=sessions[world_id],
                    turn_number=r,
                    summary=f"turn {r}",
                    world_id=world_id,
                    client=client,
                )
                assert commit.ok, commit.error
        finally:
            client.close()

    # Hammer all worlds concurrently — repo-per-world should not contend.
    with ThreadPoolExecutor(max_workers=N_WORLDS) as pool:
        list(pool.map(run_world, worlds))

    all_tokens = set(worlds)

    # 1. Nothing leaked into the legacy shared tree.
    shared_entities = shared / "data" / "state" / "core" / "entities"
    assert not shared_entities.exists() or not list(shared_entities.glob("*.json")), (
        "writes leaked into the shared REPO_ROOT instead of a world tree"
    )

    # 2. Each world's tree contains ONLY its own token — no cross-world bleed.
    for world_id in worlds:
        world_data = worlds_root / world_id / "data"
        assert world_data.is_dir(), f"world {world_id[:8]} tree missing"
        present = set()
        for ent in (world_data / "state" / "core" / "entities").glob("*.json"):
            for tok in all_tokens:
                if tok in ent.read_text(encoding="utf-8"):
                    present.add(tok)
        assert present == {world_id}, (
            f"world {world_id[:8]} tree leaked tokens: {present - {world_id}}"
        )

    # 3. Backend read path sees only this world's state (read isolation).
    for world_id in worlds:
        data_dir = resolve_world_data_dir(
            str(worlds_root), world_id, default_data_dir=shared / "data"
        )
        ctx = load_world_context(data_dir)
        names = {c.get("name") for c in ctx.characters}
        assert names == {world_id}, (
            f"load_world_context for {world_id[:8]} saw foreign state: "
            f"{names - {world_id}}"
        )

    # 4. Each world's own git repo holds its tagged commits.
    for world_id in worlds:
        repo = git.Repo(worlds_root / world_id)
        msgs = "\n".join(c.message for c in repo.iter_commits("HEAD", max_count=10))
        assert f"world={world_id[:8]}" in msgs

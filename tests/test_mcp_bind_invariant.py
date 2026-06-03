"""MCP network-isolation invariant (ADR 0003 §3, Path A/A2).

The fs-manager and git-sync servers are the write layer and have no endpoint
auth — their safety is network topology (loopback/tailnet only; Caddy never
proxies :8010/:8012). These tests assert both servers default to loopback and
refuse an all-interfaces bind unless an operator explicitly opts in. Loads each
real server module (the tracer-soak pattern — both live at module name
``server``, so load under distinct names).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SERVERS = {
    "git-sync": _ROOT / "mcp-servers" / "git-sync" / "server.py",
    "fs-manager": _ROOT / "mcp-servers" / "fs-manager" / "server.py",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(params=list(_SERVERS), ids=list(_SERVERS))
def server(request):
    name = request.param
    return _load(_SERVERS[name], f"bindtest_{name.replace('-', '_')}")


def test_default_bind_is_loopback(server):
    assert server.DEFAULT_BIND_HOST == "127.0.0.1"


def test_loopback_and_specific_ip_allowed(server, monkeypatch):
    monkeypatch.delenv("SENTINEL_ALLOW_PUBLIC_BIND", raising=False)
    server._check_bind_host("127.0.0.1")  # loopback — no raise
    server._check_bind_host("100.119.83.49")  # a specific tailnet IP — allowed


@pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])
def test_all_interfaces_bind_refused(server, host, monkeypatch):
    monkeypatch.delenv("SENTINEL_ALLOW_PUBLIC_BIND", raising=False)
    with pytest.raises(SystemExit):
        server._check_bind_host(host)


@pytest.mark.parametrize("falsey", ["0", "false", "", "no", "off"])
def test_optin_falsey_values_still_refuse(server, falsey, monkeypatch):
    # The footgun: SENTINEL_ALLOW_PUBLIC_BIND=0 must NOT enable the override
    # (a bare truthiness check on os.environ.get would treat "0" as set).
    monkeypatch.setenv("SENTINEL_ALLOW_PUBLIC_BIND", falsey)
    with pytest.raises(SystemExit):
        server._check_bind_host("0.0.0.0")


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_optin_truthy_values_allow(server, truthy, monkeypatch):
    monkeypatch.setenv("SENTINEL_ALLOW_PUBLIC_BIND", truthy)
    server._check_bind_host("0.0.0.0")  # explicitly opted in — no raise

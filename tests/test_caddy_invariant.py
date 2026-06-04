"""The committed Caddy edge template must honor the ADR 0003 §3 isolation
invariant: proxy ONLY the backend (:8001), never the MCP write layer
(:8010/:8012); gate everything behind basic_auth except /healthz.

A text test, not `caddy validate` (Caddy isn't a CI dependency) — its job is to
make "Caddy never proxies the MCP ports / never un-gates the app" a *tested*
property of the shipped template, so a future edit that adds an :8010/:8012
route or drops the gate fails here instead of silently shipping.
"""

from pathlib import Path

import pytest

_CADDYFILE = (
    Path(__file__).resolve().parent.parent
    / "infrastructure"
    / "caddy"
    / "Caddyfile.example"
)


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return _CADDYFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def directives(caddyfile) -> str:
    # Config lines only — comment lines (which legitimately *name* the MCP ports
    # in the invariant note) are stripped, so the port test catches a real
    # reverse_proxy, not the warning about it.
    return "\n".join(
        ln for ln in caddyfile.splitlines() if not ln.strip().startswith("#")
    )


def test_template_exists(caddyfile):
    assert caddyfile.strip()


@pytest.mark.parametrize("mcp_port", [":8010", ":8012"])
def test_never_proxies_the_mcp_ports(directives, mcp_port):
    # The MCP write layer must never be reachable through the public edge — no
    # directive may reference its ports (comments may name them).
    assert mcp_port not in directives


def test_proxies_the_backend(caddyfile):
    assert "127.0.0.1:8001" in caddyfile


def test_gates_the_api_behind_basic_auth(caddyfile):
    assert "basic_auth" in caddyfile
    assert "/api/*" in caddyfile


def test_invite_hash_comes_from_env_not_committed(caddyfile):
    # The bcrypt hash must be an env placeholder, never a literal hash.
    assert "{$SENTINEL_INVITE_HASH}" in caddyfile
    assert "$2a$" not in caddyfile and "$2b$" not in caddyfile  # no bcrypt literal


def test_healthz_is_exempt_from_the_gate(caddyfile):
    # /healthz must be explicitly excluded from basic_auth (monitoring needs it
    # un-gated). A bare site-level basic_auth would gate it, so the exemption is
    # an explicit `not path /healthz` matcher.
    assert "not path /healthz" in caddyfile


def test_static_cache_headers_prevent_stale_index(caddyfile):
    # stale-cache-after-redeploy guard: hashed /assets/* cache hard (immutable);
    # everything else (index.html via the SPA fallback) must not cache — a stale
    # index.html after a redeploy references purged bundles → blank page.
    assert "Cache-Control" in caddyfile
    assert "immutable" in caddyfile  # hashed assets
    assert "no-cache" in caddyfile  # index.html / SPA fallback

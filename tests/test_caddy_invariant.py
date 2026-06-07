"""The committed Caddy edge template must honor the ADR 0003 §3 isolation
invariant: proxy ONLY the backend (:8001), never the MCP write layer
(:8010/:8012); gate everything behind basic_auth except /healthz.

A text test, not `caddy validate` (Caddy isn't a CI dependency) — its job is to
make "Caddy never proxies the MCP ports / never un-gates the app" a *tested*
property of the shipped template, so a future edit that adds an :8010/:8012
route or drops the gate fails here instead of silently shipping.
"""

import re
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


def test_sessions_browser_not_exposed_on_edge(caddyfile):
    # red-team #1 (2026-06-04): the cross-world `/api/sessions*` training browser
    # is NOT gated by the per-world token and reads every world's transcripts, so
    # it must not be proxied to the backend on the public edge. An explicit
    # `handle /api/sessions*` block returns a response (404) instead of
    # reverse-proxying to :8001 — keeping it tailnet-only.
    block = re.search(r"handle\s+/api/sessions\*\s*\{([^}]*)\}", caddyfile)
    assert block is not None, "missing `handle /api/sessions*` exclusion block"
    body = block.group(1)
    assert "respond" in body
    assert "reverse_proxy" not in body


def test_admin_status_not_exposed_on_edge(caddyfile):
    # Operator status dashboard (added 2026-06-06): `/api/admin/*` JSON +
    # `/_status` HTML must be tailnet/loopback-only — they expose process-
    # internal metrics (active streams, 503/429 counters, MCP health, settings
    # posture) that should never reach an invited tester. Same exclusion shape
    # as /api/sessions*: explicit `handle` blocks returning 404, never
    # reverse-proxying.
    api_block = re.search(r"handle\s+/api/admin\*\s*\{([^}]*)\}", caddyfile)
    assert api_block is not None, "missing `handle /api/admin*` exclusion block"
    assert "respond" in api_block.group(1)
    assert "reverse_proxy" not in api_block.group(1)

    status_block = re.search(r"handle\s+/_status\s*\{([^}]*)\}", caddyfile)
    assert status_block is not None, "missing `handle /_status` exclusion block"
    assert "respond" in status_block.group(1)
    assert "reverse_proxy" not in status_block.group(1)


def test_bare_alpha_prefix_redirects_to_trailing_slash(caddyfile):
    # `handle_path /alpha/*` matches `/alpha/` and `/alpha/...` but NOT bare
    # `/alpha` (no trailing slash) — a tester typing sentinel.russalo.com/alpha
    # into the URL bar would otherwise fall through to the site-level
    # `respond 404`. An explicit `handle /alpha` block returns a 301 redirect
    # to `/alpha/`. (codex P2 on PR #108, 2026-06-07.)
    pattern = re.compile(
        r"handle\s+/alpha\s*\{[^}]*redir\s+/alpha/\s+301[^}]*\}",
        re.DOTALL,
    )
    assert pattern.search(caddyfile) is not None, (
        "missing `handle /alpha { redir /alpha/ 301 }` — bare /alpha "
        "would 404 instead of redirecting to /alpha/"
    )


def test_alpha_path_prefix_wraps_app_handles(directives):
    # Closed alpha lives at sentinel.russalo.com/alpha/ — the SPA, its assets,
    # and the API all sit under that prefix. The Caddy template MUST use
    # `handle_path /alpha/*` (not bare `handle`) so the prefix is stripped at
    # the edge before the inner handles match — that's what keeps the backend
    # at /api/ and the file_server at /assets/ unchanged. A regression to
    # plain `handle` would mean the backend would see /alpha/api/..., 404 on
    # everything, and the SPA would stop loading.
    assert "handle_path /alpha/*" in directives, (
        "missing `handle_path /alpha/*` — the /alpha prefix must be stripped at "
        "the edge so backend/file_server see un-prefixed paths"
    )


def test_alpha_hostname_is_apex_not_dev_subdomain(caddyfile):
    # The closed alpha is published on the apex `sentinel.russalo.com`, NOT
    # the tailnet-dev `sentinel.dev.russalo.com`. Catch an accidental hostname
    # regression that would either leak the alpha onto the tailnet hostname
    # or break the public hostname.
    assert "sentinel.russalo.com" in caddyfile
    # First non-comment line that opens a site block must be the apex, with
    # the explicit http:// scheme (see test_origin_core_does_not_provision_tls
    # for the scheme rationale).
    site_lines = [
        ln.strip()
        for ln in caddyfile.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert site_lines, "Caddyfile has no directive lines"
    assert site_lines[0].startswith("http://sentinel.russalo.com"), (
        f"first site block is not http://sentinel.russalo.com — got: {site_lines[0]!r}"
    )


def test_origin_core_does_not_provision_tls(caddyfile):
    # Gate-fronted topology (decided 2026-06-06): gate is the public edge and
    # terminates TLS; origin-core's Caddy serves cleartext HTTP over tailnet.
    # The `http://` scheme on the site address tells Caddy to NOT auto-provision
    # a cert — without it, origin-core would try to issue Let's Encrypt for
    # sentinel.russalo.com on every reload (and fail, because origin-core isn't
    # the DNS target). A regression to bare `sentinel.russalo.com {` or to
    # `https://` would re-enable that broken cert-issuance attempt.
    assert "http://sentinel.russalo.com" in caddyfile
    # And no implicit (scheme-less) site block, which would also auto-https.
    # Check the first directive-line opens with the explicit scheme.
    site_lines = [
        ln.strip()
        for ln in caddyfile.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert site_lines[0].startswith("http://"), (
        f"first site block must use explicit http:// scheme (TLS terminates "
        f"at gate, not origin-core) — got: {site_lines[0]!r}"
    )
    # No `https://sentinel.russalo.com` anywhere — that would re-enable TLS
    # provisioning at origin-core.
    assert "https://sentinel.russalo.com" not in caddyfile, (
        "https:// scheme on origin-core's Caddy re-enables auto-cert-provisioning "
        "for a hostname origin-core doesn't own (DNS points at gate). Use http://."
    )


def test_hostname_root_returns_404(directives):
    # The hostname root (sentinel.russalo.com/) is reserved for a future
    # landing page — for now sentinel only owns /alpha/*. A bare `respond 404`
    # at the site level (OUTSIDE the handle_path block) is what makes every
    # non-/alpha path 404. Without it, requests to the root would fall through
    # to nothing and Caddy would return its default empty response — either
    # confusing or accidentally exposing.
    # The `respond 404` MUST appear at site-level scope, not nested inside
    # handle_path /alpha/* (where it'd 404 alpha requests).
    # Find the closing brace of the handle_path block and assert `respond 404`
    # follows it within the site block.
    handle_path_match = re.search(
        r"handle_path\s+/alpha/\*\s*\{", directives, flags=re.DOTALL
    )
    assert handle_path_match is not None, (
        "expected handle_path block — test_alpha_path_prefix_wraps_app_handles "
        "covers absence"
    )
    # Walk braces to find the matching closing brace.
    start = handle_path_match.end()
    depth = 1
    i = start
    while i < len(directives) and depth > 0:
        if directives[i] == "{":
            depth += 1
        elif directives[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, "handle_path /alpha/* block is not closed in directives"
    after_alpha_block = directives[i:]
    assert "respond 404" in after_alpha_block, (
        "missing site-level `respond 404` after the handle_path /alpha/* block — "
        "non-/alpha paths must 404, not fall through to Caddy's default"
    )


def test_static_cache_headers_prevent_stale_index(caddyfile):
    # stale-cache-after-redeploy guard: hashed /assets/* cache hard (immutable);
    # everything else (index.html via the SPA fallback) must not cache — a stale
    # index.html after a redeploy references purged bundles → blank page.
    assert "Cache-Control" in caddyfile
    assert "immutable" in caddyfile  # hashed assets
    assert "no-cache" in caddyfile  # index.html / SPA fallback

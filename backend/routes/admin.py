"""Operator status dashboard (closed-alpha observability, ADR 0003 supplement).

Two endpoints, both tailnet/loopback-only by Caddy invariant — Caddy MUST
NOT proxy ``/api/admin*`` or ``/_status`` to the public edge. Same access
pattern as ``/api/sessions*`` (the ``/data`` browser).

- ``GET /api/admin/status`` — JSON snapshot of counter state, current
  capacity utilization, settings posture, MCP health. Polled by the HTML
  dashboard; also curl-friendly for terminal-only ops.

- ``GET /_status`` — Vanilla-HTML dashboard page that polls the JSON
  endpoint every 5 seconds and renders counter cards. No SPA build
  dependency, no React, no external assets — fits in a single response.

What this is NOT:
- Not Prometheus/Grafana.
- Not historical (counters reset on backend restart; uptime is surfaced).
- Not the ``/data`` training-corpus browser.
- Not user-facing.
"""

from __future__ import annotations


import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..config import Settings

router = APIRouter(prefix="", tags=["admin"])

_MCP_HEALTH_TIMEOUT_S = 2.0


def _mcp_health_one(url: str) -> dict:
    """Fetch /health on one MCP server. Never raises — returns a result dict.

    Defensively handles a non-dict JSON body: `r.json()` can return a list,
    string, or null for well-formed-but-unexpected payloads, and calling
    `.get()` on those would raise AttributeError (gemini medium on PR #107).
    The isinstance() guard treats anything non-dict as "ok-but-no-fields",
    same as a missing content-type header.
    """
    try:
        r = httpx.get(url, timeout=_MCP_HEALTH_TIMEOUT_S)
        if r.status_code == 200:
            body: dict = {}
            if r.headers.get("content-type", "").startswith("application/json"):
                parsed = r.json()
                if isinstance(parsed, dict):
                    body = parsed
            return {
                "status": body.get("status", "ok"),
                "worlds_root": bool(body.get("worlds_root", False)),
            }
        return {"status": f"http {r.status_code}", "worlds_root": False}
    except Exception as exc:
        return {"status": f"unreachable: {type(exc).__name__}", "worlds_root": False}


@router.get("/api/admin/status")
def admin_status(request: Request) -> dict:
    """JSON snapshot of operator-relevant state.

    Shape is documented in tests/backend/test_admin.py; an operator/dashboard
    is expected to tolerate field additions, so this route may grow over time.
    """
    settings: Settings = request.app.state.settings
    metrics = request.app.state.admin_metrics
    snap = metrics.snapshot()

    stream_limiter = request.app.state.stream_limiter

    return {
        "uptime_seconds": snap["uptime_seconds"],
        "concurrency": {
            "active": snap["active_streams"],
            "max": stream_limiter.max_streams,  # 0 = unlimited
            "capacity_rejected_total": snap["capacity_rejected_total"],
        },
        "throughput": {
            "streams_served_total": snap["streams_served_total"],
            "rate_limited_total": snap["rate_limited_total"],
        },
        # Use the BACKEND-configured MCP URLs (settings.fs_manager_url /
        # git_sync_url), not hardcoded loopback addresses (codex P2 on PR
        # #107). A deploy with FS_MANAGER_URL=http://fs-manager.tailnet:8010
        # or a Docker-service-name URL would otherwise report unreachable for
        # MCP servers that are actually healthy — the dashboard would lie.
        "mcp": {
            "fs_manager": _mcp_health_one(
                settings.fs_manager_url.rstrip("/") + "/health"
            ),
            "git_sync": _mcp_health_one(settings.git_sync_url.rstrip("/") + "/health"),
        },
        "settings_posture": {
            "world_token_enforced": bool(settings.session_token_secret),
            "max_concurrent_streams": settings.max_concurrent_streams,
            "rl_session_create_per_hour": settings.rl_session_create_per_hour,
            "rl_stream_per_minute": settings.rl_stream_per_minute,
            "llm_daily_ceiling": settings.llm_daily_ceiling,
            "worlds_root_set": bool(settings.worlds_root),
        },
    }


# Vanilla HTML + JS — no framework, no external assets, no SPA build step.
# Polls /api/admin/status every 5s and renders counter cards. Operator-only;
# Caddy excludes this path from the public edge.
_STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sentinel status</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
         background: #0c0d0f; color: #d0c8a0; margin: 0; padding: 2rem;
         line-height: 1.4; }
  h1 { font-weight: 400; letter-spacing: 0.05em; font-size: 1.4rem; margin: 0 0 1.5rem; }
  .grid { display: grid; gap: 1rem;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          max-width: 80rem; }
  .card { background: #15171a; border: 1px solid #2a2d33; border-radius: 6px;
          padding: 1rem 1.25rem; }
  .label { color: #6b6552; font-size: 0.8rem; text-transform: uppercase;
           letter-spacing: 0.08em; margin-bottom: 0.4rem; }
  .value { font-size: 1.7rem; font-weight: 400; color: #d0c8a0; }
  .sub { color: #8a8266; font-size: 0.85rem; margin-top: 0.2rem; }
  .ok { color: #7ab87a; }
  .warn { color: #d4a554; }
  .err { color: #c47878; }
  .footer { margin-top: 2rem; color: #6b6552; font-size: 0.8rem; }
  code { background: #2a2d33; padding: 0.1rem 0.3rem; border-radius: 3px;
         font-size: 0.85rem; }
</style>
</head>
<body>
<h1>Sentinel — operator status</h1>
<div class="grid" id="grid"></div>
<div class="footer" id="footer">connecting…</div>
<script>
const $ = (id) => document.getElementById(id);
function card(label, value, sub, cls) {
  return `<div class="card"><div class="label">${label}</div>` +
         `<div class="value ${cls||''}">${value}</div>` +
         (sub ? `<div class="sub">${sub}</div>` : '') + '</div>';
}
function fmtDur(s) {
  s = Math.floor(s);
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm ' + (s%60) + 's';
  return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
}
async function refresh() {
  let d;
  try { d = await (await fetch('/api/admin/status')).json(); }
  catch (e) { $('footer').textContent = 'unreachable: ' + e; return; }
  // Defensive: malformed response (non-object, missing sections) would crash
  // accessor chains below with TypeError. Fail visibly without crashing the
  // dashboard so the operator sees what went wrong.
  if (!d || typeof d !== 'object' || !d.concurrency || !d.throughput || !d.mcp || !d.settings_posture) {
    $('footer').textContent = 'malformed response: ' + JSON.stringify(d).slice(0, 200);
    return;
  }
  const cap = d.concurrency.max || '∞';
  const capCls = d.concurrency.max && d.concurrency.active >= d.concurrency.max ? 'err'
               : d.concurrency.max && d.concurrency.active >= d.concurrency.max * 0.8 ? 'warn'
               : 'ok';
  const mcpFs = d.mcp.fs_manager.status === 'ok' ? 'ok' : 'err';
  const mcpGit = d.mcp.git_sync.status === 'ok' ? 'ok' : 'err';
  $('grid').innerHTML = [
    card('Active streams', `${d.concurrency.active} / ${cap}`,
         `${d.concurrency.capacity_rejected_total} rejected (503)`, capCls),
    card('Streams served', d.throughput.streams_served_total,
         `${d.throughput.rate_limited_total} rate-limited (429)`),
    card('Uptime', fmtDur(d.uptime_seconds), 'since process start'),
    card('fs-manager', d.mcp.fs_manager.status, 'worlds_root: ' + d.mcp.fs_manager.worlds_root, mcpFs),
    card('git-sync', d.mcp.git_sync.status, 'worlds_root: ' + d.mcp.git_sync.worlds_root, mcpGit),
    card('Token enforcement',
         d.settings_posture.world_token_enforced ? 'ON' : 'OFF',
         null,
         d.settings_posture.world_token_enforced ? 'ok' : 'warn'),
    card('LLM daily ceiling',
         d.settings_posture.llm_daily_ceiling || 'unset',
         d.settings_posture.llm_daily_ceiling ? 'cap on /day' : 'unbounded'),
    card('Concurrency cap',
         d.settings_posture.max_concurrent_streams || 'unset',
         d.settings_posture.max_concurrent_streams ? 'hard 503 at cap' : 'unbounded'),
  ].join('');
  $('footer').textContent = 'last updated ' + new Date().toLocaleTimeString() +
                            ' — polls every 5s';
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


@router.get("/_status", response_class=HTMLResponse)
def status_dashboard() -> HTMLResponse:
    """Vanilla-HTML dashboard polling /api/admin/status every 5s."""
    return HTMLResponse(_STATUS_HTML)

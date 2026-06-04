#!/usr/bin/env python3
"""Pre-cutover readiness check (ADR 0002 / 0003, Path A-A4). READ-ONLY.

Run on origin-core BEFORE flipping the per-world + public cutover:

    just cutover-check

Prints a PASS/WARN/FAIL/INFO table and exits non-zero on any FAIL. It verifies
the isolation + access env is consistent and that the MCP servers already agree
on per-world mode — surfacing a split-brain config *before* you restart the
backend (which would otherwise refuse to start) and before anything is exposed.

Severity model:
  FAIL  — would corrupt state or break serving (worlds-root unset/unwritable,
          MCP servers disagree, public bind enabled). Blocks the cutover.
  WARN  — hardening recommended but not broken (no per-world token; all rate
          limits disabled). Surfaced loudly, doesn't block.
  INFO  — reminders for things this script can't verify (Caddy gate, tracer-soak).

This script mutates NOTHING — it only reads env + GETs the MCP /health endpoints.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / "infrastructure" / ".env"

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
_TRUTHY = {"1", "true", "yes", "on"}


def _load_env() -> dict:
    """infrastructure/.env overlaid with os.environ (the real environment wins)."""
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    env.update(os.environ)
    return env


def _http_get_json(url: str, *, timeout: float = 5.0) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"non-HTTP url: {url!r}")
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (loopback)
        return json.loads(resp.read().decode("utf-8"))


def check(env: dict, *, fetch=_http_get_json) -> list[dict]:
    """Return a list of {check, status, detail}. ``fetch`` is injectable for tests."""
    results: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        results.append({"check": name, "status": status, "detail": detail})

    # 1. Per-world isolation root — the cutover itself.
    worlds_root = (env.get("SENTINEL_WORLDS_ROOT") or "").strip()
    if not worlds_root:
        add(
            "SENTINEL_WORLDS_ROOT",
            FAIL,
            "unset — per-world isolation is off; the cutover requires it set.",
        )
    else:
        path = Path(worlds_root)
        if not path.is_dir():
            add(
                "SENTINEL_WORLDS_ROOT",
                FAIL,
                f"{worlds_root} is not an existing directory.",
            )
        elif not os.access(path, os.W_OK):
            add("SENTINEL_WORLDS_ROOT", FAIL, f"{worlds_root} is not writable.")
        else:
            add("SENTINEL_WORLDS_ROOT", PASS, f"set + writable: {worlds_root}")

    # 2. MCP servers must agree on per-world mode (only meaningful once set).
    if worlds_root:
        fs_url = (env.get("FS_MANAGER_URL") or "http://127.0.0.1:8010").rstrip("/")
        gs_url = (env.get("GIT_SYNC_URL") or "http://127.0.0.1:8012").rstrip("/")
        for name, base in (("fs-manager", fs_url), ("git-sync", gs_url)):
            try:
                body = fetch(f"{base}/health")
            except Exception as exc:
                add(f"{name} /health", FAIL, f"unreachable at {base}/health: {exc}")
                continue
            if isinstance(body, dict) and body.get("worlds_root") is True:
                add(
                    f"{name} /health",
                    PASS,
                    "worlds_root=true (agrees with the backend)",
                )
            else:
                add(
                    f"{name} /health",
                    FAIL,
                    "worlds_root not true — disagrees with per-world mode; set "
                    "SENTINEL_WORLDS_ROOT for this service too.",
                )

    # 3. The MCP write layer must not be exposed.
    if (env.get("SENTINEL_ALLOW_PUBLIC_BIND") or "").strip().lower() in _TRUTHY:
        add(
            "SENTINEL_ALLOW_PUBLIC_BIND",
            FAIL,
            "set — MCP servers may bind all interfaces; unset it (ADR 0003 §3).",
        )
    else:
        add("SENTINEL_ALLOW_PUBLIC_BIND", PASS, "unset — MCP servers stay loopback")

    # 4. Per-world token enforcement (defense-in-depth; the Caddy gate is primary).
    if (env.get("SENTINEL_SESSION_TOKEN_SECRET") or "").strip():
        add(
            "SENTINEL_SESSION_TOKEN_SECRET",
            PASS,
            "set — per-world token enforcement armed",
        )
    else:
        add(
            "SENTINEL_SESSION_TOKEN_SECRET",
            WARN,
            "unset — per-world tokens off; the Caddy invite gate is then the only "
            "access control.",
        )

    # 5. Rate limits / LLM ceiling — cost backstop (lenient is allowed → WARN).
    def _positive(value: str) -> bool:
        try:
            return int(value) > 0
        except ValueError:
            return False

    rl_keys = (
        "SENTINEL_RL_SESSION_CREATE_PER_HOUR",
        "SENTINEL_RL_STREAM_PER_MINUTE",
        "SENTINEL_LLM_DAILY_CEILING",
    )
    if any(_positive((env.get(k) or "0").strip()) for k in rl_keys):
        add("rate limits", PASS, "at least one SENTINEL_RL_* / LLM ceiling is set")
    else:
        add(
            "rate limits",
            WARN,
            "all disabled (0) — a public beta has no cost backstop; consider setting "
            "SENTINEL_LLM_DAILY_CEILING.",
        )

    # 6. Reminders this script can't verify from here.
    add(
        "Caddy invite gate",
        INFO,
        "ensure $SENTINEL_INVITE_HASH is set for Caddy and the basic_auth gate is "
        "applied (not checkable from here).",
    )
    add(
        "tracer-soak gate",
        INFO,
        "ensure tests/test_world_isolation_tracer_soak.py is green in CI before flipping.",
    )
    return results


def main() -> int:
    results = check(_load_env())
    width = max(len(r["check"]) for r in results)
    icon = {PASS: "✓", WARN: "!", FAIL: "✗", INFO: "i"}
    for r in results:
        print(f"  [{icon[r['status']]}] {r['check'].ljust(width)}  {r['detail']}")
    print()

    fails = [r for r in results if r["status"] == FAIL]
    warns = [r for r in results if r["status"] == WARN]
    if fails:
        print(f"NOT READY — {len(fails)} blocking check(s) failed. Fix and re-run.")
        return 1
    suffix = f" (with {len(warns)} warning(s))" if warns else ""
    print(f"READY for cutover{suffix}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

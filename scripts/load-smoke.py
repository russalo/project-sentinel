#!/usr/bin/env python3
"""Load smoke for the Sentinel turn loop — N concurrent worlds × M turns.

Drives N parallel `/api/stream` SSE sessions against a live backend and
measures per-turn latencies + error rate. The intent is a sanity check before
opening the closed alpha to invited testers — *not* a benchmark suite. It
catches the obvious "would 10 users at once already break this?" cliff that
the existing tracer-soak (correctness only, stubbed DM) cannot.

What it measures
----------------
- World provisioning: count + median wall-clock for ``POST /api/session/new``.
- Per-turn streaming: count, error count, first-SSE-event latency, total-turn
  latency (first byte to ``[DONE]``), each reported as p50 / p95 / p99.
- Verdict: ✅ healthy / ⚠ degraded / ❌ broken, with the trip reason inline.

Safety
------
Each turn writes JSON + commits a git snapshot. With ``SENTINEL_WORLDS_ROOT``
unset, those commits land on the *checked-out branch* (normally ``master``) —
i.e. polluting the code repo. This script refuses to run in that state unless
you pass ``--allow-shared-tree`` to acknowledge it. The right move for a real
load smoke is to export ``SENTINEL_WORLDS_ROOT`` first so commits go to a
worlds tree outside the repo (see ``docs/WORKSPACE.md`` § "Local dev: keep
gameplay out of the code repo").

Cleanup caveat: ``DELETE /api/world/<id>`` (run by default at end) ``rmtree``s
the world's tree under per-world mode, but in shared mode it can only
``git rm`` the session JSON — entity/location/faction files created during
the test remain in ``data/state/core/`` because they aren't world-scoped on
disk in shared mode. Per-world mode (the recommended setup) avoids this.

Measurement notes
-----------------
- The *first* turn after the backend has been idle hits cold-start LLM
  latency (especially on Groq) and is materially slower than warm calls.
  ``--warmup N`` (default 1) runs N throwaway turns per world before
  measurement so the published numbers reflect warm-path behavior.
- Percentiles below ~5 samples are noise (p95 of N=2 is just max). The
  script auto-degrades the report to ``min/median/max`` when N < 5 and
  to ``p50/p95/p99`` only when N >= 5.
- **A** ``❌ broken — N/M turns errored`` **verdict often means the LLM
  provider is rate-limiting, not that sentinel itself is failing.** Check
  the error text for ``429`` / ``rate limit``; the load-smoke is the
  cleanest way to detect when the provider has too little headroom for
  the planned concurrency.

Cost
----
Every turn is a real LLM call. With the defaults (3 worlds × 3 turns = 9
calls) you'll see Groq dev-tier cost on the order of cents. Scale up only when
you know what you're paying for.

Usage
-----
::

    # Local stack on origin-core (recommended: export worlds root first)
    export SENTINEL_WORLDS_ROOT=~/sentinel-worlds
    just fs-manager &  just git-sync &  just dev-backend
    python scripts/load-smoke.py --concurrent 5 --turns 3

    # Against a remote prod-like instance
    python scripts/load-smoke.py --base-url https://sentinel.example.com \\
        --concurrent 10 --turns 5

    # Skip the WORLDS_ROOT safety check (pollutes master with per-turn commits)
    python scripts/load-smoke.py --allow-shared-tree

Exit codes
----------
0 = healthy · 1 = degraded · 2 = broken · 3 = setup error (refused to run).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

# Rotating player actions, chosen so the DM doesn't degenerate to identical
# outputs across turns (which would defeat the point of a streaming load test).
_ACTIONS: list[str] = [
    "I look around carefully.",
    "I draw my weapon and step forward.",
    "I greet the nearest person.",
    "I check my pockets for anything useful.",
    "I move toward the nearest exit.",
    "I listen for sounds in the distance.",
    "I crouch and inspect the ground.",
]

# Verdict thresholds — picked to flag obvious breakage, not enforce SLOs. A
# real SLO comes after we have baseline data; these are placeholders. The
# first-token threshold assumes warm-path behavior (--warmup >= 1); cold-start
# on Groq can hit ~20s on the first call, which would falsely flag as
# degraded without warmup.
_FIRST_TOKEN_P95_DEGRADED_S = 8.0   # > this = degraded (warm path)
_TOTAL_TURN_P95_DEGRADED_S = 15.0
_ERROR_RATE_BROKEN = 0.50           # >= 50% errors = broken
_ERROR_RATE_DEGRADED = 0.10
# Below this sample count, percentiles are noise — report min/median/max instead.
_PERCENTILE_MIN_SAMPLES = 5


@dataclass
class TurnResult:
    """One streaming turn — timings in seconds, error message if any."""
    first_token_s: float | None = None
    total_s: float | None = None
    error: str | None = None
    sse_events: int = 0


@dataclass
class WorldResult:
    """One world's lifecycle — provisioning + N turns."""
    world_index: int
    world_id: str | None = None
    session_id: str | None = None
    session_token: str | None = None
    provision_s: float | None = None
    provision_error: str | None = None
    turns: list[TurnResult] = field(default_factory=list)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    # nearest-rank, conservative for small N
    k = max(0, min(len(s) - 1, int(round(pct / 100 * (len(s) - 1)))))
    return s[k]


async def _provision_world(
    client: httpx.AsyncClient, idx: int, prefix: str
) -> WorldResult:
    """POST /api/session/new — create a world, time it, capture token."""
    result = WorldResult(world_index=idx)
    payload = {
        "worldName": f"{prefix} {idx}",
        "playerCharacterName": f"Tester_{idx}",
        "playerCharacterClass": "Adventurer",
    }
    started = time.monotonic()
    try:
        resp = await client.post("/api/session/new", json=payload, timeout=60.0)
        result.provision_s = time.monotonic() - started
        if resp.status_code >= 400:
            result.provision_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return result
        body = resp.json()
        result.session_id = body.get("sessionId")
        result.world_id = body.get("worldId")
        result.session_token = body.get("sessionToken")  # None when access layer off
    except Exception as exc:
        result.provision_s = time.monotonic() - started
        result.provision_error = f"{type(exc).__name__}: {exc}"
    return result


async def _drive_one_turn(
    client: httpx.AsyncClient,
    world: WorldResult,
    action: str,
    timeout_s: float,
) -> TurnResult:
    """POST /api/stream and consume the SSE stream — record timings."""
    result = TurnResult()
    headers = {}
    if world.session_token:
        headers["X-Sentinel-World-Token"] = world.session_token
    payload = {"action": action, "sessionId": world.session_id}
    started = time.monotonic()
    first_seen: float | None = None
    try:
        async with client.stream(
            "POST",
            "/api/stream",
            json=payload,
            headers=headers,
            timeout=timeout_s,
        ) as resp:
            if resp.status_code >= 400:
                # Drain the body so the error message is informative.
                body = await resp.aread()
                result.error = f"HTTP {resp.status_code}: {body.decode('utf-8', 'replace')[:200]}"
                result.total_s = time.monotonic() - started
                return result
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if first_seen is None:
                    first_seen = time.monotonic()
                    result.first_token_s = first_seen - started
                if line.startswith("data:"):
                    result.sse_events += 1
                    # Look for explicit `error` events so an LLM failure that
                    # the server flushes inside a 200-OK stream still surfaces.
                    payload_str = line[5:].strip()
                    if payload_str and payload_str != "[DONE]":
                        try:
                            evt = json.loads(payload_str)
                            if evt.get("type") == "error":
                                result.error = (
                                    f"stream error event: {evt.get('content', '')[:200]}"
                                )
                        except json.JSONDecodeError:
                            pass
            result.total_s = time.monotonic() - started
    except Exception as exc:
        result.total_s = time.monotonic() - started
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def _drive_one_world(
    client: httpx.AsyncClient,
    idx: int,
    prefix: str,
    turns: int,
    timeout_s: float,
    warmup: int,
) -> WorldResult:
    """Provision, run ``warmup`` throwaway turns, then ``turns`` measured turns."""
    world = await _provision_world(client, idx, prefix)
    if world.provision_error:
        return world
    # Warmup turns aren't appended to world.turns, so they don't poison the
    # measurement. They DO still incur LLM cost — the budget note in the
    # docstring accounts for them.
    for w_idx in range(warmup):
        action = _ACTIONS[w_idx % len(_ACTIONS)]
        await _drive_one_turn(client, world, action, timeout_s)
    for turn_idx in range(turns):
        # Rotate past the warmup actions so the measured turns don't repeat
        # the warmup verbatim (different prompts → more representative variance).
        action = _ACTIONS[(warmup + turn_idx) % len(_ACTIONS)]
        turn_result = await _drive_one_turn(client, world, action, timeout_s)
        world.turns.append(turn_result)
        # If turn errored, keep going — we want the full error picture, not
        # a fail-fast that hides whether subsequent turns also break.
    return world


async def _teardown_world(client: httpx.AsyncClient, world: WorldResult) -> None:
    """Best-effort DELETE /api/world/<id>. Swallows errors."""
    if not world.world_id:
        return
    headers = {}
    if world.session_token:
        headers["X-Sentinel-World-Token"] = world.session_token
    try:
        await client.delete(
            f"/api/world/{world.world_id}", headers=headers, timeout=30.0
        )
    except Exception:
        pass


def _format_table(label: str, values: list[float | None]) -> str:
    """One-line table row: label, count, percentiles (or min/median/max on small N).

    Percentiles below ~5 samples are noise (p95 of N=2 is just max), so we
    report min/median/max instead — labeled clearly so a reader doesn't
    confuse the two reports across runs of different sizes.
    """
    real = [v for v in values if v is not None]
    if not real:
        return f"  {label:<22} (no data)"
    if len(real) < _PERCENTILE_MIN_SAMPLES:
        s = sorted(real)
        return (
            f"  {label:<22} n={len(real):<3}  "
            f"min={s[0]:.2f}s  median={s[len(s) // 2]:.2f}s  max={s[-1]:.2f}s  "
            f"(low-sample; bump --concurrent for percentiles)"
        )
    p50 = _percentile(real, 50)
    p95 = _percentile(real, 95)
    p99 = _percentile(real, 99)
    return (
        f"  {label:<22} n={len(real):<3}  "
        f"p50={p50:.2f}s  p95={p95:.2f}s  p99={p99:.2f}s"
    )


def _verdict(
    *,
    provision_failures: int,
    provisions_total: int,
    turn_failures: int,
    turns_total: int,
    first_token_p95: float | None,
    total_turn_p95: float | None,
) -> tuple[int, str]:
    """Return (exit_code, message). 0 healthy / 1 degraded / 2 broken."""
    reasons: list[str] = []

    if provisions_total > 0 and provision_failures == provisions_total:
        return 2, "❌ broken — every world failed to provision"
    if turns_total > 0:
        err_rate = turn_failures / turns_total
        if err_rate >= _ERROR_RATE_BROKEN:
            return 2, f"❌ broken — {turn_failures}/{turns_total} turns errored ({err_rate:.0%})"
        if err_rate >= _ERROR_RATE_DEGRADED:
            reasons.append(f"{turn_failures}/{turns_total} turns errored ({err_rate:.0%})")

    if provision_failures > 0:
        reasons.append(f"{provision_failures}/{provisions_total} worlds failed to provision")
    if first_token_p95 is not None and first_token_p95 > _FIRST_TOKEN_P95_DEGRADED_S:
        reasons.append(f"first-token p95 {first_token_p95:.1f}s > {_FIRST_TOKEN_P95_DEGRADED_S:.1f}s")
    if total_turn_p95 is not None and total_turn_p95 > _TOTAL_TURN_P95_DEGRADED_S:
        reasons.append(f"total-turn p95 {total_turn_p95:.1f}s > {_TOTAL_TURN_P95_DEGRADED_S:.1f}s")

    if not reasons:
        return 0, "✅ healthy"
    return 1, "⚠ degraded — " + "; ".join(reasons)


def _safety_gate(args: argparse.Namespace) -> int | None:
    """Refuse to run if WORLDS_ROOT unset and --allow-shared-tree not passed.

    Returns an exit code on refusal, or None to proceed. We refuse because
    each turn produces a git commit; in shared-tree mode those commits land
    on the checked-out branch (per docs/WORKSPACE.md). Polluting master
    silently from a load test is exactly the failure mode we just fixed
    docs for.
    """
    if os.environ.get("SENTINEL_WORLDS_ROOT") or args.allow_shared_tree:
        return None
    print(
        "ERROR: SENTINEL_WORLDS_ROOT is unset, so per-turn git-sync commits "
        "would land on the checked-out branch (typically master) and pollute "
        "the code repo. Either:\n"
        "  (a) export SENTINEL_WORLDS_ROOT=~/sentinel-worlds and restart the "
        "stack (see docs/WORKSPACE.md § \"Local dev: keep gameplay out of the "
        "code repo\"), OR\n"
        "  (b) pass --allow-shared-tree to acknowledge the pollution and "
        "proceed anyway.",
        file=sys.stderr,
    )
    return 3


async def _run(args: argparse.Namespace) -> int:
    started_overall = time.monotonic()
    async with httpx.AsyncClient(base_url=args.base_url) as client:
        # Per-world coroutines run truly concurrently. Each one is sequential
        # within itself (provision then M turns) — that matches a real
        # tester's flow and isolates which world(s) degrade.
        world_results: list[WorldResult] = await asyncio.gather(
            *(
                _drive_one_world(
                    client,
                    idx,
                    args.world_prefix,
                    args.turns,
                    args.timeout,
                    args.warmup,
                )
                for idx in range(args.concurrent)
            )
        )

        if not args.no_cleanup:
            await asyncio.gather(
                *(_teardown_world(client, w) for w in world_results)
            )

    wall_clock = time.monotonic() - started_overall

    # ── Aggregate ───────────────────────────────────────────────────────
    provision_times = [w.provision_s for w in world_results if w.provision_error is None]
    provision_failures = sum(1 for w in world_results if w.provision_error)

    all_turns: list[TurnResult] = [t for w in world_results for t in w.turns]
    turn_failures = sum(1 for t in all_turns if t.error)
    first_token_times = [t.first_token_s for t in all_turns if t.first_token_s is not None and not t.error]
    total_turn_times = [t.total_s for t in all_turns if t.total_s is not None and not t.error]

    # ── Print report ────────────────────────────────────────────────────
    print()
    print("═══ Sentinel load smoke ═══")
    print(f"  base_url        {args.base_url}")
    print(f"  concurrent      {args.concurrent} worlds")
    print(f"  warmup/world    {args.warmup} (excluded from stats)")
    print(f"  turns/world     {args.turns} (measured)")
    print(f"  cleanup         {'no' if args.no_cleanup else 'yes'}")
    print(f"  wall-clock      {wall_clock:.1f}s")
    print()
    print("World provisioning:")
    print(_format_table("provision", provision_times))
    if provision_failures:
        print(f"  failures        {provision_failures}/{args.concurrent}:")
        for w in world_results:
            if w.provision_error:
                print(f"    world #{w.world_index}: {w.provision_error}")
    print()
    print("Per-turn streaming:")
    print(_format_table("first-token", first_token_times))
    print(_format_table("total-turn", total_turn_times))
    print(f"  succeeded       {len(all_turns) - turn_failures}/{len(all_turns)}")
    if turn_failures:
        print(f"  errored         {turn_failures}/{len(all_turns)}:")
        seen: set[str] = set()
        for w in world_results:
            for t_idx, t in enumerate(w.turns):
                if t.error and t.error not in seen:
                    print(f"    world #{w.world_index} turn {t_idx}: {t.error}")
                    seen.add(t.error)
    print()

    exit_code, verdict = _verdict(
        provision_failures=provision_failures,
        provisions_total=args.concurrent,
        turn_failures=turn_failures,
        turns_total=len(all_turns),
        first_token_p95=_percentile(first_token_times, 95),
        total_turn_p95=_percentile(total_turn_times, 95),
    )
    print(f"Verdict: {verdict}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Concurrent-streams load smoke for the Sentinel turn loop.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See docstring at top of file for usage examples and safety notes.",
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8001",
        help="Backend base URL (default: %(default)s).",
    )
    p.add_argument(
        "--concurrent",
        type=int,
        default=3,
        help="Number of worlds to run in parallel (default: %(default)d). "
        "Modest default to keep cost predictable; bump for real load runs.",
    )
    p.add_argument(
        "--turns",
        type=int,
        default=3,
        help="Measured turns per world (default: %(default)d). Each turn is "
        "one LLM call.",
    )
    p.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Throwaway turns per world before measurement (default: %(default)d). "
        "Drops cold-start LLM latency from the measured numbers; set 0 to "
        "disable. Each warmup turn is also a real LLM call.",
    )
    p.add_argument(
        "--world-prefix",
        default="LoadSmoke",
        help="Prefix for created world names (default: %(default)s).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-turn timeout in seconds (default: %(default).0f).",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip the DELETE /api/world/<id> teardown step. Useful for "
        "inspecting created worlds after the run.",
    )
    p.add_argument(
        "--allow-shared-tree",
        action="store_true",
        help="Run even when SENTINEL_WORLDS_ROOT is unset. Without this flag, "
        "the script refuses because per-turn git-sync commits would pollute "
        "the checked-out branch (see docs/WORKSPACE.md).",
    )
    args = p.parse_args(argv)

    if args.concurrent < 1 or args.turns < 1:
        print("ERROR: --concurrent and --turns must be >= 1", file=sys.stderr)
        return 3
    if args.warmup < 0:
        print("ERROR: --warmup must be >= 0", file=sys.stderr)
        return 3

    refused = _safety_gate(args)
    if refused is not None:
        return refused

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

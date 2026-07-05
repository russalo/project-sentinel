#!/usr/bin/env python3
"""RFC-0016 — the staging deploy-smoke driver.

Drives a **mock-DM** backend through the committed death-sequence fixture and
asserts the PC ends up dead — the deterministic, zero-LLM deploy gate. It plays
the client half of the two-round-trip loop: create a session, POST each turn, and
whenever the DM emits a ``check_request`` send the matching roll on the next turn
(a FAILING roll for death saves, so the 3-strike clock actually reaches ``dead``).

Death is engine-authoritative, so reaching ``dead`` proves the whole chain wired
up for real: mock DM -> fact_extractor -> fs-manager dispatch (HP/stats persisted)
-> death_stakes resolve. Run against an ephemeral mock trio via `just stage-smoke`.

Usage: stage_smoke.py --base http://127.0.0.1:8201 --worlds-root /tmp/smoke-worlds
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import mock_dm  # noqa: E402

_PC_NAME = "Kaelen"  # must match the fixture's PC (death_stakes finds it by name)


def _post(url: str, body: dict) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def _sse_events(text: str) -> list:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :].strip()
            if payload and payload != "[DONE]":
                try:
                    out.append(json.loads(payload))
                except json.JSONDecodeError:
                    pass
    return out


def _roll_for(check: dict) -> dict:
    """Build the RollResult the client would send for this check_request.

    death_save -> a low roll that FAILS (margin = rolled + will*5 - 60 < 0 for
    will 4 when rolled < 40); other checks -> a comfortable success. effectDie is
    omitted (optional) so we don't have to satisfy its die-spec pattern.
    """
    kind = check.get("kind", "skill")
    stat = check.get("stat", "body")
    target = int(check.get("target", 60))
    rolled = 5 if kind == "death_save" else 85
    return {
        "kind": kind,
        "stat": stat,
        "rolled": rolled,
        "bonus": 0,
        "total": rolled,
        "target": target,
        "margin": rolled - target,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="staging backend base URL")
    ap.add_argument(
        "--worlds-root",
        required=True,
        help="staging world store (to read the PC entity)",
    )
    args = ap.parse_args()

    turns = mock_dm.load_turns(SimpleNamespace(dm_mock_fixture=None))
    stream_turns = sorted(n for n in turns if n >= 1)

    # 1. Create the session (mock intro = fixture turn 0; PC name MUST match).
    created = json.loads(
        _post(
            f"{args.base}/api/session/new",
            {
                "worldName": "Stage Smoke",
                "playerCharacterName": _PC_NAME,
                "playerCharacterClass": "Warrior",
                "genre": "fantasy",
            },
        )
    )
    if not isinstance(created, dict):
        print(
            f"FAIL: session/new returned {type(created).__name__}, expected an object",
            file=sys.stderr,
        )
        return 1
    session_id = created.get("sessionId") or created["session_id"]
    world_id = created.get("worldId") or created["world_id"]
    print(f"session {session_id[:8]}  world {world_id[:8]}")

    # 2. Drive the turns, feeding a roll whenever the prior turn requested a check.
    pending: dict | None = None
    for n in stream_turns:
        body = {
            "action": turns[n].get("player_action", f"turn {n}"),
            "sessionId": session_id,
        }
        if pending is not None:
            body["roll"] = _roll_for(pending)
        events = _sse_events(_post(f"{args.base}/api/stream", body))
        wu = [
            e for e in events if isinstance(e, dict) and e.get("type") == "world_update"
        ]
        pending = None
        if wu:
            data = wu[-1].get("data")
            if isinstance(data, dict):
                pending = data.get("check_request")
        tag = f" check={pending.get('kind', 'skill')}" if pending else ""
        print(f"  turn {n:>2}{tag}")

    # 3. Assert the PC persisted as dead in the STAGING store.
    slug = re.sub(r"[^a-z0-9_-]", "", _PC_NAME.lower().replace(" ", "_"))
    entity = (
        Path(args.worlds_root) / world_id / "data/state/core/entities" / f"{slug}.json"
    )
    if not entity.exists():
        print(f"FAIL: PC entity {entity} was never written", file=sys.stderr)
        return 1
    pc = json.loads(entity.read_text(encoding="utf-8"))
    if not isinstance(pc, dict):
        print(
            f"FAIL: PC entity is {type(pc).__name__}, expected an object",
            file=sys.stderr,
        )
        return 1
    status = pc.get("status") or pc.get("module_data", {}).get(
        "character_sheet", {}
    ).get("status")
    print(f"PC status: {status}")
    if status != "dead":
        print(f"FAIL: expected the PC to be dead, got {status!r}", file=sys.stderr)
        return 1
    print("OK: stage-smoke reached a verified death.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

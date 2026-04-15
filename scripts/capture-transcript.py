#!/usr/bin/env python3
"""Copy the current Claude Code session transcript into ``chatlogs/``.

Invoked by the ``PreCompact`` hook defined in ``.claude/settings.json``
via ``just capture-transcript``. Works on macOS, Linux, and Windows —
uses only the Python standard library, no shell syntax, no
Unix-specific tools.

Contract (from Claude Code hook docs — verified 2026-04-14 via
https://code.claude.com/docs/en/hooks-guide.md):

- **Stdin.** Claude Code writes a JSON payload to the hook command's
  stdin at invocation time. The payload includes:
    {
      "session_id": "<uuid>",
      "transcript_path": "/absolute/path/to/session.jsonl",
      "cwd": "/working/directory/at/event/time",
      "hook_event_name": "PreCompact"
    }
  The original Claude Code advice said this was passed via environment
  variables (``$CLAUDE_TRANSCRIPT_PATH`` etc.) — that's wrong. ChatGPT
  Codex flagged it on PR #16 review and the docs confirm stdin JSON
  is the actual contract. An earlier version of this hook gated on
  the env vars and silently no-op'd every time because they were
  never set.

- **Environment variables.** Claude Code also injects
  ``$CLAUDE_PROJECT_DIR`` — the absolute path of the project root,
  reliably set for every hook invocation. Use this to anchor output
  paths instead of relying on ``cwd``, which can be anywhere inside
  the repo (or outside, if the user changed directories mid-session).

Defensive posture
-----------------
This script must NEVER raise or exit non-zero. The ``PreCompact``
hook runs synchronously before compaction; if it errors, Claude
Code's behavior around that is undefined and in the worst case
could block compaction or crash the session. Every operation here
is wrapped in a try/except with graceful fallback, and the exit
code is always 0. Errors land on stderr as a single line starting
with ``capture-transcript:`` so they're greppable in Claude Code's
hook log without polluting stdout.

Manual invocation
-----------------
The script is also runnable manually to snapshot the current
conversation mid-session without waiting for compaction:

    just capture-transcript

When invoked manually without a stdin JSON payload (empty stdin
or non-JSON content), the script falls back to reading the
``CLAUDE_TRANSCRIPT_PATH`` / ``CLAUDE_SESSION_ID`` environment
variables if set, and otherwise no-ops with an explanatory stderr
message. This keeps ``just capture-transcript`` safe to run ad-hoc
during development — it won't erase anything, and if you have the
env vars set (e.g. from a custom shell helper), it still works.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import threading
from pathlib import Path

# Maximum time to wait for stdin to close when reading the hook payload.
# Claude Code writes a small JSON blob and closes the stream immediately, so
# anything beyond a couple seconds means the caller is misbehaving and we'd
# rather no-op than block the PreCompact hook indefinitely.
_STDIN_READ_TIMEOUT_SECONDS = 5.0

# Session id is used unescaped in a filename. Cap length and restrict to a
# safe charset so a malformed id can't traverse directories or blow past
# filesystem name limits.
_SESSION_ID_MAX_LEN = 64

# Upper bound on the stdin payload. Claude Code's hook JSON is a handful of
# fields (session_id, transcript_path, cwd, hook_event_name) totaling well
# under a kilobyte; 1 MiB is orders of magnitude beyond plausible and keeps
# a misbehaving or hostile caller from exhausting memory.
_STDIN_MAX_BYTES = 1024 * 1024


def _log(msg: str) -> None:
    print(f"capture-transcript: {msg}", file=sys.stderr)


def _read_hook_input() -> dict:
    """Read and parse the JSON payload Claude Code writes to stdin.

    Returns an empty dict if stdin is empty, not JSON, or not a
    JSON object. Never raises.
    """
    try:
        if sys.stdin.isatty():
            # Running interactively with no piped input — skip stdin.
            return {}
    except (OSError, ValueError):
        return {}

    # Read stdin on a background thread so a misbehaving caller that never
    # closes the stream can't block the PreCompact hook. signal.alarm is
    # Unix-only and select() on stdin isn't reliable cross-OS, so a thread
    # with a join timeout is the portable option.
    result: dict = {"raw": None}

    def _reader() -> None:
        try:
            result["raw"] = sys.stdin.read(_STDIN_MAX_BYTES)
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout=_STDIN_READ_TIMEOUT_SECONDS)
    if thread.is_alive():
        _log(f"stdin read exceeded {_STDIN_READ_TIMEOUT_SECONDS}s; ignoring")
        return {}

    raw = result["raw"]
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _log(f"stdin was not valid JSON; ignoring ({len(raw)} bytes)")
        return {}
    if not isinstance(parsed, dict):
        _log(f"stdin was JSON but not an object; ignoring ({type(parsed).__name__})")
        return {}
    return parsed


def _resolve_transcript_path(hook_input: dict) -> Path | None:
    """Return the transcript file path, or None if unavailable.

    Preference order:
    1. ``transcript_path`` field from the hook-input JSON (the real contract)
    2. ``CLAUDE_TRANSCRIPT_PATH`` env var (fallback for manual invocation)

    Logs exactly one reason to stderr when returning None so the
    stderr output is informative without double-reporting.
    """
    candidate = hook_input.get("transcript_path") or os.environ.get(
        "CLAUDE_TRANSCRIPT_PATH"
    )
    if not candidate:
        _log("no transcript path available from stdin or env; skipping")
        return None
    path = Path(candidate)
    if not path.is_file():
        _log(f"transcript path {path} does not exist; skipping")
        return None
    return path


def _resolve_session_id(hook_input: dict) -> str:
    """Return the session id for the filename suffix.

    Preference order:
    1. ``session_id`` field from the hook-input JSON
    2. ``CLAUDE_SESSION_ID`` env var
    3. Fallback constant ``'session'`` so the filename is still valid

    The result is sanitized to ``[A-Za-z0-9_-]`` and capped at
    ``_SESSION_ID_MAX_LEN`` characters. Session ids land in a filename
    unescaped, so a malformed value (path separators, null bytes,
    excessive length) could otherwise traverse directories or trip
    filesystem name limits. If sanitization empties the string, fall
    back to ``'session'``.
    """
    raw = (
        hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID") or "session"
    )
    cleaned = "".join(c for c in str(raw) if c.isalnum() or c in "-_")[
        :_SESSION_ID_MAX_LEN
    ]
    if not cleaned:
        cleaned = "session"
    if cleaned != raw:
        _log(f"sanitized session_id {raw!r} → {cleaned!r}")
    return cleaned


def _resolve_project_dir() -> Path:
    """Return the project root path for anchoring ``chatlogs/``.

    Preference order:
    1. ``CLAUDE_PROJECT_DIR`` env var (reliable per Claude Code docs)
    2. Path computed relative to this script's location:
       ``scripts/capture-transcript.py`` → parent → parent → repo root

    The second fallback works for manual invocation from anywhere.
    """
    from_env = os.environ.get("CLAUDE_PROJECT_DIR")
    if from_env:
        env_path = Path(from_env)
        if env_path.is_dir():
            return env_path
    return Path(__file__).resolve().parent.parent


def _utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    try:
        hook_input = _read_hook_input()

        transcript_path = _resolve_transcript_path(hook_input)
        if transcript_path is None:
            # Helper already logged the specific reason.
            return 0

        session_id = _resolve_session_id(hook_input)
        project_dir = _resolve_project_dir()
        chatlogs_dir = project_dir / "chatlogs"

        try:
            chatlogs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log(f"could not create {chatlogs_dir}: {exc}")
            return 0

        target = chatlogs_dir / f"{_utc_timestamp()}-{session_id}.jsonl"

        try:
            shutil.copy2(transcript_path, target)
        except OSError as exc:
            _log(f"could not copy {transcript_path} → {target}: {exc}")
            return 0

        _log(f"saved {target}")
    except Exception as exc:  # pragma: no cover - defensive
        _log(f"unexpected error (ignored): {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

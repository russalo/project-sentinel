# engine — Project Sentinel Inference Core

Pure-Python core for the DM → Fact-Extractor → `<world_update>` pipeline.

## The boundary contract

This package exists to keep the Inference Node independent of any specific
web framework, storage layer, or deployment topology. It is invoked today as
an in-process import from the FastAPI backend (`backend/`), and the same design
allows it to later run as a standalone node — wrapped in its own service over
the network — without touching the core logic.

Everything in this package obeys four rules:

1. **No imports from `backend/`, `apps/`, or any web framework.**
   Enforced by `tests/engine/test_boundaries.py`. If you need backend
   models or settings inside `engine/`, the shape is wrong — pass plain
   dataclasses in, return plain dataclasses out, and do the framework
   translation in `backend/` where it belongs.

2. **No `os.environ` reads.** All configuration arrives via `engine.Config`
   passed explicitly from the caller.

3. **No runtime side effects.** `engine/` does not write to disk
   or make HTTP calls to the MCP servers. It produces
   strings and structured payloads; the caller is responsible for
   dispatching them. Reading bundled schema/prompt resources (e.g.
   `schemas/apply_world_update.schema.json` loaded lazily by
   `engine/schema.py`) is explicitly allowed — those are
   framework-agnostic initialization reads, not external state changes.

4. **Streaming is a generator protocol, not a framework concern.**
   `stream_turn(...)` yields tokens. The FastAPI backend wraps the
   generator in an SSE stream; any other transport (a test loop, a CLI,
   a future standalone adapter) could wrap the same generator differently.
   The engine doesn't know or care.

## Current status

**Wired into the production backend.** The engine package is the
Inference Node referenced in ADR 0001 Phase 1. Every per-turn
HTTP request served by the FastAPI backend (`backend/main.py`)
goes through this package: the backend calls `dm.stream_turn()`,
accumulates tokens, hands the raw response to
`fact_extractor.extract()`, and dispatches the resulting payload
via `engine.apply_world_update()`. Session creation
(`POST /api/session/new`) uses the same pipeline via
`dm.generate_intro()`.

Implemented:

- `engine.Config`, `engine.WorldContext`, `engine.DMTurnInput`,
  `engine.DMTurnResult` — the public type contracts
- `engine.validate()` — lazy-loaded Draft 2020-12 validator with
  `format_checker` (enforces `session_id` UUID, etc.)
- `engine.llm.build_client()` — thin OpenAI client wrapper
- `engine.dispatch.apply_world_update()` — synchronous HTTP client
  for `fs-manager:8010/tools/apply_world_update` with structured
  `DispatchResult` and optional `httpx.Client` injection for tests
- `engine.dispatch.commit_snapshot()` — synchronous HTTP client for
  `git-sync:8012/tools/commit_snapshot`. Same shape as the fs-manager
  dispatcher: structured `DispatchResult`, client injection for tests,
  trailing-slash URL normalization. Called by the backend after every
  successful fs-manager write to produce the per-turn git audit trail
  ADR 0001 Phase 1 promises. "no_changes" server responses (git has
  nothing staged to commit) return `ok=True` — that's a normal
  outcome, not a failure.
- `engine.agents.fact_extractor.extract()` — parses DM `<world_update>`
  hint blocks and emits schema-valid payloads; returns
  `FactExtractResult(payload, narrative, errors)`; self-validates
  output so callers can trust a non-None payload is fs-manager-ready
- `engine.agents.dm.run_turn` / `engine.agents.dm.stream_turn` —
  the real DM agent. `stream_turn` is a plain generator yielding
  token strings so any transport (FastAPI SSE, test loop, CLI,
  future FastAPI adapter) can consume it. Both functions accept
  optional `client=` injection for test mocking, matching the
  dispatcher's pattern.
- `engine.prompts.dm.DM_SYSTEM_PROMPT` — ported verbatim from the
  legacy `backend/api/dm_ai.py` (since retired)

Still stubbed:

- `engine.agents.lorekeeper.*` — the RAG step that queries ChromaDB
  for relevant lore and injects it into the DM's context window. No
  file yet; scaffolded as BACKLOG Phase 2 once the core loop is
  running against a real backend.

Typical caller pattern (what the FastAPI backend does — see
`backend/routes/stream.py`):

```python
import engine
from engine.agents import dm as dm_agent, fact_extractor

config = engine.Config(openai_api_key=..., ...)  # from app settings
turn_input = engine.DMTurnInput(
    session_id=session_uuid,
    player_action=action_text,
    world_context=load_world_context(),  # caller reads data/state/*.json
)

full = []
for token in dm_agent.stream_turn(config, turn_input):
    full.append(token)
    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

raw = "".join(full)
result = fact_extractor.extract(raw, session_uuid, turn_number)
if result.payload is not None:
    dispatch_result = engine.apply_world_update(config, result.payload)
    if not dispatch_result.ok:
        # feed the error back to the DM for retry, per ARCHITECTURE.md
        ...

# After all fs-manager writes succeed for this turn, commit the
# snapshot to git so the turn becomes a real commit in the audit
# trail. Separate dispatch because the failure modes are distinct —
# a schema violation and a git failure need different responses.
commit_result = engine.commit_snapshot(
    config,
    session_id=session_uuid,
    turn_number=turn_number,
    summary=narrative[:200],
)
if not commit_result.ok:
    # Non-fatal: narrative + disk state are durable, only the audit
    # trail missed this turn. Surface as an error event; do not roll back.
    yield f"data: {json.dumps({'type': 'error', 'content': commit_result.error})}\n\n"

yield "data: [DONE]\n\n"
```

Wired in production: `backend/routes/session.py` and
`backend/routes/stream.py` are the primary callers. Django has
been retired. `backend/api/dm_ai.py` no longer exists. Every new
turn the frontend triggers runs through this engine package,
writes to `data/` via fs-manager, and commits to git via git-sync
— producing the per-turn audit trail ADR 0001 describes. The
full pipeline was verified end-to-end against a real qwen3:32b
model on 2026-04-14 and produces real git commits like
`[sentinel] session=3182ff9f turn=3 — <summary>`.

## Install

```bash
pip install -r engine/requirements.txt
```

Or run `just install` from the repo root, which now chains engine deps
alongside the other Python installs.

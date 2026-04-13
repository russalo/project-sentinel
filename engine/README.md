# engine — Project Sentinel Inference Core

Pure-Python core for the DM → Fact-Extractor → `<world_update>` pipeline.

## The boundary contract

This package exists to keep the Inference Node independent of any specific
web framework, storage layer, or deployment topology. It is invoked today as
an in-process import from Django (`backend/`), but the design allows it to
later be wrapped in a FastAPI service and run as a standalone node without
touching the core logic.

Everything in this package obeys four rules:

1. **No imports from Django, `backend/`, `apps/`, or `artifacts/`.**
   Enforced by `tests/engine/test_boundaries.py`. If you need Django
   models or settings inside `engine/`, the shape is wrong — pass plain
   dataclasses in, return plain dataclasses out, and do the Django
   translation in `backend/api/` where it belongs.

2. **No `os.environ` reads.** All configuration arrives via `engine.Config`
   passed explicitly from the caller.

3. **No runtime side effects.** `engine/` does not write to disk,
   mutate databases, or make HTTP calls to the MCP servers. It produces
   strings and structured payloads; the caller is responsible for
   dispatching them. Reading bundled schema/prompt resources (e.g.
   `schemas/apply_world_update.schema.json` loaded lazily by
   `engine/schema.py`) is explicitly allowed — those are
   framework-agnostic initialization reads, not external state changes.

4. **Streaming is a generator protocol, not a framework concern.**
   `stream_turn(...)` yields tokens. Django wraps the generator in
   `StreamingHttpResponse`; a future FastAPI adapter could wrap the same
   generator in SSE. The engine doesn't know or care.

## Current status

**End-to-end in-process, not yet wired to a backend.** Every piece of
the per-turn pipeline is implemented and unit-tested in isolation:
a caller can build a `DMTurnInput`, run it through `stream_turn` for
tokens, accumulate the response, hand it to `fact_extractor.extract`,
and dispatch the resulting payload to `fs-manager` — all without any
production backend touching the engine yet.

Implemented:

- `engine.Config`, `engine.WorldContext`, `engine.DMTurnInput`,
  `engine.DMTurnResult` — the public type contracts
- `engine.validate()` — lazy-loaded Draft 2020-12 validator with
  `format_checker` (enforces `session_id` UUID, etc.)
- `engine.llm.build_client()` — thin OpenAI client wrapper
- `engine.dispatch.apply_world_update()` — synchronous HTTP client
  for `fs-manager:8010/tools/apply_world_update` with structured
  `DispatchResult` and optional `httpx.Client` injection for tests
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
- `engine.prompts.dm.DM_SYSTEM_PROMPT` — ported verbatim from
  `backend/api/dm_ai.py`

Still stubbed:

- `engine.agents.lorekeeper.*` — the RAG step that queries ChromaDB
  for relevant lore and injects it into the DM's context window. No
  file yet; scaffolded as BACKLOG Phase 2 once the core loop is
  running against a real backend.

Typical caller pattern (what the new FastAPI backend will do):

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

yield "data: [DONE]\n\n"
```

Not yet wired: no caller uses `engine` in production. The Django
backend (`backend/api/dm_ai.py`) still serves turns. That changes
when the new FastAPI backend lands per ADR 0001 Phase 1.

## Install

```bash
pip install -r engine/requirements.txt
```

Or run `just install` from the repo root, which now chains engine deps
alongside the other Python installs.

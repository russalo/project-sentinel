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

**Partially implemented.** The source-of-truth decision (ADR 0001)
unblocked the agent work. The MCP Bridge dispatcher and the
Fact-Extractor are real; the DM agent follows immediately after.

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
- `engine.prompts.dm.DM_SYSTEM_PROMPT` — ported verbatim from
  `backend/api/dm_ai.py`

Still stubbed (`NotImplementedError`):

- `engine.agents.dm.run_turn` and `engine.agents.dm.stream_turn` —
  land in the next commit of the `feat/engine-agents` PR
- `engine.agents.lorekeeper.*` — scaffolded directory only; full
  module deferred to Phase 2 per `docs/BACKLOG.md`

Not yet wired: no caller uses `engine` in production. The Django
backend (`backend/api/dm_ai.py`) still serves turns. That changes
when the new FastAPI backend lands per ADR 0001 Phase 1.

## Install

```bash
pip install -r engine/requirements.txt
```

Or run `just install` from the repo root, which now chains engine deps
alongside the other Python installs.

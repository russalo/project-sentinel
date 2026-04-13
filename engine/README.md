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

3. **No side effects.** `engine/` does not write to disk, query databases,
   or make HTTP calls to the MCP servers. It produces strings and
   structured payloads; the caller is responsible for dispatching them.

4. **Streaming is a generator protocol, not a framework concern.**
   `stream_turn(...)` yields tokens. Django wraps the generator in
   `StreamingHttpResponse`; a future FastAPI adapter could wrap the same
   generator in SSE. The engine doesn't know or care.

## Current status

**Scaffolding only.** The public types, schema loader, LLM client wrapper,
and DM system prompt have landed, but none of the agent functions are
implemented yet. Everything raises `NotImplementedError`. This is
intentional — see `docs/BACKLOG.md` for the remaining design decisions that
gate real implementation (source-of-truth, Fact-Extractor output shape,
agent topology).

## Install

```bash
pip install -r engine/requirements.txt
```

Or run `just install` from the repo root, which now chains engine deps
alongside the other Python installs.

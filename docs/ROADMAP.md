# Project Sentinel — Near-Term Roadmap

> **Scope:** what ships in the next 1–3 PRs. Concrete, backlog-linked,
> stack and architecture assumed fixed. For the long-term direction and
> open stack questions, see [`VISION.md`](./VISION.md).

_Last updated: 2026-04-15_

---

## Where we are

- **ADR 0001 Phases 1 and 2 are both landed.** Canonical world state is
  `data/state/*.json` + `data/lore/*.md` under git. The production backend
  is FastAPI (`backend/`), which reads state directly from `data/` and
  dispatches writes through `engine/` → `fs-manager` → `git-sync`. Django,
  Postgres, and the orphaned `db-vector` MCP server are gone.
- **The engine package is live, not scaffolding.** `engine/agents/dm.py` and
  `engine/agents/fact_extractor.py` are fully implemented — `run_turn`,
  `stream_turn`, `generate_intro`, and `extract` all have real bodies that
  the FastAPI backend calls on every per-turn request and new session.
  `backend/api/dm_ai.py` is gone; there is no inline DM logic left in
  `backend/`. See `engine/README.md` § "Current status" for the implemented
  vs. stubbed list. The only stub left is `engine.agents.lorekeeper.*` — the
  ChromaDB RAG step, which is currently an unscheduled Vision item.
- **fs-manager security gaps closed on 2026-04-15 (PR #29).** The namespace
  gate from `ARCHITECTURE.md` §2 is now actually enforced, `PROTECTED_FIELDS`
  matches the §4 Protected Fields table, the `protected_check` opt-out is
  gone, protected-field enforcement runs on both create and update, and the
  session_id directory-traversal vector surfaced by Copilot on review is
  sealed. 16-test suite in `tests/fs_manager/` covers the behaviors.
- **Live smoke test passed on 2026-04-14.** Player → FastAPI → LLM →
  Fact-Extractor → fs-manager → git-sync worked end-to-end against a real
  Ollama-backed model over LiteLLM. The pipeline has been re-smoke-tested
  via curl against the live fs-manager during PR #29's security work.
- **React is the 1.0 frontend.** Decided 2026-04-15 by the landing of
  `feat/panel-ux-entity-cards` — shipping real `EntityCard` primitives +
  wired left/right panel interactions is a de-facto commitment. The
  "frontend strategy undecided" gate that blocked feature work until now
  is resolved. See [`VISION.md`](./VISION.md) § "Resolved decisions" for
  the rationale and `CLAUDE.md` for the updated agent guidance.

---

## In flight — next 1–3 PRs

Ordered by what unblocks what. Each item links to a `docs/BACKLOG.md` entry
for the full technical detail; the roadmap stays short on purpose.

**Note on Panel UX:** the initial Panel UX primitives (`EntityCard`,
click-to-inspect wiring, panel tabs) are being built directly on
`feat/panel-ux-entity-cards` without a preceding ADR. That was an
intentional call — the ADR's open questions (tombstones for removed
entities, `mentioned_only` state for future Entity Sweeper glimpses, the
Phase 1/2/3 source-of-truth split for the system log) all depend on
downstream work that doesn't exist yet, so writing the ADR now would be
premature. The ADR is deferred until Entity Sweeper and system log work
begin. See the BACKLOG entry for the full reframing.

### 1. **Persona ID resolution (Layer 1.5)**

PR #20 wired `persona_id` through to the DM intro prompt as a raw string,
so the LLM sees `"DM persona: oracle"` with no context about what "oracle"
means. Gemini flagged on review that an opaque ID is unlikely to make the
LLM actually adopt the persona. Minimum viable fix: either (a) have the
frontend send `personaName` + a one-line `personaDescription` alongside
`personaId`, or (b) have the backend resolve the ID against a small
in-memory catalog of known personas and inject the descriptive version into
the intro prompt. Unblocks meaningful persona selection without waiting for
the full preset system in the DM Personas & Content Framework BACKLOG item.

- Backlog: [`Persona ID resolution (Layer 1.5)`](./BACKLOG.md)
- Exit criteria: the DM intro prompt for a persona-selected session contains
  the descriptive persona text, not the raw ID. Verified by a unit test
  against `_build_intro_messages`.

### 2. **git-sync unit tests**

Sibling of the fs-manager test suite that landed in PR #29. `git-sync` has
zero test coverage today — no `tests/` directory, the engine-side dispatch
tests only cover the HTTP contract via `httpx.MockTransport`. Test targets
per the BACKLOG entry: happy-path commit with the standard
`[sentinel] session=<id> turn=<N> — <summary>` message format, rollback
behavior on commit failure, the "no changes" case (empty working tree
after dispatch — must return `ok=True`), and repository-detection logic.

- Backlog: [`Write the first unit tests for mcp-servers/git-sync/`](./BACKLOG.md)
- Exit criteria: `tests/git_sync/test_server.py` exists with at least the
  four behaviors above, wired into `pytest tests/` so CI runs it.

---

## Ready but unscheduled

Work that's actionable but waiting on a specific trigger or decision:

- **Lorekeeper agent + ChromaDB indexing.** The one remaining engine agent
  stub. ChromaDB is still in the infrastructure stack specifically so this
  can land, but it's non-trivial work — needs an indexer for
  `data/lore/**/*.md`, the `engine/agents/lorekeeper.py` agent itself, and
  an integration point in the DM prompt. The honest precondition (per
  `VISION.md`) is "enough lore to query to make the RAG earn its complexity,"
  which isn't satisfied today. An ADR-sized design decision before any
  implementation.
- **Suggested Actions as a structured field** — small schema addition +
  prompt bullet + frontend pill component. Tiny change, but gated on the
  Panel UX ADR so the visuals compose correctly.
- **Entity Sweeper second-pass extraction** — design captured in memory,
  implementation deferred. Waiting on: the first few live sessions that
  produce enough "DM mentioned it but didn't emit state" examples to
  validate the approach.
- **`docs/WORKSPACE.md` rewrite** — stale against current reality (describes
  Express 5, `artifacts/api-server/src/lib/dm-ai.ts`, etc.). Lower priority
  than the README/ARCHITECTURE rewrite that shipped in PR #19 because
  WORKSPACE.md has fewer readers.

---

## Explicitly NOT near-term

These belong in [`VISION.md`](./VISION.md):

- 1.0 frontend stack decision (React stays vs. pivot)
- World identity model + multi-session support
- Background simulation / APScheduler ticking
- `.spak` export / import / Airlock pipeline
- Community pack gateway and validation CI
- Sentinel Charter governance
- Plugin API for third-party MCP tools

---

## How to use this document

When starting a session: read the "In flight" list and pick the top
unfinished item whose prerequisites are met. When finishing a session:
if you completed an in-flight item, move it to the bottom of the file
with a short "landed in PR #N" line, then promote the next unscheduled
item if its trigger has fired. When discovering new near-term work,
add it to BACKLOG first and only surface it here once it's next up.

Vision-level ideas never land here directly — they belong in
[`VISION.md`](./VISION.md) until they're concrete enough to commit to.

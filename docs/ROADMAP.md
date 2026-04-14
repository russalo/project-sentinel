# Project Sentinel — Near-Term Roadmap

> **Scope:** what ships in the next 1–3 PRs. Concrete, backlog-linked,
> stack and architecture assumed fixed. For the long-term direction and
> open stack questions, see [`VISION.md`](./VISION.md).

_Last updated: 2026-04-14_

---

## Where we are

- **ADR 0001 is fully landed.** Canonical world state is `data/state/*.json` +
  `data/lore/*.md` under git. The production backend is FastAPI (`backend/`),
  which reads state directly from `data/` and dispatches writes through
  `engine/` → `fs-manager` → `git-sync`. Django, Postgres, and the orphaned
  `db-vector` MCP server are all gone as of the cleanup PR that introduced
  this document.
- **The engine package is scaffolding.** `engine/agents/` has boundary
  tests passing but no live agent implementations yet — agent entry points
  raise `NotImplementedError`. `backend/api/dm_ai.py` is what actually
  serves turns today (via the same `engine.dispatch` path for writes).
- **Live smoke test passed on 2026-04-14.** Player → FastAPI → LLM →
  Fact-Extractor → fs-manager → git-sync works end-to-end against a real
  Ollama-backed model over LiteLLM.

---

## In flight — next 1–3 PRs

Ordered by what unblocks what. Each item links to a `docs/BACKLOG.md` entry
for the full technical detail; the roadmap stays short on purpose.

### 1. **Panel UX ADR (pre-work for the frontend refactor)**

Write ADR 0002 covering the "Panel UX system" BACKLOG item: the unified
four-view display layer (panel cards, narrative scroll, system log tab,
turn-delta feedback) that shares `EntityCard` / `DeltaMessage` / `TabbedChat`
primitives. The ADR pins down the open questions (drawer vs. modal,
tombstones for removed entities, `mentioned_only` state for future Entity
Sweeper glimpses, the Phase 1/2/3 source-of-truth split for the system log)
before any implementation.

- Backlog: [`Panel UX system — unified state rendering across four views`](./BACKLOG.md)
- Gated behind the stack decision in [`VISION.md`](./VISION.md) — if the
  1.0 frontend stays React, the ADR is actionable; if not, this work is
  premature.
- Exit criteria: ADR merged, referenced from BACKLOG.

### 2. **Engine agent migration (DM + Fact-Extractor)**

Replace `backend/api/dm_ai.py`'s inline DM/extractor logic with real
implementations under `engine/agents/dm.py` and `engine/agents/fact_extractor.py`.
The boundary contract (pure Python, no backend imports) is already enforced
by `tests/engine/test_boundaries.py`. After this, the backend routes just
wire HTTP ↔ engine and nothing else.

- Backlog: engine agent scaffolding items
- Exit criteria: `backend/api/dm_ai.py` deleted, turn loop served entirely
  out of `engine/`, smoke test still green, existing 108 tests still pass.

### 3. **CHANGELOG catch-up or explicit retirement**

`CHANGELOG.md` has an empty `[Unreleased]` section with ~6 months of
unrecorded work. Either catch it up from git history in one pass and
resume maintenance, or add a one-line "changelog is currently unmaintained"
note at the top so contributors aren't misled. Decide before the next
minor release bump.

- Backlog: [`CHANGELOG.md [Unreleased] section is empty of ~6 months of work`](./BACKLOG.md)
- Exit criteria: file is either accurate or explicitly marked unmaintained.

---

## Ready but unscheduled

Work that's actionable but waiting on a specific trigger or decision:

- **Layer 1 wiring for World Generation fields** — `genre`, `tone`, `starting_region`,
  `persona_id`, `mood`, and the modifiers land in `NewSessionRequest` and get
  fed to the DM prompt as free-form context. Unblocks later "genre definitions"
  work. Waiting on: nothing — can land anytime.
- **Suggested Actions as a structured field** — small schema addition +
  prompt bullet + frontend pill component. Tiny change, but gated on the
  Panel UX ADR so the visuals compose correctly.
- **Entity Sweeper second-pass extraction** — design captured in memory,
  implementation deferred. Waiting on: the first few live sessions that
  produce enough "DM mentioned it but didn't emit state" examples to
  validate the approach.

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

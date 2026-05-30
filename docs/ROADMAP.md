# Project Sentinel — Near-Term Roadmap

> **Scope:** what ships in the next 1–3 PRs. Concrete, backlog-linked,
> stack and architecture assumed fixed. For the long-term direction and
> open stack questions, see [`VISION.md`](./VISION.md).

_Last updated: 2026-05-30_

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
- **World Generation Layer 2 shipped (PR #39).** The preset content +
  generation pipeline that was previously vision-level work is now real:
  5 genres, 3 personas, 6 moods, and 20 regions (4 per genre) live as
  TOML files under `data/lore/core/presets/`. `backend/presets.py` loads them on
  `POST /api/session/new`, and the engine's `_build_intro_messages`
  injects the resolved fragments as a "WORLD FOUNDATIONS" paragraph
  block above the existing one-line "CREATION CONTEXT" block.
  Augments — rather than replaces — the Layer 1 (PR #20) and Layer 1.5
  persona resolution (PR #33) work: the older fields stay on
  `IntroInput` as graceful fallbacks when no preset matches. 70+ new
  tests in `tests/backend/test_presets.py` and `tests/engine/test_dm.py`.
- **Frontend test infrastructure landed (PR #37).** vitest +
  @testing-library/react now run as a dedicated CI job; first 34 tests
  cover `utils/delta.js` and the Panel UX primitives (`EntityCard`,
  `DeltaMessage`). Adding more tests is now mechanical work — the
  hard part (infra + the JSX automatic-runtime config) is done.
- **fs-manager and git-sync both have first-class CI test suites.**
  PR #29 added 16 fs-manager tests against a tmp-data fixture; PR #35
  added 10 git-sync tests against a tmp git repo. Both servers are
  exercised end-to-end (real file writes, real git commits) instead
  of just contract-tested via httpx.MockTransport from the engine
  side. The "MCP servers have no unit tests" gap is closed.
- **Mobile-responsive chat layout shipped (2026-05-30).** The game UI
  is now usable on phones. Side panels are hidden below the `lg`
  breakpoint and accessible via `Users` / `BookOpen` icon buttons in
  the TopBar that open a slide-in drawer with a backdrop-tap-to-dismiss
  pattern. CommandBar gains `env(safe-area-inset-bottom)` for notched
  iPhones. Tab touch targets, narrative padding, and Roll button label
  are all responsive. `viewport-fit=cover` added to the HTML viewport
  meta. `uiStore` gains `mobilePanelOpen` state.

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

### 1. **Frontend store + hook tests**

Vitest infrastructure landed in PR #37 with the first 34 tests covering
`utils/delta.js` and the Panel UX primitives (`EntityCard`, `DeltaMessage`).
The next slice is the Zustand stores (`chatStore`, `worldStore`, `uiStore`,
`personaStore`) and the `useDMStream` hook. `useDMStream` is the highest-
value target because it carries the SSE event parsing + delta computation
+ pendingDeltas flush ordering that's been the source of multiple bugs
(see PR #34's review history). Tests should mock `fetch` with a small
SSE-event-emitting fake — no real backend required.

- Backlog: [`Expand apps/sentinel-ui/ test coverage to stores and hooks`](./BACKLOG.md)
- Exit criteria: store unit tests landed; `useDMStream` has at least one
  end-to-end test covering the player → token → world_update → [DONE]
  ordering with delta insertion happening AFTER `commitStreamMessage()`.

### 2. **World identity & multi-session ADR**

The "world identity, world_seed persistence, and multi-session semantics"
BACKLOG item has been queued for a while and now sits as a precondition
for two unblocked items: (a) the seed-entity step of WC Layer 2 (region
preset files describe canonical NPCs/locations in prose, but there's no
structured guarantee — needs to know whether regions are keyed per world
or globally shared), and (b) Phase 2 of the Panel UX system log (the
backend hydration endpoint needs to know what session-id-to-world
mapping it's filtering by). An ADR-sized decision before any
implementation: per-clone single-world vs. multi-world-per-clone, how
`world_seed` persists, what session resume looks like.

- Backlog: [`World identity, world_seed persistence, and multi-session semantics`](./BACKLOG.md)
- Exit criteria: ADR 0002 (or whatever number lands in order) merged
  under `docs/adr/` capturing the decision and its rationale.

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

---

## Explicitly NOT near-term

These belong in [`VISION.md`](./VISION.md):

- Background simulation / APScheduler ticking
- `.spak` export / import / Airlock pipeline
- Community pack gateway and validation CI
- Sentinel Charter governance
- Plugin API for third-party MCP tools

(The 1.0 frontend stack decision and the genre/preset content system —
both previously listed here — have shipped. See "Where we are" above
and `VISION.md` § "Resolved decisions".)

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

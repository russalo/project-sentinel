# Project Sentinel — Near-Term Roadmap

> **Scope:** what ships in the next 1–3 PRs. Concrete, backlog-linked,
> stack and architecture assumed fixed. For the long-term direction and
> open stack questions, see [`VISION.md`](./VISION.md).

_Last updated: 2026-06-13_

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
  via curl against the live fs-manager during PR #29's security work, and
  re-verified against the current dev LLM (Groq `llama-3.3-70b-versatile`,
  ~4s/turn) on 2026-06-04.
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
- **World isolation: ADR 0002 accepted, Slices 1–5 landed (through resume completeness, 2026-06-03).**
  [ADR 0002](./adr/0002-world-identity-and-isolation.md) ratified repo-per-world
  isolation (one player per world, concurrently). Slices 1–4 and Slice 5's
  first chunk (resume completeness) are merged:
  `world_id` is minted per session and threaded through the backend, the engine
  dispatcher, and the git-sync commit message
  (`[sentinel] world=<id[:8]> session=… turn=… — …`); both MCP servers resolve a
  per-world tree/repo under `SENTINEL_WORLDS_ROOT` (UUID-validated +
  traversal-guarded); the **backend reads** route per-world too, worlds are
  **provisioned** at creation (git-sync `init_world`), and a **tracer-soak gate**
  (`tests/test_world_isolation_tracer_soak.py`) proves zero cross-world leak
  under concurrency — it caught and drove the fix for a real git-sync cwd race.
  The frontend now plays at a world's own URL (`/w/<world_id>`), so a game is
  shareable and survives a refresh — resume rebuilds the scroll, the world-state
  panels (entities/locations/factions/items), and the persona (id/name/mood)
  from `GET /api/world/<world_id>`.
  **`SENTINEL_WORLDS_ROOT` is unset by default**, so per-world routing is dormant
  and runtime behavior is unchanged (single shared `data/` tree); the cutover is
  now a one-line operational flip (see `docs/WORKSPACE.md` § "Per-world isolation
  cutover"). See the "ADR 0002
  implementation — remaining slices" item in [`BACKLOG.md`](./BACKLOG.md).
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
or an RFC for the full technical detail; the roadmap stays short on purpose.

**Note on process (2026-06-13):** non-trivial designs now go through an
**RFC** (Request For Comments) — a lighter sibling to ADRs. ADRs cover
long-lived architectural commitments; RFCs cover per-feature designs and
minor iterations. The RFC system itself (`docs/rfc/` + README +
TEMPLATE) is item #1 below — once it lands, items #2+ each cite the
RFC that drives them. BACKLOG transitions from a tracked planning surface
to a personal scratch / harvest pool for ideas that mature into RFCs
(also part of item #1).

### 1. **Adopt the RFC system + initial bootstrapping**

`docs/rfc/` lands as a new doc surface alongside `docs/adr/`. Includes the
README (conventions, lifecycle, BACKLOG-feeds-in pattern) + `TEMPLATE.md` +
the first RFC (`RFC 0001 — PlayerVitals vitality-fill model`, see item #2).
BACKLOG is becoming gitignored in the same batch — it transitions from a
tracked planning surface to a personal scratch / harvest pool for ideas
that mature into RFCs.

- Status: drafted (workflow output staged); pending Russell green-light to commit + push.
- Exit criteria: RFC structure on disk + BACKLOG removed from version control + first RFC live as a Draft PR.

### 2. **PlayerVitals vitality-fill flip (RFC 0001)**

Russell visual feedback 2026-06-13: the current "wound spreads from the head
as HP drops" wash should be inverted — a vessel-of-vitality that drains from
the head down as HP falls. Plus distinct visual states for **unconscious**
(HP=0 recoverable) vs **dead** (terminal), which is a status enum expansion
beyond the current `alive | dead | unknown | missing`. Solid-fill replaces
the radial gradient.

- RFC: `docs/rfc/0001-player-vitals-vitality-fill.md` (lands with item #1).
- Open questions in the RFC: unconscious/dead pose artwork; status enum
  spelling (just `"unconscious"`, or also `"dying"` / `"stable"`).
- Exit criteria: RFC Accepted; implementation PR(s) flip the math + drop
  the gradient + add status-keyed dispatch.

### 3. **Core Systems — Fantasy as flagship genre**

Russell directive 2026-06-12: define Sentinel's core systems (combat,
healing, magic, encounter mechanics, progression, time, weather, faction,
death stakes) for the **Fantasy** genre first as the canonical reference,
then other genres inherit via per-genre flavor overrides. The ambient
surfaces shipping this week (tension meter, HP silhouette) increasingly
imply a systemic layer that doesn't exist yet — each new surface widens the
gap between what testers see and what the world actually models.

- Approach (from BACKLOG): planning RFC to set scope → Fantasy v1 spec →
  pilot one system end-to-end (combat is the obvious first proof) → 2–3
  genre overrides (Sci-Fi + Cyberpunk) to validate the template.
- Backlog: [`Core Systems — Fantasy as Flagship Model`](./BACKLOG.md)
- Exit criteria: scope-RFC Accepted; combat-resolution RFC follow-up
  drafted.

### 4. **Tester self-signup page (Tuesday-window-ish)**

Per-tester reauth (PR #125) closed the recovery story; provisioning is still
operator-as-relay. Self-signup replaces that with operator green-lights a
list. Spec already in BACKLOG; needs the RFC's open calls answered before
implementation (single-use invite ledger shape, Caddy-write-back path,
audit-log credential-id pattern). RFC follow-up.

- Backlog: [`Tester self-signup page`](./BACKLOG.md)
- Exit criteria: RFC Accepted; backend + signup page + admin approval flow
  land together.

---

## Ready but unscheduled

Work that's actionable but waiting on a specific trigger or decision:

- **Lorekeeper agent + ChromaDB indexing.** The one remaining engine agent
  stub. ChromaDB is still in the infrastructure stack specifically so this
  can land, but it's non-trivial work — needs an indexer for
  `data/lore/**/*.md`, the `engine/agents/lorekeeper.py` agent itself, and
  an integration point in the DM prompt. The honest precondition (per
  `VISION.md`) is "enough lore to query to make the RAG earn its complexity,"
  which isn't satisfied today. An RFC-sized design decision before any
  implementation.
- **Entity Sweeper second-pass extraction** — design captured in memory,
  implementation deferred. Waiting on: the first few live sessions that
  produce enough "DM mentioned it but didn't emit state" examples to
  validate the approach.
- **PlayerVitals Tier 2 red-team follow-ups** — a11y Fallen-state silent
  to AT, `prefers-reduced-motion` not respected on inline SVG transitions,
  global SVG IDs (`vitals-body-clip` / `vitals-damage`) need `useId()`
  scoping for multi-instance safety, same-named NPC + DM role-strip can
  surface NPC HP as the player's. Each is its own focused PR;
  collectively waiting on the RFC-0001 vitality-fill flip landing first
  to avoid rework.

(Suggested Actions — previously listed here — shipped in PRs #112/#113.
DM emits `<action>label</action>` tags inline + a structured
`suggestedActions` field on the world_update; the SPA highlights both as
amber pill rail + inline underlines.)

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

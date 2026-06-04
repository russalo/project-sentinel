# Project Sentinel — Testing

> **Scope:** what tests exist today, how to run them, what's deliberately
> not tested yet, and where the test suite is pointing long-term.
> Structure follows the near-term / vision split from `CLAUDE.md`
> — "Current" is a commitment, "Vision" is a direction.

_Last updated: 2026-04-14_

---

## Current

### What runs in CI

Every push and pull request runs four jobs from `.github/workflows/ci.yml`:

| Job | What it runs | Runtime |
|-----|--------------|---------|
| **Validate Schemas** | The full Python test suite: `pytest tests/` | ~20s |
| **Lint Python** | `ruff check` + `ruff format --check` across `engine/`, `backend/`, `tests/`, `scripts/`, `mcp-servers/` | ~10s |
| **Typecheck TypeScript** | `pnpm run typecheck` across the pnpm workspace | ~20s |
| **Frontend Tests** | `pnpm --filter @sentinel/ui run test` — vitest + @testing-library/react against `apps/sentinel-ui/src/**/*.{test,spec}.{js,jsx}` | ~25s |

"Validate Schemas" is kept as the job's display name for branch-protection
continuity; as of PR #23 it actually runs every test under `tests/`, not just
`tests/test_schema_validation.py` like it used to.

### What the Python test suite covers

`tests/` holds **111 tests** as of this writing, split into three concerns:

- **`tests/test_schema_validation.py`** — fixture-based validation of every
  JSON Schema under `schemas/` against a set of known-good and known-bad
  payloads. The schema gate is what makes Sentinel's "LLM never touches
  the filesystem" story load-bearing; these tests fail loudly if a schema
  is relaxed in a way that would silently admit bad payloads.
- **`tests/backend/`** — route-level tests against the FastAPI backend
  (`/healthz`, `/api/session/new`, `/api/stream`) using FastAPI's
  `TestClient`. The `app` fixture in `tests/backend/conftest.py` patches
  `engine.dispatch.apply_world_update`, `engine.commit_snapshot`, and the
  OpenAI client with in-memory fakes, so the tests run offline with zero
  real network or disk I/O outside of `tmp_path`.
- **`tests/engine/`** — unit tests for the engine package: DM agent prompt
  assembly, Fact-Extractor parsing, `engine.dispatch.fs_manager` and
  `engine.dispatch.git_sync` HTTP clients (via `httpx.MockTransport`), and
  the boundary contract (`test_boundaries.py`) that enforces the engine's
  no-backend-imports rule.

### What CI does **not** cover today

Flagging gaps honestly so TESTING.md doesn't lie by omission:

- **`apps/sentinel-ui/` test coverage is the first 34 tests, not zero.**
  vitest + @testing-library/react infrastructure landed; first three
  test files cover `utils/delta.js` (14 pure-function tests) and the
  Panel UX primitives `EntityCard` (10 component tests) + `DeltaMessage`
  (10 component tests). Stores, hooks (especially `useDMStream`), and
  the rest of the components still have no coverage. Listed in
  `docs/BACKLOG.md` Developer Experience as the next vitest target
  set, but no longer load-bearing — the infrastructure is in place
  and adding more tests is mechanical.
- **No end-to-end turn loop.** We don't spin up a real fs-manager
  subprocess + real git-sync + real LLM (or a fake one) and send a
  synthetic turn through the whole pipeline. The first live smoke test
  happened manually on 2026-04-14 and is not automated.
- **No real LLM call exercised in CI.** Every test that involves the DM
  or Fact-Extractor runs against a `FakeOpenAI` client. Real-LLM quirks
  (rate limits, model-specific `<world_update>` emission differences,
  streaming ordering) are caught only by the manual smoke test.
- **No coverage tracking.** `pytest --cov` is not run, no coverage gate
  exists, no report is published. We have roughly no idea what percentage
  of lines the test suite exercises.
- **No load or perf tests.** Nobody has asked "what happens when
  `data/state/core/entities/` has 500 files and the backend re-reads them
  on every turn" in a measurable way.

### How to run tests locally

```bash
# Full suite (matches CI)
SENTINEL_SKIP_ENV_CHECK=1 pytest tests/

# Just one file
SENTINEL_SKIP_ENV_CHECK=1 pytest tests/engine/test_dm.py -v

# Just one test
SENTINEL_SKIP_ENV_CHECK=1 pytest tests/engine/test_dm.py::test_build_intro_messages_includes_creation_context_block_when_fields_set -v

# TypeScript checks
just typecheck         # pnpm -r typecheck
just build             # pnpm -r build (catches issues typecheck misses)
```

`SENTINEL_SKIP_ENV_CHECK=1` tells `backend.config.Settings.load()` to skip
the `infrastructure/.env` presence check. CI sets this at the job level;
set it manually when running the backend tests outside the repo root or
without a generated `.env`.

### Standing rules (load-bearing — don't relax without discussion)

These are the testing commitments that outlive any individual PR. If
you're tempted to break one to make a test pass, stop and talk to the
reviewer first.

1. **Integration tests that touch fs-manager or git-sync hit real disk,
   not mocks.** Memory flag on this — a prior project got burned when
   mocked tests passed but the real integration failed. The engine's
   dispatch tests use `httpx.MockTransport` for the HTTP layer (which
   is fine — that's a protocol boundary), but anything that claims to
   test "fs-manager writes a file" must actually write a file under
   `tmp_path`.
2. **Engine boundary contract is enforced by tests, not code review.**
   `tests/engine/test_boundaries.py` grep-asserts that `engine/` never
   imports from `backend/`, `django`, `psycopg2`, or anything framework-
   specific. If you need to break this, the boundary contract itself is
   wrong and needs an ADR, not a test-suite relaxation.
3. **Schema failure is a first-class control-flow path, not an error
   case.** ADR 0001 specifies that invalid `<world_update>` payloads
   from the DM are rejected and fed back to the DM to self-correct.
   Tests for this path must assert both the rejection AND the
   feedback-to-DM flow, not just "the error is raised."
4. **Test fixtures live under `tests/fixtures/`, not inline in test
   files.** Large JSON payloads or schema examples go in fixture
   files so they can be diffed and re-used; test files stay short
   enough to read end-to-end.
5. **Every test must be deterministic and offline.** No real network
   calls, no real LLM, no wall-clock sleeps, no "retry three times and
   hope." If a test needs randomness, seed it. If it needs a timestamp,
   inject one.

### Near-term test work (next 1–3 PRs)

Most of the "near-term" work that was originally queued has shipped
(see "Resolved" below for what landed). What's left, ordered by
dependency:

1. **Expand frontend test coverage to stores and hooks.** vitest +
   @testing-library/react infrastructure landed with the first 34
   tests covering `utils/delta.js` + the `EntityCard` and
   `DeltaMessage` primitives. The next slice is the Zustand stores
   (`chatStore`, `worldStore`, `uiStore`, `personaStore`) and the
   `useDMStream` hook — the latter is the trickiest because it
   touches `fetch` and the stream parser, but it's also the highest
   value for catching turn-loop regressions. Tests should mock
   `fetch` with a small SSE-event-emitting fake.

2. **Component tests for the rest of `apps/sentinel-ui/`.** The
   Panel UX primitives are covered, but `NarrativeScroll`,
   `WorldCreation`, `PersonaSheet`, `LiveSeedPreview`, the
   left-panel lists, etc. all have zero coverage. Mechanical work
   that benefits from the existing test patterns — defer until a
   regression makes one of them load-bearing.

### Resolved (recent)

- **vitest + @testing-library/react infrastructure + first 34 tests**
  — landed with this doc's most recent revision (the PR that touched
  this file). Pure-function tests for `utils/delta.js`, component
  tests for `EntityCard` and `DeltaMessage`. CI runs them as the
  "Frontend Tests" job.
- **fs-manager spec/code gap closure + 16 unit tests** — landed in
  PR #29. Closed the ARCHITECTURE.md ↔ `server.py` divergence
  (namespace gate, `core_faction_id` protection, `protected_check`
  opt-out removal, create-path enforcement) and shipped the first
  unit tests against a real tmp git repo.
- **git-sync first unit-test suite (10 tests)** — landed in PR #35.
  Same shape as the fs-manager tests: TestClient + tmp git repo
  fixture, end-to-end coverage of the commit / no_changes / error
  paths.
- **Engine agent tests for DM + Fact-Extractor** — actually landed
  long before any of the recent work; `tests/engine/test_dm.py` and
  `tests/engine/test_fact_extractor.py` have always covered the
  prompt assembly and parsing paths. The previous version of this
  doc described them as pending because of stale planning-doc
  drift, not because they were actually missing. Verified during
  the engine migration recon (PR #31).

---

## Vision

These are the things we're pointing at, not a commitment. Each is listed
with its trigger — the condition that would make the item worth moving to
the Current section.

### Integration tests against real fs-manager + git-sync

Today the engine's dispatch tests mock HTTP via `httpx.MockTransport`.
That's the right call for unit testing, but it means nothing tests that
the real fs-manager process correctly applies a payload to real files
and that the real git-sync process correctly commits the result. The
vision: a `tests/integration/` tier that starts fs-manager and git-sync
as subprocesses against a temporary data directory, pushes a synthetic
`apply_world_update` payload through, and asserts both the files on
disk and the resulting git commit.

**Trigger:** the first production-like bug that mocks fail to catch.
Until then, the cost of maintaining a subprocess-based test tier isn't
worth it for a solo project.

### End-to-end turn loop

A single test that plays the role of a player: spins up the FastAPI
backend against a fake LLM that returns a canned narrative +
`<world_update>` block, hits `/api/stream` with a player action, and
asserts that the resulting state change lands on disk AND in a git
commit AND that the next `/api/stream` call sees the updated state.
This would catch the entire class of "each layer's tests passed but
the handoff was broken" bugs that the 2026-04-14 live smoke test had
to find manually.

**Trigger:** the Panel UX ADR (ROADMAP #1) ships a backend endpoint for
system log hydration. At that point there's enough moving parts in the
turn loop that manual smoke tests start missing things, and the
subprocess infrastructure pays for itself.

### Schema property tests (hypothesis-style)

Current schema tests use fixtures: a handful of known-good and
known-bad payloads. Property tests would generate arbitrary payloads
from the schema itself, assert that any schema-conforming payload is
accepted and any schema-violating payload is rejected, and surface
corner cases the fixture tests don't. The `hypothesis-jsonschema`
library can do this directly from a schema file.

**Trigger:** a schema-related bug escapes the fixture tests and lands
in a `<world_update>` that fs-manager accepts but shouldn't have.

### Playwright E2E for the frontend

Once the 1.0 frontend stack question in `docs/VISION.md` is settled
and a real client exists, Playwright tests driving it through a full
world-creation + multi-turn session against a fake-LLM backend would
catch the end-to-end flows that no unit test covers: "does the panel
card show the right data after three turns", "does the system log
accumulate correctly across reloads", "does the DM stream render
without visual glitches."

**Trigger:** the Panel UX system ships (ROADMAP #1) and stabilizes
for long enough that the UI is worth regression-testing, AND the 1.0
frontend stack decision makes it worth investing in a specific tool's
test infrastructure.

### Coverage tracking and enforcement

Add `pytest-cov` to the Python side and a similar tool to the
frontend side, publish a coverage report per PR, and eventually gate
merges on coverage regressions. Open question: **hard fail vs
report-only.** Hard fail incentivizes good coverage but also
incentivizes useless coverage-padding tests; report-only trusts the
reviewer to catch gaps. Probably start report-only and escalate only
if the numbers trend the wrong way.

**Trigger:** coverage drops below some line we care about, OR a PR
ships with "I forgot to test this" as its followup.

### Load and performance tests

The bet underneath ADR 0001 is that re-reading `data/state/*.json` per
turn is cheap enough that it doesn't need a cache layer. At v1.0 scale
(hundreds of entities, not millions) this is probably true, but nobody
has measured it. Vision: a benchmark suite that generates a world with
N entities and M sessions, replays synthetic turns through the
backend, and measures p50/p95 turn latency and per-turn allocation
pressure. If the filesystem-as-truth assumption ever starts to break
under realistic load, we want the benchmark to tell us before a real
player does.

**Trigger:** a real player session generates enough entities to make
someone worry.

### Real-LLM smoke tests in CI

A handful of end-to-end tests that actually hit a real LLM
(e.g. cloud-hosted Groq, or a small local Ollama-backed model via LiteLLM) and verify that a real model
emits a `<world_update>` block in a shape the Fact-Extractor can
parse. This catches prompt-drift issues: the model's output subtly
changes shape over time as upstream models update, and fixture-based
tests using `FakeOpenAI` can't detect it.

**Trigger:** the first production incident where the DM's output
format shifted and manual QA missed it. Until then, running a real
LLM in CI is cost and flakiness for unclear benefit.

---

## How this document gets updated

- When a **Current** item becomes stale (test suite changes, new job,
  etc.): update it in the same PR that ships the change.
- When a **Vision** item's trigger fires: move it to the Near-term work
  section in Current, with a dated entry. When it ships, move it again
  to the main Current description.
- When a **Vision** item gets explicitly rejected or superseded: delete
  it (or move it to a short "Rejected" footer with a one-line reason).
- When the standing rules change: they need an ADR or a conversation
  that lands in memory, not a silent edit. The rules are testing
  *commitments*, not preferences.

---

## Related

- **`docs/ROADMAP.md`** — the near-term work items this doc's
  Near-term test work section is aligned to
- **`docs/VISION.md`** — the long-term stack/architecture direction
  that the Vision section is pointing at
- **`docs/BACKLOG.md`** — discovered test-related work that hasn't
  earned a spot on the roadmap yet (frontend test scaffolding,
  fs-manager CI wiring, etc.)
- **`CLAUDE.md` → Planning Docs: Near-Term vs Vision** — the principle
  this file is structured under

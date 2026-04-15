# Project Sentinel — Testing

> **Scope:** what tests exist today, how to run them, what's deliberately
> not tested yet, and where the test suite is pointing long-term.
> Structure follows the near-term / vision split from `CLAUDE.md`
> — "Current" is a commitment, "Vision" is a direction.

_Last updated: 2026-04-14_

---

## Current

### What runs in CI

Every push and pull request runs three jobs from `.github/workflows/ci.yml`:

| Job | What it runs | Runtime |
|-----|--------------|---------|
| **Validate Schemas** | The full Python test suite: `pytest tests/` | ~20s |
| **Lint Python** | `ruff check` + `ruff format --check` across `engine/`, `backend/`, `tests/`, `scripts/`, `mcp-servers/` | ~10s |
| **Typecheck TypeScript** | `pnpm run typecheck` across the pnpm workspace | ~20s |

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

- **`apps/sentinel-ui/` has zero tests.** No vitest, no
  `@testing-library/react`, no component or store tests. Typecheck only.
  Flagged in `docs/BACKLOG.md` under Developer Experience; scheduled to
  land alongside the Panel UX primitives (`EntityCard`, `DeltaMessage`,
  `TabbedChat`) per `docs/ROADMAP.md` step 1.
- **`mcp-servers/git-sync/` has no unit tests.** `fs-manager/` got its
  first 16-test suite in PR #29 as part of the security-gap closure,
  but `git-sync/` — the only thing that produces the per-turn git
  audit trail — still has no `tests/` directory. The engine-side
  dispatch tests (`tests/engine/test_dispatch_git_sync.py`) cover the
  HTTP contract via `httpx.MockTransport`, which validates the
  request/response shape the backend relies on but does not test the
  server's internal commit logic or rollback behavior. Flagged in
  `docs/BACKLOG.md`.
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

Ordered by dependency. Each links to a `docs/BACKLOG.md` item:

1. **vitest + `@testing-library/react` wiring for `apps/sentinel-ui/`.**
   Scaffold the frontend test infrastructure when the Panel UX primitives
   (`EntityCard`, `DeltaMessage`, `TabbedChat`) land. These are pure
   components — fixture-based unit tests against rendered output, no
   store wiring — which is the smallest possible unlock for
   frontend CI coverage. Wire the resulting `pnpm --filter @sentinel/ui
   test` invocation into the Typecheck TypeScript job (or a new
   "Frontend Tests" job).
2. **Engine agent tests for DM + Fact-Extractor once they land in
   `engine/agents/`.** The migration from `backend/api/dm_ai.py` to
   `engine/agents/dm.py` (ROADMAP item #2) should ship with full unit
   test coverage of the intro and normal-turn prompt assembly paths,
   using `FakeOpenAI` and matching the style of the existing
   `test_dm.py::_build_intro_messages_*` tests.
3. **Close the ARCHITECTURE.md ↔ `server.py` spec/code gap in
   `mcp-servers/fs-manager/`, then write the first unit tests.** This
   was originally scoped as just "write the first tests" but review
   on PR #25 surfaced that parts of fs-manager's documented behavior
   don't actually exist in code. Two things the spec promises but
   server.py doesn't enforce:
   - **Namespace gate.** ARCHITECTURE.md §2 says writes to
     `data/{state,lore}/core/` are blocked unless the payload carries
     a `"namespace": "core"` authorization token. `server.py` has no
     such check.
   - **`core_faction_id` protection.** ARCHITECTURE.md §4 lists it as
     a protected field. `server.py`'s `PROTECTED_FIELDS` set omits it.

   Before writing tests, decide whether to implement the missing
   enforcement or pare ARCHITECTURE.md back to match the code. Then
   the test work has a real target. First test slice once the spec
   and code agree: path traversal rejection (`..` and absolute paths
   outside `data/`), full protected-field blocklist, namespace gate
   (if it lands), schema validation rejection, commit rollback on
   partial failure. Wire into `pytest tests/` once the tests exist.
   The tracking BACKLOG item covers both halves.

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

A handful of end-to-end tests that actually hit a small local LLM
(e.g. Ollama-backed Qwen via LiteLLM) and verify that a real model
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

# ADR 0001 — `data/` is the canonical source of truth

**Status:** Accepted
**Date:** 2026-04-13
**Deciders:** Russell Pfister; Claude (design session on 2026-04-13 following the engine/ scaffold PR #9)
**Supersedes:** — (no prior ADR)

---

## Context

As of 2026-04-13, Project Sentinel has two internally inconsistent stories
about where the canonical world state lives, and every downstream design
question stalls on that inconsistency.

### What the project documents say

`README.md`, `ARCHITECTURE.md`, and the Core Principles all assert a clear
answer:

> *"The Inference Node is never granted direct filesystem access. All world
> mutations route through local MCP servers that validate every write against
> JSON Schema contracts before anything persists."*

> *"Prompt-Driven Development at the infrastructure level: the narrative is
> the API, the schema is the contract, and the MCP server is the enforcer."*

> *"Human-Readable — Lore stored in Markdown; state stored in JSON."*

> *"Schema-Enforced — The Inference Node is never granted raw filesystem
> access."*

Taken together, these claim that `data/lore/*.md` (narrative) and
`data/state/*.json` (structured state) are the canonical ground truth, that
`fs-manager` is the only component permitted to write to them, that
`git-sync` commits each write for auditability, and that the entire design
exists to prevent an LLM from ever corrupting state because **the schema
gate is the actual gate**.

`ARCHITECTURE.md` additionally commits the project to:

- A Core/Community namespace split at the filesystem level (§1)
- Protected-field enforcement at schema write time (§4)
- Community content packs distributed as file trees with a `community.json`
  manifest (§3)
- A Sentinel Porter that exports worlds as `.spak` archives by bundling
  subtrees of `data/` (§8)
- An Airlock / Veil pipeline that sanitizes PII before packaging (§8)

Every single one of these features presumes that `data/` is the source of
truth. They do not work if `data/` is a derived export of something else.

### What the code actually does

`backend/api/dm_ai.py` (merged in PR #7 as the Django production backend) is
the code that currently runs when a player submits an action:

1. Build world context by querying Postgres via Django ORM (`Character`,
   `Location`, `Faction`, `Item`, `WorldState`, `Turn`, `Session`)
2. Build the DM prompt from that context
3. Call OpenAI, stream tokens to the frontend
4. Regex-extract the `<world_update>` JSON block from the raw response
5. Mutate Postgres directly via the ORM (`apply_world_update()`)
6. Save a new `Turn` row

At no point in this flow does the code:

- Validate the payload against `schemas/apply_world_update.schema.json`
- Call `fs-manager:8010`
- Call `git-sync:8012`
- Write anything to `data/state/*.json`
- Write anything to `data/lore/*.md` (session transcripts)
- Create a git commit

The MCP Bridge exists and works — `fs-manager`, `db-vector`, and `git-sync`
are all running FastAPI servers with real schema enforcement — but **nothing
calls them during normal play.** The schema gate the README describes is
not in the hot path. The Inference Node (the LLM and its wrapper code in
`backend/api/`) *does* have direct filesystem and database access, via the
Django ORM and Django's runtime.

`data/state/` and `data/lore/core/sessions/` contain a handful of hand-made
fixtures and nothing from any actual play session. Every turn since the
Django backend shipped has written to Postgres only.

### Why this is a problem to resolve now

The `engine/` package landed in PR #9 as the pure-Python scaffold for the
"real" Inference Node — DM, Fact-Extractor, and Lorekeeper agents. The
Fact-Extractor is the next piece of concrete work (BACKLOG High Priority),
and it is blocked on this decision: the Fact-Extractor's job is to produce
a schema-valid payload that "dispatches to some consumer," and the consumer
determines the output shape.

If Postgres is canonical, the Fact-Extractor produces ORM-flavored updates
that are dispatched to the Django write layer. If `data/` is canonical,
the Fact-Extractor produces `apply_world_update.schema.json`-shaped payloads
that are dispatched to `fs-manager`. These are not compatible, and you
cannot start writing the Fact-Extractor without picking one.

Every other downstream question — where the new Inference Node lives, what
the engine's boundary contract is, how community packs get loaded, what
`.spak` export looks like, whether `dm_ai.py` survives or gets rewritten —
flows from this one decision.

### Why the docs and the code disagree

The project's documented architecture was written early, describing an ideal
system. The code was built iteratively under time pressure, following a
different pragmatic path: PR #7 (the Django backend) was the right decision
*at the time it was made* because:

- The Replit-era Express backend had to be replaced for licensing and
  portability reasons
- The frontend needed a working backend urgently so development could
  continue
- The user (who is the sole maintainer) already knew Django well
- Nobody had yet sat down and asked "but what is the canonical store?" — the
  answer just got inherited from what was already in place

This ADR is not a criticism of PR #7. It is the resolution of a question
that PR #7 did not have to answer but this decision does.

---

## Decision drivers

Stripping out implementation guesses and re-reading the project's own core
principles, the values this decision must serve are:

1. **The AI cannot corrupt state.** Schema validation must be enforced at
   the write boundary, not hoped for in the middle of the stack. This is
   the single most-repeated claim in the project's documentation, and it is
   the entire reason the MCP Bridge exists.

2. **Community-friendly plug-and-play packs.** Contributors must be able to
   ship content as distributable file trees with a `community.json`
   manifest. Not as SQL import scripts, not as Django management commands,
   not as API calls. `ARCHITECTURE.md §3` is explicit about this, and it is
   a major contributor-acquisition play.

3. **Human-readable canonical representation.** Both lore and state should
   be `cat`-able. If the truth lives in a database, "human-readable" becomes
   a lie — the JSON file you're looking at is a stale export, not the
   source. Core Principles #3 (*"Human-Readable — Lore stored in Markdown;
   state stored in JSON."*) demands that the file IS the truth.

4. **Auditable, shareable, forkable history.** The git-backed narrative is
   the entire point of the Sentinel Porter work in `ARCHITECTURE.md §8`.
   Export a world, share it, fork it, import someone else's, replay a
   campaign. All of this requires that commits represent real state changes
   you can diff and checkout.

5. **Narrative as the API, schema as the contract, MCP server as the
   enforcer.** This is stated verbatim in the README opening. Any
   architecture where the MCP Bridge is not in the write path demotes this
   to marketing copy.

6. **Modularity.** Core Principle #2: *"Every subsystem is independently
   replaceable."* A design that couples the Django ORM to the storage model
   couples them forever.

7. **Runs autonomously for months.** Core Principle #1: *"Automation First
   — The world updates itself. Zero manual file handling."* This is a
   concurrency and durability concern, not a performance-at-any-cost
   concern.

These are the values. The decision is scored against them, not against
convenience.

---

## Options considered

Three options were viable. Each was scored against the seven values above.

### Option A — Postgres canonical, `data/` is a derived export target

**Per-turn flow:**
1. Engine produces narrative and a schema-valid payload
2. Engine validates the payload against
   `schemas/apply_world_update.schema.json` in-process
3. Engine writes to Postgres (via `db-vector` MCP or direct ORM)
4. On demand (export, backup, share): serialize Postgres state to
   `data/state/*.json` and git-commit it

**How it scores:**

- AI cannot corrupt state: ⚠ depends entirely on engine-side validation.
  `fs-manager` is no longer a gate for per-turn writes — it's only invoked
  at export time. The "schema gate is the actual gate" story weakens to
  "there's a validator somewhere in the engine."
- Community packs: ❌ **broken.** A community pack is a file tree under
  `data/lore/community/<author>/`. If `data/` is a derived export, the
  engine doesn't read from there at all. Packs would have to become SQL
  import scripts or Django management commands, which is a much worse
  contributor experience and kills the value proposition.
- Human-readable canonical representation: ❌ the JSON files under `data/`
  are stale snapshots. "The truth is in Postgres" contradicts Core
  Principle #3.
- Shareable history / `.spak`: ⚠ requires building a Postgres serializer to
  produce the export. Doable but a separate pipeline.
- Schema gate is real: ⚠ it's a validator in the engine's call graph, not
  a process boundary between the LLM and the filesystem.
- Modularity: ⚠ tight Postgres coupling; Django models define the shape of
  game state.
- Runs for months: ✅ Postgres is built for this.

**Summary:** cheap to implement from where the code is today, but breaks
two of the most load-bearing stated values (community packs, schema gate as
a real gate) and compromises a third (human-readable canonical
representation). Rejected.

### Option B — `data/` is canonical, Postgres is a derived read cache

**Per-turn flow:**
1. Engine produces narrative and a schema-valid payload
2. Engine dispatches payload to `fs-manager:8010` via HTTP
3. `fs-manager` validates against
   `schemas/apply_world_update.schema.json`, enforces protected fields,
   performs path-regex checks, and writes to `data/state/*.json` and
   `data/lore/*.md`
4. `git-sync:8012` commits the write atomically
5. A Postgres projection (if it still exists) gets rebuilt or incrementally
   updated from `data/`, serving only as a read cache for the
   read-side API layer

**How it scores:**

- AI cannot corrupt state: ✅ `fs-manager` is the actual gate. The LLM never
  has a path to disk that bypasses schema validation. This is the
  value being preserved.
- Community packs: ✅ works exactly as documented. Drop a pack tree into
  `data/lore/community/<author>/` and the engine reads from it natively.
- Human-readable canonical representation: ✅ the file on disk IS the truth.
  `cat data/state/core/entities/kael.json` is not a stale export, it is
  the record.
- Shareable history / `.spak`: ✅ trivial. Export is `tar czf` on a subtree.
- Schema gate is real: ✅ this is the option where the stated architecture
  is honest.
- Modularity: ✅ the fewest moving parts. Storage is just a filesystem
  layout; nothing is pinned to a particular database or ORM.
- Runs for months: ⚠ concerns about per-turn write speed and concurrency;
  addressed in the "Rationale" section below with actual arithmetic.

**Summary:** preserves every stated value. The only cons are engineering
concerns (write speed, concurrency, rewrite cost) rather than value
trade-offs. Selected.

### Option C — Split: Postgres for hot state, `data/` for snapshots at commit boundaries

**Framing:** treat Postgres as the in-game runtime and `data/` as the save
file. During normal play, writes go to Postgres. On save/milestone/export,
state is serialized to `data/state/*.json`, validated by `fs-manager`, and
git-committed.

**How it scores:**

- AI cannot corrupt state: ⚠ the schema gate is split — engine-side
  validation for per-turn Postgres writes, `fs-manager` only for save
  writes. Two enforcement boundaries to maintain.
- Community packs: ✅ (as a load-time import into Postgres)
- Human-readable canonical representation: ⚠ truth lives in Postgres during
  play, in JSON between plays. Readable, but split.
- Shareable history / `.spak`: ✅ save = export by construction.
- Schema gate is real: ⚠ half real (at save); not real at per-turn.
- Modularity: ⚠ two representations create coupling — the serializer has to
  track both, and drift between them is a realistic failure mode.
- Runs for months: ✅.

**Summary:** this was the initial recommendation from the design
conversation, positioned as the engineer-pragmatic middle ground ("every
real RPG has a runtime and a save file"). It was rejected after the user
pointed out that it was optimizing for "what real RPGs look like" rather
than for "what Project Sentinel values." The split preserves most values
but dilutes two of them (schema gate, human-readable canonical), and it
commits the project to maintaining two state representations forever.
Rejected.

### Scoring summary

| Value | A (Postgres canonical) | B (`data/` canonical) | C (split) |
|---|:---:|:---:|:---:|
| 1. AI can't corrupt state | ⚠ | ✅ | ⚠ |
| 2. Community packs as file trees | ❌ | ✅ | ✅ |
| 3. Human-readable canonical state | ❌ | ✅ | ⚠ |
| 4. Shareable history / `.spak` | ⚠ | ✅ | ✅ |
| 5. Schema gate is the real gate | ⚠ | ✅ | ⚠ |
| 6. Modularity | ⚠ | ✅ | ⚠ |
| 7. Runs for months autonomously | ✅ | ✅ | ✅ |

**B is the only option where every stated value is preserved without
compromise.**

---

## Decision

**`data/state/*.json` + `data/lore/*.md` + git is the canonical source of
truth for Project Sentinel. All world-state writes must pass through the
engine → `fs-manager` → `git-sync` path. The Inference Node never gets
direct filesystem or database access.**

Adopting this in a single monolithic rewrite is unsafe and unnecessary.
The decision is implemented in two phases:

### Phase 1 — canonical by path, Postgres demoted to read cache

The immediate scope:

1. The new FastAPI backend (replacing the Django backend) reads from `data/`
   directly for all read-side API endpoints. No ORM, no Django models in
   the hot path.
2. All writes go through the `engine/` package, which dispatches validated
   payloads to `fs-manager:8010` and commits via `git-sync:8012`. The
   engine's boundary contract already forbids direct filesystem access;
   this is it being honored.
3. Postgres continues running. It is rebuilt from `data/` on startup (fast
   at v1.0 scale — hundreds of records, not millions) and serves as a
   derived read cache if and only if performance measurement proves it
   necessary. In practice for v1.0, reading JSON files directly is
   expected to be fast enough that the Postgres cache layer is not worth
   maintaining, and Phase 1 will likely ship without actively using it.
   If the cache turns out to be retained *and* a future world grows large
   enough that full-rebuild-on-startup becomes a noticeable delay, the
   upgrade path is incremental sync — a filesystem watcher, a change-log
   append, or a hash comparison between the Postgres state and the
   `data/` tree — rather than continuing to rebuild from scratch. That
   upgrade is not designed in this ADR because the expected outcome is
   Phase 2 (removing Postgres entirely) lands before it becomes
   necessary.
4. Django, `backend/api/dm_ai.py`, `backend/api/models.py`, and
   `backend/api/views.py` are replaced by the new FastAPI layer. The Django
   codebase is removed from the repo in the same PR that lands its
   replacement, not left as dead code.
5. `artifacts/api-server/` (the Express + Drizzle dev reference backend)
   retires in the same cleanup. It has been vestigial since PR #7 and has
   no remaining purpose. `lib/db/` (the Drizzle schema) retires with it.

### Phase 2 — drop Postgres entirely (deferred, optional)

If and when Phase 1 proves that the Postgres cache layer is never actually
load-bearing, Phase 2 removes Postgres from the Docker stack:

1. Remove `sentinel-postgres` from `infrastructure/docker-compose.yml`
2. Remove `infrastructure/migrations/*.sql`
3. Remove any remaining psycopg2 / database-URL wiring
4. Update `just` recipes, documentation, and health checks accordingly

Phase 2 is deferred to a future ADR or BACKLOG item. It is not a
precondition for declaring this ADR implemented.

---

## Rationale

### Why Option B over the others

The scoring table above is the short answer: Option B is the only one
where the core stated values are preserved unanimously. The qualitative
argument that reinforces this:

- **The schema gate is the whole point.** If the MCP Bridge exists to
  enforce that the AI cannot write unvalidated state, and the AI is not
  actually using the MCP Bridge for writes, then the MCP Bridge is
  decoration. Option B is the only option where the Bridge is load-bearing
  at all times. Options A and C turn it into a validator you could
  equivalently implement as a function call inside the engine.

- **Community packs are a first-class contributor acquisition story.** The
  project's `CONTRIBUTING.md` and `ARCHITECTURE.md §3` sell content
  contribution as "drop files in a folder and the engine picks them up."
  Option A breaks this completely. If we want to keep the Lore-Smith
  contributor pathway, we need Option B.

- **`data/` has to be real for `.spak` to mean anything.** The portability
  section of `ARCHITECTURE.md` is quite specific about `.spak` archives
  being `tar.gz` bundles of the relevant `data/` subtree with PII scrubbed.
  This is only trivial in Option B. In Option A, export becomes "dump the
  Postgres state, convert to JSON, figure out the Veil scrubber, archive."
  That's a build to do, not a bundle to tar.

- **Forkable history requires real git history.** The repo's own tagline
  is about running a campaign for months with full auditability. In Option
  B, `git log data/state/core/entities/kael.json` is the character's entire
  arc. In Option A, git history contains exports — snapshots taken at
  arbitrary points — and tells you nothing about what happened in between.

### Why Phase 1 and not "rip out Postgres now"

Two reasons.

First, ripping out Postgres is a separate, larger rewrite than the one
already required to land the new FastAPI backend. Combining them inflates
the blast radius of a single PR. Phase 1 ships the FastAPI backend and
makes `data/` canonical; Phase 2 deletes Postgres. These are independently
testable and independently revertible.

Second, there is a small amount of residual value in keeping Postgres
around during the transition as a fallback — if the new read-side logic
has a bug, there is still a working Django view we can point the frontend
at while the bug is fixed. Once Phase 1 is stable in production-equivalent
use, Phase 2 becomes safe.

### Addressing the "`data/` is slow" concern

The obvious objection to Option B is that every turn becomes multiple file
writes plus a git commit, and that sounds slow. The arithmetic does not
support this objection.

A turn in the current system takes 2–10 seconds, almost entirely dominated
by OpenAI inference latency. A Sentinel turn does not run in a tight loop;
it runs at human reading pace.

The filesystem cost of a per-turn write under Option B, on SSD:

- 1–3 JSON file writes (merged entity updates) — ~5–20 ms
- 1 Markdown append (session log) — ~2–5 ms
- 1 `git add` + `git commit` — ~50–200 ms depending on pack state
- Total: roughly 100–500 ms per turn

As a fraction of end-to-end turn latency, this is **5–10% of the total**.
It is not observable to the player.

The concurrency concern is similarly overstated for v1.0. Sentinel's
current design target is single-player. There is exactly one writer per
session (the DM agent). Background world simulation (ARCHITECTURE.md §7)
runs on its own cadence and can take a filesystem lock via `fs-manager`.
Multi-player is not a v1.0 requirement and can be revisited in a future
ADR if and when it becomes one.

The query capability concern ("can I list all characters in region X?")
resolves to "yes, by loading the entity tree and filtering in memory,
which is milliseconds at the 100-entity scale a v1.0 world occupies." If
world sizes grow past 10k entities, an in-memory index becomes worthwhile.
We do not pre-optimize for a scale we do not have.

### Why the original tech choices don't carry their own weight

Several of the existing technology decisions (Django, Postgres, Drizzle
ORM, the Express backend in `artifacts/api-server/`) were made early,
under time pressure, based on what the user was already familiar with from
other projects. They were the right call for shipping working code
quickly, but they were not chosen because they specifically served the
project's stated values. The user was explicit about this during the
design conversation on 2026-04-13:

> *"We need to stay true to the values of what we are looking to achieve
> not necessarily follow the guess of what that looked like when they
> wrote the document."*

> *"The technology was implied from what I was familiar with not to what
> the best fit was."*

This ADR takes those statements at face value. The existing stack is
treated as a starting point to re-evaluate, not a set of constraints to
preserve. Components that do not earn their seat against the values get
retired; components that do (ChromaDB, the MCP servers, the `engine/`
package, the frontend, `data/`, `schemas/`) stay.

---

## Consequences

### Positive

- **The schema gate becomes real.** Every write to world state passes
  through `fs-manager`, which validates against
  `schemas/apply_world_update.schema.json` and enforces protected fields
  before anything hits disk. The AI's filesystem isolation is enforced by
  architecture, not by discipline.
- **Community packs work as designed.** A contributor drops a file tree
  into `data/lore/community/<author>/` with a `community.json` manifest,
  and the engine reads from it natively. No import scripts, no migration
  dances, no API calls — files on disk are live.
- **`.spak` export is trivial.** `tar czf world.spak data/state/core/
  data/lore/core/codex/` plus a small metadata stub. The Airlock / Veil
  PII-scrubbing pipeline becomes a file-content transform rather than a
  database-export transform.
- **Git log is the campaign timeline.** `git log` over `data/state/` shows
  every state change the AI made, in order, with timestamps and the
  session context. Diffs between two commits show exactly what changed in
  a given time window. Checking out an old commit rehydrates the world at
  that point in time. Fork-and-diverge campaigns become a native git
  workflow.
- **Stack consistency.** With Django retired, every server-side component
  is FastAPI: `fs-manager`, `db-vector`, `git-sync`, and the new backend.
  One async model, one dependency tree, one deployment story, one set of
  patterns to learn.
- **Fewer moving parts.** Removing Django, Postgres (eventually), Drizzle,
  and the Express dev reference reduces the active dependency surface by
  roughly a third. `just install` gets faster, `docker-compose up` becomes
  cheaper, the test surface shrinks.
- **The Inference Node's boundary contract (PR #9) is finally honored.**
  The engine package's "no direct filesystem access, no database queries,
  no side effects" rules already existed; this ADR makes them actually
  matter by ensuring the engine has to use the MCP Bridge to do anything.
- **The code agrees with the docs.** The `ARCHITECTURE.md` document that
  describes the system matches the code that implements it — not after a
  doc rewrite, but after a code rewrite. That's the direction we want the
  correction to go.

### Negative

- **The biggest backend rewrite in the project's history.** The Django
  code in `backend/` — the production backend shipped in PR #7 — is
  replaced. The existing views, models, and serializers are discarded.
  The SSE streaming endpoint is rebuilt on FastAPI primitives. This is
  real work and it retires real code that was written recently.
- **Time cost.** Writing a new backend that covers feature parity with PR
  #7 is not free. It is at least a few PRs of work, during which the
  project is in a partial-transition state.
- **Two ways of reading state during the transition.** Until the FastAPI
  backend is serving all routes, there may be a brief window where the
  frontend is still hitting the Django backend for some endpoints and the
  new backend for others. This window should be short, but it exists.
- **Multi-player concurrency becomes harder.** If Sentinel ever grows to
  support multiple simultaneous players in the same world, filesystem
  locking via `fs-manager` is a less forgiving concurrency model than
  Postgres row-level locking. This is a deferred concern (not a v1.0
  requirement) and can be revisited in a future ADR if it materializes.
- **Drizzle, Django, and Postgres experience doesn't carry forward.** The
  user's familiarity with these was a legitimate velocity advantage and
  has been, for a while, the reason they were in the stack. That
  advantage is spent in this decision.

### Neutral

- **ChromaDB stays.** It serves a distinct purpose (vector search over
  lore text for the Lorekeeper RAG step) that nothing else in the stack
  replaces. It is not affected by this decision.
- **The frontend (`apps/sentinel-ui/`) is unaffected.** It talks to a
  backend over HTTP and SSE. It does not know or care whether that backend
  is Django or FastAPI, and does not know whether state lives in Postgres
  or in JSON files. The existing fetch-based SSE streaming contract is
  preserved.
- **`engine/` is unaffected.** It was scaffolded in PR #9 with a boundary
  contract that already forbids Django and direct filesystem access. This
  ADR validates those choices rather than changing them.
- **The MCP servers are unaffected except that `db-vector`'s role
  narrows.** `fs-manager` and `git-sync` stay exactly as they are.
  `db-vector` was designed to route structured queries to Postgres and
  semantic queries to ChromaDB; with Postgres retiring, it becomes either
  a ChromaDB wrapper or a unified read layer over `data/` + ChromaDB. The
  exact shape is deferred to a separate BACKLOG item.

---

## Implementation implications

This ADR does not itself change any code. It records the decision and
implies the work that has to happen to honor it. The concrete follow-ups:

### New work

1. **`engine/dispatch/` module.** A new submodule of the engine package
   that wraps an HTTP client for calling the MCP servers (`fs-manager`,
   `git-sync`, and eventually `db-vector`). Takes a `Config` with the MCP
   server URLs. Used by the Fact-Extractor and by any future save/export
   path. Small, testable in isolation against a mock server. Tracked in
   `docs/BACKLOG.md`.

2. **`engine/agents/fact_extractor.py` implementation.** Now that the
   output shape is pinned (`apply_world_update.schema.json` with
   `fs-manager` as the single consumer), the Fact-Extractor can be
   written as a pure function: raw DM response + session context → valid
   payload. Full unit test coverage is possible because there are no side
   effects. Tracked in `docs/BACKLOG.md`.

3. **New FastAPI backend.** Replaces `backend/sentinel/` and
   `backend/api/`. Responsibilities:
   - Read routes (`/api/world`, `/api/characters`, `/api/locations`,
     `/api/factions`, `/api/items`) that read from `data/` directly
   - SSE turn endpoint (`/api/stream`) that calls the engine, streams
     narrative tokens to the client, and dispatches the Fact-Extractor
     output through `engine.dispatch` to `fs-manager`
   - Session management endpoints (`/api/session/new`, `/api/session`)
     that read/write session state from `data/lore/core/sessions/`
   - Health check (`/healthz`)
   - Community pack load on startup (if implemented in this phase)
   - No ORM, no Django, no direct SQL
   - Sized at roughly 500–800 lines of Python + tests
   - Preserves the existing SSE response format (`{type: 'token', content}`,
     `{type: 'world_update', data}`, `[DONE]`) so the frontend does not
     have to change
   - Tracked in `docs/BACKLOG.md`

### Retirements

4. **Django backend.** `backend/sentinel/`, `backend/api/`, and
   `backend/manage.py` are removed in the same PR that lands the FastAPI
   replacement. The contents of `backend/requirements.txt` are rewritten
   to list the FastAPI stack instead of the Django stack (same filename,
   different dependencies). `scripts/check-structure.sh` and
   `folder_structure.json` updated accordingly.

5. **Express dev reference + Drizzle.** `artifacts/api-server/` and
   `lib/db/` are removed. These have been double-dead-code since PR #7
   and retire together. Workspace files (`pnpm-workspace.yaml`,
   `tsconfig.json`, `package.json`) updated to drop the workspace members.

6. **Postgres (Phase 2, deferred).** Not removed in Phase 1. Removed in a
   later ADR or BACKLOG item once Phase 1 proves stable and the cache
   layer is confirmed unnecessary.

### Documentation realignment

7. **`README.md` and `ARCHITECTURE.md`.** These are *not* rewritten by
   this ADR. Small forward-pointing callouts are added where the current
   prose contradicts the decision, directing the reader to this ADR. The
   full rewrite happens after Phase 1 ships, so the documents reflect
   actual running code instead of aspirational architecture.

8. **`CLAUDE.md`.** Same — small callout directing future sessions to this
   ADR where the current Architecture section references Django as the
   backend.

9. **`docs/BACKLOG.md`.** The existing High Priority item about the
   source-of-truth decision is marked resolved (pointer to this ADR). The
   Fact-Extractor and engine-wiring items are updated to reflect the
   concrete pinned shapes. New items are added for each piece of follow-up
   work listed above.

10. **`docs/QUICKSTART.md`.** Currently ends at "start the fs-manager MCP
    server and curl it to prove schema validation works." This is still
    accurate and becomes more so under Option B — the schema gate is the
    real gate, and the QUICKSTART is showing you how to use it. Minor
    updates may be needed to mention the new backend, deferred to the
    Phase 1 implementation PR.

11. **`docs/WORKSPACE.md` and `CHANGELOG.md`.** Pre-existing drift,
    already tracked in BACKLOG. Not touched by this ADR. Will be rewritten
    as part of the Phase 1 cleanup once the new backend is running.

---

## Alternatives considered and rejected

### Keep everything as-is and just add schema validation inside `dm_ai.py`

**Rejected** because it preserves none of the stated values beyond
catching obviously-malformed payloads. The schema gate exists to ensure
the *boundary* between the inference layer and the storage layer is
enforced. A validator called as a function inside the inference layer is
not a boundary — it's a check the inference layer can forget, skip,
bypass, or be prompt-injected around. The whole point of a separate MCP
server listening on a socket is that it enforces the schema from outside
the process that produced the payload.

### Move to data/ canonical but keep Django reading from it

**Rejected** as a stable end state, though it is considered briefly as a
transition state in Phase 1. Django's value is in its ORM, admin, forms,
and auth machinery — none of which are used by Project Sentinel's actual
endpoints. A Django app that reads JSON files and serves them through
`JsonResponse` is a very expensive way to import `json` and
`http.server`. FastAPI serves the same routes in a fraction of the
dependency surface, matches the async model already in use by every
other server-side component, and uses Pydantic models that mirror the
JSON schemas directly (no ORM-to-schema translation layer). The
consistency value alone justifies the swap.

### Build the new backend with plain Starlette / aiohttp / `http.server`

**Rejected** on the grounds that FastAPI is strictly a superset of
Starlette for this use case, and the project's existing MCP servers are
already on FastAPI. Adopting FastAPI for the backend means a developer who
learns one server's idioms can work on all of them. Going thinner would
save a small amount of dependency surface at the cost of fragmenting the
patterns across the repo.

### Rip out Postgres in the same PR as the backend rewrite

**Rejected** in favor of phasing. See "Phase 1 and not 'rip out Postgres
now'" in Rationale.

---

## References

- Project values: `README.md` § Core Principles, `ARCHITECTURE.md` §§ 1–5
- Existing code documented as being replaced: `backend/api/dm_ai.py`,
  `backend/api/models.py`, `backend/api/views.py`, `backend/sentinel/`,
  `artifacts/api-server/`, `lib/db/`
- Engine package scaffold (boundary contract): `engine/README.md` (PR #9)
- Schema contract being enforced at the gate:
  `schemas/apply_world_update.schema.json`
- MCP servers currently implementing the gate:
  `mcp-servers/fs-manager/server.py`, `mcp-servers/git-sync/server.py`
- The design conversation that produced this decision: 2026-04-13 session
  on `feat/engine-scaffold` → `docs/adr-0001-data-canonical` branch
- Relevant BACKLOG items (rewritten in the companion commit to this ADR):
  - "Build the Inference Node from scratch" — resolved
  - "Implement `engine/agents/fact_extractor.py`" — output shape now
    pinned
  - "Wire engine into Django / retire `backend/api/dm_ai.py`" — now means
    "replace Django with FastAPI"
  - "Delete `world-engine/` entirely" — unchanged
  - New: "`engine/dispatch/` HTTP module for MCP Bridge calls"
  - New: "FastAPI backend to replace Django"
  - New: "Retire `artifacts/api-server/` and `lib/db/`"
  - New: "Phase 2 — drop Postgres from the Docker stack"
  - New: "Rewrite `ARCHITECTURE.md` and `README.md` Core Loop narratives
    after Phase 1 ships"

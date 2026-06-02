# ADR 0002 — World identity & isolation (one player per world, concurrently)

**Status:** Proposed
**Date:** 2026-06-02
**Deciders:** Russell Pfister; Claude (design session 2026-06-02, prompted by "can this handle multiple users?" → goal: concurrent isolated worlds for public test users)
**Relates to:** ADR 0001 (`data/` is canonical); the "World Identity & Multi-Session" backlog item, whose three gaps this ADR resolves.

---

## Context

Sentinel is designed as **one player per world** — every player gets their own
isolated world. It is *not* designed as "one global world that only one player
may touch." But the implementation never built the isolation: today **all
sessions share one `data/state/core/` tree** (`entities/`, `locations/`,
`factions/`, `items/`, `world/state.json`), so two sessions overwrite each
other's world. Verified gaps as of this ADR:

1. **No world isolation.** Sessions are per-UUID (`sessions/<id>.json`), but the
   world *state* they read/write is global. Cross-session bleed is already a
   single-player bug (the "AR15 → Ray Gun" case); with concurrent users it
   becomes a data race.
2. **No concurrency control.** Zero locks in `backend/`, `engine/`, or
   `mcp-servers/`. Concurrent turns race on file writes *and* the single git
   index (git-sync does `git.Repo(REPO_ROOT)`).
3. **No `world_id`.** Nothing identifies or separates worlds; `world_seed` is
   dropped on the floor (backlog Gap 1).
4. **World data lives in the code repo.** `data/` is tracked in the project's
   own git repo, so per-turn `git-sync` commits land on the checked-out code
   branch (the `master`-pollution hazard noted in CLAUDE.md).

The goal that forces this decision: run **N concurrent, isolated worlds** so
each public test user gets their own, none seeing or corrupting another's.

## Decision drivers

- **Isolation is correctness, not nicety** — test users must not bleed into each
  other's worlds.
- **Concurrency safety** — two worlds advancing turns at once must not corrupt
  files or a shared git index.
- **Operational simplicity** — one deploy we can expose publicly, not a fleet to
  orchestrate (test scale: tens of worlds, low turn rate, short sessions).
- **Stay on the ADR-0001 model** — git-backed files remain canonical; no DB.
- **Don't preclude co-op multiplayer later** (vision), but don't build it now.

## Options considered

**Option A — Path-namespaced multiplex (one repo).** One backend process; world
data under `data/worlds/<world_id>/state/...` inside the existing project repo;
`world_id` in the request. *Cons:* every world commits to the one code repo →
the `master`-pollution hazard persists and a *global* commit lock is required
(serializes all worlds); a path refactor across engine/backend/fs-manager.

**Option B — Repo-per-world (recommended).** One backend process that, keyed by
`world_id` from the request, reads/writes that world's **own git repo** under a
data root *outside* the code repo (e.g. `~/sentinel-worlds/<world_id>/`). *Pros:*
hard isolation (a world can't touch another's tree); per-world git → no
cross-world index contention (only a per-world lock); and world data leaves the
code repo entirely → **the `master`-pollution hazard disappears by
construction.** Aligns with the backlog's stated intent ("one `data/` tree = one
world"). *Cons:* provision a fresh repo per world at creation; git-sync and the
`data/` readers must take a per-request world root rather than a fixed path.

**Option C — DB-per-world.** Rejected: reintroduces a database, contradicting
ADR 0001.

## Decision (proposed — ratify via this PR)

Adopt **Option B: repo-per-world**, one backend process routing by `world_id`.

1. **World root is per-request.** The fixed `data/state/core/...` paths become
   `<world_root>/state/core/...`, where `<world_root>` is resolved from the
   request's `world_id`. Worlds live under a configurable data root outside the
   code repo; each world root is its own git repo (git-sync operates on it).
2. **`world_id` + genesis.** A `world_id` (uuid4) is minted at world creation and
   written once to a `genesis` block in `world/state.json` (world_seed, presets,
   created_at), immutable thereafter — per the backlog's genesis spec.
3. **Routing.** The play URL carries the world (`/w/<world_id>`); API turn calls
   carry `world_id` (or resolve it from the session→world mapping). Creating a
   world mints the id and returns its URL; resuming = revisiting it.
4. **Concurrency.** A **per-world write lock** serializes a world's turn writes;
   because each world is its own repo, commits don't contend across worlds. No
   global bottleneck.
5. **Commit format.** `[sentinel] world=<id[:8]> session=<id[:8]> turn=N — <summary>`
   (backlog Gap 3), now in the *world's* repo.
6. **Lifecycle.** World create / reset / teardown operate on a single world root
   (`just reset-world` becomes world-scoped; teardown = remove the world root).

## Explicitly out of scope (downstream, not this ADR)

- **Auth, access-gating, rate-limiting, and public exposure** (Tailscale Funnel
  vs tunnel, invite codes, abuse/LLM-budget caps). These are required *before*
  public test users but are a separate decision — likely ADR 0003. Until then,
  this stays tailnet-only.
- **Co-op multiplayer** (multiple players in one shared world, turn coordination)
  — vision, not near-term.

## Consequences

**Positive:** true per-world isolation; clean per-world concurrency (no global
commit lock); the `master`-pollution hazard is eliminated (world data leaves the
code repo); aligns with ADR 0001 + the backlog's intended model; unblocks the
public-test-user goal once auth/exposure (ADR 0003) lands.

**Negative:** a path refactor — every hardcoded `data/state/core` /
`data/lore/core` reference in `engine/`, `backend/`, and the MCP servers must
take a world root; git-sync must target a per-request repo; world provisioning
(git init + baseline) is a new creation step. Migration: the existing single
shared tree becomes "world zero" or is reset.

**Neutral:** presets/lore that are meant to be *shared* across worlds
(`data/lore/core/presets/`) need a home that isn't per-world — either copied
into each world root at creation or read from a shared read-only path. The ADR
assumes a shared read-only preset/lore source + per-world mutable state.

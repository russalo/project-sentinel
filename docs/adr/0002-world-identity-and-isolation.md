# ADR 0002 — World identity & isolation (one player per world, concurrently)

**Status:** Accepted
**Date:** 2026-06-02
**Deciders:** Russell Pfister (ratified Option B, 2026-06-02); Claude (design session 2026-06-02, prompted by "can this handle multiple users?" → goal: concurrent isolated worlds for public test users)
**Supersedes:** — (no prior ADR)
**Implementation:** Landed. Slices 1–5 complete by 2026-06-04 (per-world routing end-to-end, provisioning at session-create, the tracer-soak gate, the `/w/<world_id>` frontend route, "my worlds" picker, hard-delete teardown, per-world cross-process write locking via `filelock`). Cutover armed 2026-06-07 (`SENTINEL_WORLDS_ROOT` set in `infrastructure/.env` on origin-core; gate-fronted topology live).

---

## Context

Sentinel is designed as **one player per world** — every player gets their own
isolated world. It is *not* "one global world that only one player may touch."
But the implementation never built the isolation: today **all sessions share one
`data/state/core/` tree** (`entities/`, `locations/`, `factions/`, `items/`,
`world/state.json`), so two sessions overwrite each other's world. Verified gaps
as of this ADR:

1. **No world isolation.** Sessions are per-UUID (`sessions/<id>.json`), but the
   world *state* they read/write is global. Cross-session bleed is already a
   single-player bug (the "AR15 → Ray Gun" case); with concurrent users it
   becomes a data race.
2. **No concurrency control.** Zero locks in `backend/`, `engine/`, or
   `mcp-servers/`. Concurrent turns race on file writes *and* the single git
   index (git-sync does `git.Repo(REPO_ROOT)`).
3. **No `world_id`.** Nothing identifies or separates worlds; `world_seed` is
   dropped on the floor (backlog Gap 1).
4. **World data lives in the code repo.** `data/` is tracked in the project's own
   git repo, so per-turn `git-sync` commits land on the checked-out code branch
   (the `master`-pollution hazard noted in CLAUDE.md).

The goal that forces the decision: run **N concurrent, isolated worlds** so each
public test user gets their own, none seeing or corrupting another's.

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
`world_id` in the request. *Cons:* every world commits to the one code repo → the
`master`-pollution hazard persists and a *global* commit lock is required
(serializes all worlds); a path refactor across engine/backend/fs-manager.

**Option B — Repo-per-world (chosen).** One backend process that, keyed by
`world_id` from the request, reads/writes that world's **own git repo** under a
data root *outside* the code repo (e.g. `~/sentinel-worlds/<world_id>/`). *Pros:*
hard isolation (a world can't touch another's tree); per-world git → no
cross-world index contention (only a per-world lock); world data leaves the code
repo entirely → **the `master`-pollution hazard disappears by construction.**
Aligns with the backlog's stated intent ("one `data/` tree = one world"). *Cons:*
provision a fresh repo per world at creation; git-sync and the `data/` readers
must take a per-request world root rather than a fixed path.

**Option C — DB-per-world.** Rejected: reintroduces a database, contradicting
ADR 0001.

## Decision

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
   because each world is its own repo, commits don't contend across worlds.
5. **Commit format.** `[sentinel] world=<id[:8]> session=<id[:8]> turn=N — <summary>`
   (backlog Gap 3), now in the *world's* repo.
6. **Lifecycle.** World create / reset / teardown operate on a single world root
   (`just reset-world` becomes world-scoped; teardown = remove the world root).

**Explicitly out of scope (→ follow-on ADR 0003):** auth, access-gating,
rate-limiting, and the public-exposure mechanism (Tailscale Funnel vs tunnel).
These are required *before* public test users but are a separate decision; until
then Sentinel stays tailnet-only. Co-op multiplayer (many players, one shared
world, turn coordination) is vision, not near-term.

## Rationale

**Why B over A.** Both isolate worlds and both need world-scoped routing + a
write lock, so the deciding factors are git topology and the pollution hazard. A
keeps every world's commits in the single code repo: that forces a *global*
commit lock (one world's commit blocks all others) and leaves the
`master`-pollution hazard intact — recording still dirties the code branch. B
gives each world its own repo, so commits are independent (per-world lock only,
no global bottleneck) and world data lives entirely outside the code repo, which
*eliminates* the hazard rather than working around it. At the cost of a one-time
`git init`+baseline per world — cheap at test scale — B is strictly better on
isolation and concurrency, and it matches the backlog's long-stated "one tree =
one world" intent. **Why not C:** a database contradicts ADR 0001's
canonical-files decision and buys nothing here.

## Consequences

> **Status note (added 2026-06-13):** Consequences and Implementation
> implications below are stated forward-looking from the 2026-06-02 ADR.
> All are now landed — see the **Implementation** field at the top of
> this ADR. The text is preserved as decision-record per ADR
> append-only convention.

**Positive:** true per-world isolation; clean per-world concurrency (no global
commit lock); the `master`-pollution hazard is eliminated (world data leaves the
code repo); aligns with ADR 0001 + the backlog's intended model; unblocks the
public-test-user goal once auth/exposure (ADR 0003) lands.

**Negative:** a path refactor — every hardcoded `data/state/core` /
`data/lore/core` reference in `engine/`, `backend/`, and the MCP servers must
take a world root; git-sync must target a per-request repo; world provisioning
(git init + baseline) is a new creation step. Migration: the existing single
shared tree becomes "world zero" or is reset.

**Neutral:** presets/lore meant to be *shared* across worlds
(`data/lore/core/presets/`, `schemas/`) need a home that isn't per-world — read
from a shared read-only path, or copied into each world root at creation.

## Implementation implications

- **`world_id` is a path component → validate it as a hard security boundary.**
  Never interpolate a raw `world_id` into a filesystem path. Resolve world roots
  only through a UUID-validated id, reusing the `_require_uuid` path-traversal
  guard already in `backend/state/sessions.py`; reject anything else before any
  path is built — in the backend route *and* in the MCP servers (which must not
  trust the backend blindly).
- **The write lock must be cross-process, not in-process.** The backend,
  fs-manager, and git-sync are separate processes, so an `asyncio`/`threading`
  lock won't serialize them. Use a filesystem lock per world root (a `.lock`
  file / `flock`) that all writers acquire, or funnel all writes for a world
  through a single serializing owner.
- **Split static/shared from per-world-mutable during the refactor.** Shared,
  read-only content (`data/lore/core/presets/`, core lore, `schemas/`) resolves
  to a fixed shared path (or is copied into the world root at creation); only
  mutable world state (`state/core/{entities,locations,factions,items}`,
  `world/state.json`, sessions, session lore logs) is per-world.
- **Path sites to refactor** (non-exhaustive): `engine/schema.py`
  (`_SCHEMA_PATH`), `backend/state/world_context.py` + `backend/state/sessions.py`
  (fixed core paths), `backend/datasets.py` / the training endpoints (session
  scan), the fs-manager write root, and git-sync's `REPO_ROOT` (→ per-request
  world repo).
- **Lifecycle work:** world provisioning (`git init` + baseline) at creation;
  world-scoped `just reset-world`; teardown removes the world root. Tracks the
  "World Identity & Multi-Session" and `just reset-world` items in
  `docs/BACKLOG.md`.
- **Then ADR 0003** (auth + access-gating + public exposure) must land before any
  public test user, plus the deferred systemd item so the services survive a
  reboot.

## References

- **ADR 0001** — `data/` is the canonical source of truth (this ADR keeps the
  git-backed-files model; only the topology changes to one repo per world).
- **`docs/BACKLOG.md`** — "World Identity & Multi-Session" (the three gaps this
  resolves) and the "Session boundary is not a world boundary" Critical
  smoke-test finding.
- **Source:** `backend/state/sessions.py` (`_require_uuid`, `Session`),
  `backend/state/world_context.py`, `mcp-servers/fs-manager/server.py`,
  `mcp-servers/git-sync/server.py` (`REPO_ROOT`), `engine/schema.py`.
- **Produced by:** the 2026-06-02 design conversation ("can this handle multiple
  users?") and PR #59.

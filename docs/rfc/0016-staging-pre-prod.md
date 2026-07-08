# RFC 0016 — Staging as true pre-prod (own backend + world store + mock-DM acceptance harness)

**Status:** Implemented
**Date:** 2026-07-04
**Author:** Russell Pfister
**Implements:** RFC-0015 § Out of Scope — a staging-own backend
**Supersedes:** —
**Superseded by:** —

---

## Context

RFC-0015 gave the alpha a dev→staging→prod *frontend* pipeline, but staging has
no own backend — `sentinel-staging.dev.russalo.com/alpha/api` proxies to prod's
`:8001`, so staging and production **share one backend and one world store**
(`~/sentinel-worlds`). Fallout observed 2026-07-04 on the first pipeline deploy: a
world created on staging landed in the prod store and showed in prod's world list;
prod worlds show on staging but load empty (the per-world session token is
origin-scoped `localStorage`, and staging has no basic_auth for the reauth-remint).
Neither is a bug — both are the shared-backend design. This RFC carves staging out
of prod and makes it a real pre-prod. (dev/local is already isolated.)

## Decisions (locked with Russell 2026-07-04)

1. **Staging backend runs the CANDIDATE**, not master — a true pre-prod that
   catches *backend* regressions before prod.
2. **Session-token gate OFF on staging** — tailnet-only membership is the access
   control; gate off ⇒ worlds open freely (no token, no reauth), fixing the
   "can't open a world on staging" symptom.
3. **Mock DM** (zero LLM cost) replaying a scripted sequence as the deterministic
   staging acceptance scenario (a full mechanics walkthrough ending in death).
4. Staging world store at **`~/sentinel-worlds-staging`**.

## Proposal

### A. Mock DM + the acceptance fixture (this PR — slice 1)
`SENTINEL_DM_MODE=mock` makes the backend inject a **fixture client** into the DM
agents (`engine.agents.dm`) in place of the live LLM. The engine is IO-pure, so
fixture loading + per-turn selection live in the backend (`backend/mock_dm.py`),
reusing the DM agents' existing injectable `client=` seam — no engine change.
- Fixture (`tests/fixtures/mock_dm_death_sequence.json`): the DM-authored
  death-by-combat sequence, reconciled to the real emit shape (friendly
  `<world_update>` block: top-level `world`/`characters`/`locations` +
  a top-level `check_request`) and the real two-round-trip cadence (a
  `check_request` turn, then its roll-resolve turn). Turn 0 = intro; 1..N =
  `/api/stream` responses in POST order. Walks create → skill check → combat to
  0 HP → unconscious → the 3-save death chain → dead.
- Selection: the backend picks the fixture turn by `next_turn_number` (turn 0 for
  the intro). Over-running the script raises → surfaces as the generic DM error.

### B. Staging trio (own store, alt ports) — later slice
| service | prod | staging | worlds root |
|---|---|---|---|
| backend | 8001 | 8101 | `~/sentinel-worlds-staging` |
| fs-manager | 8010 | 8110 | (same) |
| git-sync | 8012 | 8112 | (same) |

All set `SENTINEL_WORLDS_ROOT=~/sentinel-worlds-staging` (config-agreement within
the staging trio); `SENTINEL_SESSION_TOKEN_SECRET` unset (gate off). systemd units
`sentinel-{backend,fs-manager,git-sync}-staging` (mirror prod templates).

### C. Candidate code via a git worktree — later slice
Staging backend runs from a git worktree pinned to the candidate ref; prod runs
the main checkout at the released ref. `just stage-candidate <ref>` restarts the
staging trio on it. `just stage-smoke` drives the mock fixture (rolls and all) and
asserts the terminal death + mechanics checkpoints — the deploy gate.

### D. Edge (tailnet's lane) — later slice
Repoint `sentinel-staging.dev.russalo.com/alpha/api/*` → `:8101`.

## Open Questions
- [ ] Backend "promote" mechanism: fast-forward the prod checkout to `<ref>` +
      restart the prod trio, vs a released-ref pin? Keep minimal.
- [ ] Worktree location + lifecycle (per-candidate vs one reused, cleanup)?
- [ ] `stage-smoke` assertion granularity: terminal dead state only, or per-turn
      checkpoints too?

## Acceptance Criteria
- [x] `SENTINEL_DM_MODE=mock` injects a fixture client into the DM agents; the
      committed death fixture drives `/api/stream` end-to-end (mock narrative +
      `check_request` flow; turn selected by turn number). *(slice 1)*
- [x] Every fixture `world_update` survives the real `fact_extractor` with a
      schema-valid payload; the arc (create → 0 HP → unconscious → 3-save chain →
      dead) is test-guarded. *(slice 1)*
- [x] Staging trio (backend :8101 + fs-manager :8110 + git-sync :8112) on
      `<STAGING_WORLDS_ROOT>` — systemd unit templates + `just staging-*` recipes;
      config-agreement verified green in mock mode, a session lands in the staging
      store with prod untouched. Origin-core `enable --now` is the ops step. *(slice 2)*
- [x] `just wipe-staging-worlds` + `just staging-check` guard that staging root ≠
      prod root (both refuse a match). *(slice 2)*
- [x] `just stage-smoke` — ephemeral mock trio (free ports) + `scripts/stage_smoke.py`
      drives the fixture (failing death-save rolls) to a **verified death**
      (`status == "dead"` persisted), proving mock DM → fact_extractor → fs-manager
      dispatch → death_stakes end-to-end. `just stage-candidate <ref>` checks the
      staging worktree out at a candidate ref; the staging units run from it. *(slice 3)*
- [x] tailnet repoints `sentinel-staging.dev/alpha/api/*` + `/alpha/healthz` →
      :8101 (done 2026-07-08, block-scoped, invariant held). *(bring-up)*
- [x] A staging world appears ONLY in staging's `/api/worlds`, not prod's —
      verified on the live trio (session on :8101 → staging store; prod untouched
      5→5) and at the edge (`/api/worlds` = staging, `POST edge == :8101`). *(bring-up)*

**Bring-up note (2026-07-08):** the staging backend runs from the worktree
(WorkingDirectory), which lacks the gitignored `infrastructure/.env`.
`backend/config.py` resolves `ENV_PATH` relative to its own file location
(`Path(__file__)…` = the worktree root), so it looked for `<worktree>/infrastructure/.env`
and raised when missing. systemd's `EnvironmentFile=` already supplies the env, so
the fix is `SENTINEL_SKIP_ENV_CHECK=1` in `.env.staging` (now in the committed
`.env.staging.example`). **RFC-0016 COMPLETE.**

## Out of Scope
- CI-driven staging deploys.
- Per-tester world isolation (accounts / open-signup — ADR 0003 vision).
- Touching prod's stack beyond the backend-promote restart (purely additive trio).

## Cross-links
- Related RFCs: RFC-0015 (the frontend pipeline this extends)
- Related ADRs: ADR 0002 (world identity/isolation), ADR 0003 (access gating)
- PRs: #NN (slice 1 — mock DM + fixture; filled in as it lands)
- Memory: project_minimum_viable_structure_loop (the repeatable smoke harness this
  realizes), project_prod_topology_closed_alpha, project_cutover_restart_recipe

# RFC 0015 — Alpha deploy pipeline (dev → staging → production)

**Status:** Accepted
**Date:** 2026-07-03
**Author:** Russell Pfister
**Implements:** Alpha deploy: staging-dir + atomic-symlink-swap so a stray build can't hit prod
**Supersedes:** —
**Superseded by:** —

---

## Context

The closed alpha has no staging and no separation between "build" and "deploy."
origin-core's Caddy roots `/alpha/*` **directly** at the code-repo build output
dir `apps/sentinel-ui/dist`, so `pnpm --filter @sentinel/ui build:alpha`
overwrites the live-served files in place. There is no verification step between
producing a bundle and serving it, and no rollback.

This has caused real outages: on 2026-07-03 a plain `pnpm build` (base `/`, not
`build:alpha`) run on a feature branch during RFC-0014 verification clobbered the
live-served `dist/` → blank alpha, recovered only by rebuilding `build:alpha` from
master. The class of bug — wrong mode or wrong branch reaching prod because the
build output *is* the live dir — is structural, not a one-off mistake.

The public marketing site (`apps/sentinel-site`) already solved this with a
versioned-artifact + atomic-symlink model (tarball → `/srv/handoff/` → tailnet's
atomic swap). This RFC brings the gated alpha up to that model and adds a staging
verification step. Slice 1 is **frontend-only** (the deploy incidents are all
frontend build-in-place); the backend's deploy pipeline is out of scope.

Cross-lane with tailnet Claude, who owns the edge: decisions were agreed
2026-07-03 (serve-tree path, staging host, the two-root repoint).

---

## Proposal

### Serve tree (sentinel-owned, outside the code repo)

`SENTINEL_ALPHA_SERVE_ROOT`, default `/srv/serve/sentinel-alpha` (russellp-owned
on origin-core, provisioned by tailnet):

```
/srv/serve/sentinel-alpha/
  releases/<git-short-sha>/   each = one `build:alpha` output, immutable
  current  -> releases/<sha>  what production serves
  staging  -> releases/<sha>  what the staging URL serves (the candidate)
  .previous                   short-sha path of the prior `current` (for rollback)
```

The seed release (the pre-pipeline live bytes, exact build-sha unknown) carries a
dated label `releases/live-seed-YYYYMMDD`; every pipeline-built release is
`<git-short-sha>`.

### Edge (tailnet's lane)

- Caddy roots `/alpha/*` at `<SERVE_ROOT>/current` (a symlink) instead of
  `apps/sentinel-ui/dist`. **Both** origin-core `/alpha` roots repoint — the
  public apex block (`sentinel.russalo.com/alpha/*`) and the tailnet dev block
  (`sentinel.dev.russalo.com/alpha/*`).
- A tailnet-only staging host `sentinel-staging.dev.russalo.com/alpha/*` serves
  `<SERVE_ROOT>/staging`, mirroring prod's shape: `/alpha/api/* → :8001` with the
  same `/alpha` strip, no basic_auth (tailnet ACL already gates it). Because
  `VITE_API_URL=/alpha/api` is a same-origin **relative** path, the same build
  bytes serve correctly on both hosts — staging is byte-identical to what promotes.

### Pipeline (`justfile` recipes, deploy-host / origin-core)

- `build-alpha-release` — refuses off `master` or on a dirty tree; builds
  `vite build --mode alpha --outDir <SERVE_ROOT>/releases/<sha>` (byte-faithful to
  `build:alpha`, never writes `dist/`); guards that the built `index.html` is
  `/alpha/`-based; repoints `staging`. Does **not** promote.
- `promote-alpha` — atomically repoints `current` at the `staging` release
  (`rename(2)`); records `.previous`.
- `rollback-alpha` — repoints `current` at `.previous` (reversible).
- `alpha-status` — shows current / staging / previous + releases.
- `prune-alpha-releases keep=5` — deletes old releases, never current/staging.

Deploy = `build-alpha-release` → verify at the staging URL → `promote-alpha`.

### Template + docs

- `infrastructure/caddy/Caddyfile.example` — `root` becomes `<ALPHA_SERVE_ROOT>/current`;
  a SERVE MODEL note documents the pipeline + the two-root repoint. The ADR 0003
  isolation invariants (only `:8001` proxied, gate, exclusions) are unchanged
  (`tests/test_caddy_invariant.py` stays green).
- `docs/WORKSPACE.md` § "Alpha deployment (staging → production)" — the runbook.

---

## Open Questions

- [x] Serve-tree path — resolved: `/srv/serve/sentinel-alpha/` (russellp-owned;
      distinct from root-owned `/srv/www` and drop-only `/srv/handoff`).
- [x] Staging host — resolved: dedicated tailnet-only `sentinel-staging.dev.russalo.com/alpha/*`
      (wildcard-covered, no new DNS/cert; `.dev` prod host already serves `/alpha/`).
- [x] basic_auth on staging — resolved: skip (tailnet ACL gates it; the bugs staging
      catches are basic_auth-independent for a static SPA).

---

## Acceptance Criteria

- [x] `justfile` recipes: build-alpha-release, promote-alpha, rollback-alpha,
      alpha-status, prune-alpha-releases. Guards (master-only, dirty-tree,
      `/alpha/`-based index) enforced.
- [x] promote/rollback verified as atomic symlink swaps against the real seeded tree.
- [x] `Caddyfile.example` root → `current`; invariant test green.
- [x] WORKSPACE.md runbook; BACKLOG item dropped.
- [ ] **Operational cutover** (tailnet window, Option A): repoint both `/alpha`
      roots → `current` (byte-identical no-op), wire the staging host. First
      pipeline use ships RFC-0014 + #175 via `build-alpha-release` → verify → promote.

---

## Out of Scope

- Backend dev→staging→prod pipeline + frontend/backend version-coupling automation
  (a follow-on slice; the backend stays a discrete `systemctl restart`).
- A staging-own backend (staging runs the candidate frontend against the prod
  `:8001` this slice).
- CI-driven auto-deploy — promotion stays a deliberate human step in a patch window.
- The public `apps/sentinel-site` deploy (already versioned via the handoff tarball).

---

## Cross-links

- Related ADRs: ADR 0003 (access gating / public exposure — the edge invariant)
- Related RFCs: —
- BACKLOG items: "Alpha deploy: staging-dir + atomic-symlink-swap" (dropped on merge)
- PRs: #NN (filled in as it lands)
- Memory: `project_alpha_deploy_is_build_in_place`, `project_tailnet_claude_owns_public_edge`,
  `project_gate_fronted_topology`, `reference_openart_animated_tile_recipe`

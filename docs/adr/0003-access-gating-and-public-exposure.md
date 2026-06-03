# ADR 0003 — Access gating & public exposure (closed-beta test users)

**Status:** Accepted
**Date:** 2026-06-03
**Deciders:** Russell Pfister (ratified the auth model, exposure mechanism, and
audience, 2026-06-03); Claude (design session 2026-06-03, prompted by "draft
adr 0003" to satisfy the public-test-user prerequisite ADR 0002 deferred)
**Supersedes:** — (no prior ADR)

---

## Context

[ADR 0002](0002-world-identity-and-isolation.md) made **N concurrent, isolated
worlds** possible (repo-per-world, routed by `world_id`) and *explicitly deferred*
"auth, access-gating, rate-limiting, and the public-exposure mechanism" to this
ADR, noting they are **required before any public test user** and that Sentinel
stays tailnet-only until they land. This ADR makes those decisions for the
**closed-beta** phase: exposing the mockup URLs to a known set of invited
testers, not the open internet.

State as of this ADR:

1. **No auth, no rate-limiting.** `POST /api/session/new` is anonymous; it mints
   a `session_id` + `world_id` (both uuid4) and returns them. The de-facto model
   is **capability-by-UUID** — possessing a `session_id` lets you drive that
   session (`/api/stream` reads the session by id and derives its `world_id`).
   UUIDs are unguessable, so today the URL *is* the secret.
2. **CORS only.** `backend/main.py` adds `CORSMiddleware` (allowlist, or
   allow-all in debug). That is the entire access surface.
3. **Caddy already fronts the app.** On `origin-core`, Caddy serves
   `sentinel.dev.russalo.com`: `/api/*` + `/healthz` reverse-proxy to the backend
   on `127.0.0.1:8001`; everything else is static from `apps/sentinel-ui/dist/`.
   The MCP servers (`fs-manager :8010`, `git-sync :8012`) are **not** on the
   public edge.
4. **git-sync `rollback_to`/`list_snapshots` are world-routable with no auth**
   (BACKLOG). Today this is contained purely by network topology — those
   endpoints are only reachable on localhost/tailnet, never the public edge.

**The risk at test scale is cost and abuse, not data confidentiality.** Worlds
are throwaway test data; nobody's secrets are in them. But every turn is a
paid/free-tier LLM call, so an open world-creation + turn surface is a
budget-drain and abuse vector. That — plus keeping the write layer (MCP servers)
unreachable — is what this ADR must contain.

## Decision drivers

- **Cost/abuse containment** — only invited people should be able to spend LLM
  calls; a leaked link or a curious bot must not run up the bill.
- **Operational simplicity** (carried from ADR 0002) — one deploy, one rotatable
  secret; **no user database, no external identity provider** for tens of
  testers.
- **Reuse the existing edge** — Caddy already terminates TLS and proxies; the
  gate and rate-limit belong there, not bolted onto every backend route.
- **Keep the write layer off the public internet** — the MCP servers are
  internal; the simplest correct control is "not reachable from outside."
- **Don't preclude real accounts later** (vision) — but don't build them now.

## Options considered

**Access / auth model**

- **A — Capability URLs only (no gate).** Rely purely on UUID unguessability.
  *Rejected:* world creation stays open → the LLM-cost/abuse vector remains; no
  revocation.
- **B — Capability URLs + shared invite gate (chosen).** A single shared invite
  secret gates all of `/api/*` so only invited testers reach the backend; within
  the gate, `/w/<world_id>` + a per-world session token authorize turns. No
  accounts. *Pros:* closes the cost vector, one rotatable secret = simple revoke,
  no user store. *Cons:* the shared secret is coarse (no per-user revoke /
  accounting — rotating logs everyone out).
- **C — Per-user accounts (outsourced IdP / JWT).** Clerk/Auth0/Supabase logins,
  per-user world ownership. *Deferred to vision:* over-built for tens of testers;
  reintroduces an external dependency + secrets + a user↔world store.
- **D — Self-hosted passwords.** *Rejected:* password management is exactly what
  the backlog's "Auth strategy decision" wants to avoid; reintroduces a user
  store, against the ADR-0001 no-DB spirit.

**Public-exposure mechanism**

- **Caddy + public DNS + TLS (chosen).** Already serving `sentinel.dev.russalo.com`;
  the edge owns TLS, the gate, rate-limiting, static, and the proxy in one place.
  *Con:* exposes origin-core's public IP.
- **Tailscale Funnel.** *Rejected for now:* ties the public surface to Tailscale,
  has port/bandwidth limits, and forces the gate/rate-limit into the backend
  rather than the edge.
- **Cloudflare tunnel.** *Rejected for now:* hides the origin IP and adds a WAF,
  but introduces a Cloudflare dependency and duplicates what Caddy already does;
  revisit only if exposing origin-core's IP becomes a problem.

## Decision

Adopt **Option B (capability URLs + shared invite gate)** behind the **existing
Caddy edge**, sized for a **closed beta of invited testers**. Concretely:

1. **Edge access gate (Caddy).** A single shared invite secret gates all of
   `/api/*` and the app so only invited testers reach the backend or spend LLM
   calls — Caddy `basic_auth` or an invite-code/header check at the edge.
   `/healthz` stays open for monitoring. **Revoke everyone by rotating the
   secret.** The secret lives outside the repo (chezmoi/`.env` on origin-core),
   never committed.
2. **Per-world session token.** World creation mints, alongside `world_id`, a
   per-world **session token** returned to the client. Turn and stream calls must
   present it; the backend verifies **token ↔ world_id** before dispatching.
   Recommended form: a **signed stateless token** (HMAC of `world_id` + expiry,
   key in env) so there is no session store to maintain (fits the no-DB model).
   This makes the URL no longer the sole secret, lets tokens expire, and closes
   the "anyone with a `world_id` can drive it" gap.

   **The token must be stored per-world, never in a single shared cookie.** ADR
   0002 lets one player run *several* concurrent isolated worlds on the same
   origin; a lone `session_token` cookie would be clobbered when a second world
   opens, logging the player out of the first. Two acceptable deliveries: (a) a
   **client-held token sent as a per-request header** (e.g. `X-Sentinel-World-Token`),
   which the SPA keeps keyed by `world_id` — cleanest for the multi-world SPA; or
   (b) a **per-world-named** `HttpOnly`, `Secure`, `SameSite=Lax` cookie (e.g.
   `sw_<world_id[:8]>`) so concurrent worlds don't collide. (a) is preferred for
   the multi-world case; (b) trades cookie bloat for `HttpOnly` XSS-resistance —
   a minor concern given throwaway worlds and a cost-not-confidentiality threat
   model. A single shared cookie is **not** acceptable.
3. **MCP servers stay network-isolated.** `fs-manager :8010` and `git-sync :8012`
   are **never** exposed publicly — only the backend's `/api` is, via Caddy. This
   is the access-control answer for the write layer and resolves the git-sync
   `rollback_to`/`list_snapshots` "no auth" gap by topology. Make it an explicit,
   tested invariant: the servers bind to `127.0.0.1`/tailnet only, and Caddy must
   never proxy `:8010`/`:8012`.
4. **Rate-limiting (lenient, closed-beta backstop).** Per-IP limit on world
   creation (`POST /api/session/new`) and per-world limit on turns
   (`POST /api/stream`), plus a **global daily LLM-call ceiling** as a circuit
   breaker (env-configurable; refuse new turns past it). Tuned as a backstop
   against accidents and a leaked link — not adversaries, since the audience is
   invited.
5. **TLS + public surface via Caddy** (already in place): Let's Encrypt;
   `/api/*` + `/healthz` → backend; static → `dist/`. Exposing origin-core's IP
   is acceptable for a closed beta; revisit a Cloudflare tunnel only if it
   becomes a problem.
6. **systemd units.** Run Caddy, the backend (`.venv/bin/uvicorn`), fs-manager,
   and git-sync as systemd services (`WantedBy=multi-user.target`) so they
   survive a reboot — the deferred operational item (the post-reboot incident
   showed services don't currently auto-start).

### Out of scope — vision, not near-term

Per the repo's near-term/vision split, **everything above is the near-term
target**; the following are explicitly *not* built now and are the natural next
step when Sentinel graduates from closed beta to open signup:

- Per-user accounts & login (outsourced IdP / JWT), per-user world ownership and
  dashboards.
- Granular per-user rate tiers; CAPTCHA / hostile-traffic hardening for a
  truly-open audience.
- Co-op multiplayer auth (many players, one shared world — already vision in
  ADR 0002).

The capability + gate model is **forward-compatible**: when real accounts land, a
user simply *owns* capability tokens, so the world layer doesn't change.

## Rationale

**Why B over C.** At tens of testers, accounts buy revocation and accounting we
don't need yet, at the cost of an external dependency, more secrets, and a
user↔world store — directly against the operational-simplicity driver carried
from ADR 0002. The shared gate delivers the actual requirement ("only invited
people") with one rotatable secret, and the per-world token gives per-world
isolation without per-user identity. When real accounts are warranted, B's tokens
become things an account owns — no rework of the world layer.

**Why the gate at the edge, not in the backend.** Unauthenticated traffic should
never reach the LLM-spending code. Terminating it at Caddy is cheaper and keeps
the cost vector closed even if a future backend route ships without its own auth.
Caddy already terminates TLS, so it is the natural choke point.

**Why network-isolate the MCP servers rather than auth them.** They are internal
services; the simplest correct control is "unreachable from the internet." ADR
0002 already keeps them behind the backend. Endpoint auth on git-sync would be
defense-in-depth, but the topology already provides the boundary — so we make the
boundary explicit and tested rather than adding an auth layer to internal RPC.

**Why keep Caddy over Funnel/tunnel.** It is already serving the site and is the
single place that can host TLS + gate + rate-limit + static + proxy. Funnel moves
the gate into the backend and constrains bandwidth; a Cloudflare tunnel adds a
dependency to hide an IP we don't need to hide for a closed beta.

## Consequences

**Positive:** only invited testers can spend LLM budget; per-world tokens close
the world-routable gap and make the URL no longer the sole authorizer; the MCP
write layer is provably off the public edge; one rotatable secret = simple
revoke; services survive reboot; no user DB and no external IdP. Unblocks the
ADR 0002 public-test-user goal.

**Negative:** the shared secret is coarse — no per-user revoke or accounting, and
rotating it logs everyone out; capability cookies need correct flags
(`HttpOnly`/`Secure`/`SameSite`) and an expiry policy; the gate, token check, and
rate-limit are new code/config paths to test; systemd units are Linux-specific
(fine for origin-core, but the recipes must keep the cross-OS `just start` path
for macOS/Windows dev).

**Neutral:** the existing anonymous flow keeps working on the tailnet (the gate
only bites at the public edge); `world_id` stays in the URL for shareable resume,
but is no longer the sole secret.

## Implementation implications

- **Edge gate (Caddy):** add a `basic_auth` block (the stock Caddy v2 directive)
  or a `@gate` matcher checking an invite header/cookie on `/api/*` and the app;
  exempt `/healthz`. Store the secret in chezmoi/`.env` on origin-core; never
  commit it.
- **Session token:** mint in `backend/routes/session.py` alongside `world_id`;
  return it and set the cookie. Add a FastAPI dependency used by `stream.py` (and
  any world-scoped route) that verifies **token ↔ world_id** (reuse
  `_require_uuid` for the id), returning 401/403 on mismatch. Use a **signed
  stateless token** (HMAC over `world_id` + expiry, key from env) to avoid a
  session store.
- **Rate-limit:** implement in the **backend** — per-IP token-bucket on
  `/api/session/new`, per-world bucket on `/api/stream` (single process →
  in-memory is fine at test scale), plus a global daily LLM-call counter (env
  ceiling) that refuses new turns when exceeded. Note: `rate_limit` is **not** a
  stock Caddy directive — it's the third-party `caddy-ratelimit` plugin, which
  needs a custom `xcaddy` build. So the backend limiter is the default, not a
  Caddy-edge rate-limit, to keep the stock Caddy edge.
- **MCP isolation invariant:** assert fs-manager/git-sync bind to
  `127.0.0.1`/tailnet only (not `0.0.0.0`); add a health/test check; document that
  Caddy must never proxy `:8010`/`:8012`.
- **systemd:** units for `caddy`, `sentinel-backend` (`.venv/bin/uvicorn …`),
  `sentinel-fs-manager`, `sentinel-git-sync`; document in `docs/WORKSPACE.md` (or
  a new ops note). Cross-OS caveat: systemd is Linux-only — macOS/Windows dev
  keeps using `just start`.
- **Sequencing:** this pairs with the ADR 0002 **Slice 3 cutover** (per-world
  routing). The gate/token/rate-limit can land before or alongside it; *both* the
  Slice 3 isolation work and this access layer are prerequisites before inviting
  testers.

## References

- **ADR 0001** — canonical git-backed files, no DB (informs "no user store").
- **ADR 0002** — world identity & isolation; this ADR is its explicitly-deferred
  follow-on (§ "Explicitly out of scope → ADR 0003").
- **`docs/BACKLOG.md`** — "Auth strategy decision (future)" (the two paths this
  ADR chooses between), the git-sync `rollback_to`/`list_snapshots` no-auth item,
  and the deferred systemd item.
- **Source:** `backend/main.py` (CORS), `backend/routes/session.py` +
  `backend/routes/stream.py` (anonymous mint + turn flow),
  `backend/state/sessions.py` (`_require_uuid`), `docs/WORKSPACE.md` (Caddy /
  exposure), `apps/sentinel-ui/.env.production` (`VITE_API_URL`).
- **Produced by:** the 2026-06-03 design conversation ("draft adr 0003"); auth
  model, exposure mechanism, and closed-beta audience ratified by the user.

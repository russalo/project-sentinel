# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Agent Instructions — Project Sentinel

This file contains standing instructions for AI agents (Claude Code and others) working
in this repository. Read this before planning or implementing anything.

---

## Backlog Maintenance

The file `docs/BACKLOG.md` is the single source of truth for work that was discovered,
deferred, or left incomplete. You are required to keep it current.

**During a coding session, append to `docs/BACKLOG.md` when you:**
- Discover a bug, inconsistency, or technical debt that is out of scope for the current task
- Identify something that should be done soon but was not part of your planning
- Leave a task incomplete because it requires more information or a separate planning session
- Notice that documentation is out of sync with the current state of the code

**At the end of a session, remove from `docs/BACKLOG.md` when:**
- An item was fully resolved during the session
- An item is no longer relevant due to a direction change

**Format for new entries:**
```
- [ ] Short description of the item
      _Discovered: YYYY-MM-DD | Context: brief note on where/why this surfaced_
```

Add items under the most appropriate existing section. If no section fits, add one.
Never leave `docs/BACKLOG.md` in a state where completed work is still listed as pending.

---

## Explicit Approval Required Before Implementation

**You must not create, edit, or delete any file until the user has explicitly approved
a plan in the current session.**

This rule has no exceptions. "The plan seemed clear" is not an exception. "The user
approved something similar before" is not an exception. "The task is small" is not
an exception.

**Allowed without approval:**
- Reading files, exploring the codebase, running read-only commands
- Writing or updating the plan file at `~/.claude/plans/`
- Asking clarifying questions

**Not allowed until the user says to proceed:**
- Creating new files
- Editing existing files
- Deleting files
- Running commands that modify state (git commits, installs, etc.)

If you have written a plan and are ready to implement, present it and stop. Wait for
the user to explicitly say to proceed — words like "go ahead", "do it", "looks good",
or equivalent. An acknowledgment that you answered a question correctly ("ok", "that
makes sense") is **not** approval to implement.

If you catch yourself about to write a file without approval, stop and ask.

---



You are expected to think critically, not just execute. Before implementing:

- If a directive is ambiguous, ask a clarifying question rather than assuming
- If you believe the approach has a meaningful tradeoff, name it explicitly
- If a requested tool, pattern, or dependency introduces lock-in or complexity that
  may not be worth the benefit, say so with your reasoning
- If something you were asked to do turns out to be more complex than expected,
  stop, surface the complexity, and propose that it go to the backlog rather than
  delivering a partial or risky implementation

Healthy critique is part of the job. Silent compliance that ships a wrong answer is not.

---

## Branching and Merging

The default branch is `master`. Never push to `master` directly.

**Session lanes (trial since 2026-08-17).** The repo may be worked by an
Orchestrator session (`/srv/projects/project-sentinel`, the only tree that owns
`master`) plus lane sessions in their own worktrees (`sentinel-be`, `sentinel-fe`,
`sentinel-play`). If your cwd is a `/srv/projects/sentinel-*` worktree, you are a
lane: read `docs/SESSION_LANES.md` before your first action — you never touch
`master`, never deploy, never relay outward, and (engineering lanes) never play
against a stack without `SENTINEL_WORLDS_ROOT`.

Every unit of work gets its own branch off fresh master, named after
the kind of change it is (lane sessions branch the same way but never check
out `master`: `git fetch origin && git checkout -b <prefix>/<name> origin/master`,
and rebase onto `origin/master` — the `git checkout master && git pull` step
below is Orchestrator-only):

- `feat/<short-description>` — new feature or capability
- `fix/<short-description>` — bug fix or regression
- `chore/<short-description>` — cleanup, deletion, refactor with no
  behavior change
- `docs/<short-description>` — documentation-only change
- `ci/<short-description>` — CI workflow or tooling change

Workflow for each unit of work:

1. `git checkout master && git pull --ff-only` (Orchestrator / single-session only; lanes: `git fetch origin` and branch from `origin/master`)
2. `git checkout -b <prefix>/<short-description>`
3. Make the changes and commit them with DCO sign-off
   (`git commit -s`). Multiple commits are fine; they get squashed
   on merge anyway. `CONTRIBUTING.md` § "DCO Sign-off (Required)"
   is the canonical rule — every commit needs `Signed-off-by:`.
4. Push with `git push -u origin <branch>`
5. Open a PR with `gh pr create` — title + body formatted to match
   recent PRs on this repo
6. Wait for CI; address review-bot comments inline as small followup
   commits on the same branch
7. Squash-merge with `gh pr merge <N> --squash --delete-branch` once
   CI is green and comments are addressed
8. Run `just end-session` before stopping at equilibrium — it
   re-checks the backlog and structure so drift from the PR is
   caught before the session closes. Then stop; don't chain into
   the next unit of work without checking in with the user first.

Multiple logically-separate units of work should go to separate PRs
— but "logically separate" is judged by the user's "solo repo, bigger
swaths OK" preference: a coherent multi-commit sweep is one PR, not
six. Splitting into smaller PRs is only worth it when the split makes
the diff more legible or lets part of the work ship while another
part waits for review.

`tomorrow prep` or `end of day` may involve closing loose ends on
multiple branches; those are the exceptions where multiple PRs
land back-to-back.

---

## Reviewing changes (decorrelated swarm)

For anything cross-cutting (multi-subsystem, public-facing, concurrency),
run a **decorrelated review swarm** — reviewers that fail *differently*, so
each catches what the author (you) and the others miss:

1. **`/code-review master...HEAD`** (in-house) — best at sibling-path
   completeness ("hardened A, missed B/C") and logic. (Default branch is
   `master`; adjust the base if you branched from elsewhere.)
2. **Cross-model (Gemini)** — invoke the `gemini` CLI read-only (`--approval-mode
   plan --skip-trust`) with the diff + a falsify prompt. It reads `GEMINI.md` at
   the repo root for auditor instructions + the hunt list. Best at attacking
   premises a same-model reviewer inherited. Chunk by subsystem; for a sliced
   change, add one **integration pass aimed at the seam** where slices meet.
   *(On origin-core, a ready wrapper — `gem.sh`, flash; fall back from pro on
   "Invalid stream" — lives in the sibling File Observer project at
   `/srv/projects/pkplab/scanner/scratch/review/`; it is external to this repo.)*
   For a **whole-codebase** read (not a diff), Gemini's native review extensions
   (`/code-review`, `/maestro:security-audit` — a 39-agent fan-out) are
   *tool-using*, so they require `--approval-mode yolo` — the read-only `plan`
   mode above is for the inline-diff prompts and denies the extensions' git/skill/
   subagent tools (not a contradiction; different jobs). On origin-core a ready
   wrapper, `gem-review.sh` (yolo + the same key handling), sits beside `gem.sh`
   in that **same external scanner project** (not in this repo); the portable
   form is `gemini --skip-trust --approval-mode yolo -p "/maestro:security-audit …"`
   with the extensions installed. Because yolo can write, run it on an **isolated
   `/tmp` copy** of the code dirs (exclude `data/` + secrets), copy this repo's
   `GEMINI.md` into the workspace root for the hunt list, **scope per-subsystem**,
   and throttle (`MAESTRO_MAX_CONCURRENT=3`) or flash 429s. **A Gemini-native
   swarm is still ~1 vote** (same model family) — coverage, not independent
   confirmation; it stays one leg, and every finding still gets the triage below.
3. **PR bots** (Codex / Gemini Code Assist / Copilot) — open a PR. Best at
   doc/code drift after reworks.

Disciplines (more important than the tools): **falsify-first**; treat tests/
corpus as **biased** (construct the input they omit); **triage = verification**
(repro a finding in ~10 lines → real or dropped; act on a reproduction, never on
a tag — bots over-tag and re-flag fixed issues); **convergence across layers =
strongest real-bug signal**; **re-run the full suite + a real-flow check after
every fix round**, gated (cheap suite every round; expensive check at round
boundaries and mandatory before merge — never skipped). Per-PR review + a final
integration pass for sliced features.

### Red-teaming a security boundary (construct-and-run)

Code-reading review (the legs above) finds logic flaws; it does **not** prove a
boundary holds. For access/isolation/auth work, add a **construct-and-run
red-team**: author a `Workflow` script that fans out one agent per attack
surface (cross-tenant isolation, token forgery, path-traversal via id, the MCP
write-firewall, rate-limit/ceiling bypass, schema-gate/protected-field bypass,
malformed-LLM-output, SSE auth), each of which **constructs AND fires a real
hostile request**, then a verify stage that **independently reproduces** each
claimed break. Two non-negotiables (learned 2026-06-04):

- **Attack a DISPOSABLE test instance, never prod** — stand up an armed stack on
  alt ports + a temp `SENTINEL_WORLDS_ROOT` with throwaway worlds (the
  cutover-verify recipe), point the swarm at it, tear it down after. yolo/attacks
  can write.
- **Ground every finding** — the verify stage pre-grounds (it ran the attack),
  but re-check each CONFIRMED break against real source before it counts;
  reachability matters (a loopback-only sink is network-isolated, but the same
  logic may be reachable via untrusted LLM output on the engine→fs-manager path).

This is leg 1's *attack* variant (Claude-side, many perspectives, one model) and
complements the Gemini code-reading leg — for a boundary you want **both**.
Triage docs live in gitignored `scratch/review/` (e.g. `redteam-<date>-<area>.md`).
The first run (2026-06-04) found the happy-path hardening was incomplete: ungated
`/api/sessions*`, an `X-Forwarded-For`-spoofable rate-limit key, and
protected-field/schema-gate bypasses in fs-manager.

### Failure patterns this codebase exhibits (hunt these first)

Seeded from real bugs; update each release. The cross-model auditor's copy lives
in `GEMINI.md`.

- **Inter-world / cross-boundary state bleed** — state/context/RNG/transcript
  leaking across worlds or sessions (shared mutable globals, a fixed path not
  scoped by `world_id`, a cache keyed without the world). This is the
  cross-session contamination that motivated ADR 0002, generalized to the
  multi-tenancy boundary. *Prove it deterministically with a tracer soak — stub
  the DM with a per-world token and assert no cross-world leak; never against a
  live LLM. The harness now exists at `tests/test_world_isolation_tracer_soak.py`
  (CI-gated) — extend it for new boundaries rather than rebuilding.*
- **Sibling-path incompleteness** — a fix on path A while siblings B/C keep the
  bug (e.g. the `list_sessions`→`get_session` canonical-id miss).
- **Doc/code drift after reworks** — comments/docs/ADRs describing a superseded
  design (engine "scaffolding," Tailwind v4, Express/Django in CONTRIBUTING).
- **Schema-gate bypass** — a write path reaching fs-manager without
  `apply_world_update.schema.json` validation, or treating a rejection as fatal
  instead of feeding it back to the DM.
- **git-sync committing to the checked-out branch** — the `master`-pollution
  hazard during play/recording (only while `SENTINEL_WORLDS_ROOT` is unset; once
  set, per-turn commits go to each world's own repo outside the code repo).
- **Squash-merge captures gameplay state from a feature branch** — when
  gameplay happens *on the feature branch* during PR review (because
  `SENTINEL_WORLDS_ROOT` is unset and per-turn writes are committing to
  HEAD), the squash-merge picks up the gameplay's data files alongside
  the intended code changes. Those files land permanently on master and
  can't be reset away (PR #108 brought in 5 such orphan files; cleanup
  needed PR #110). Two preventatives, in order of preference: (a) keep
  `SENTINEL_WORLDS_ROOT` armed wherever you do PR development (so
  gameplay never touches the code repo); (b) check `git log` for any
  `[sentinel] world=… session=… turn=…` commits on the feature branch
  *before* opening a PR — those are the early-warning signal that
  gameplay data is about to land on master.
- **Malformed-LLM-output intolerance** — non-`dict` `world_update`, non-`list`
  collections.
- **Path traversal via id interpolation** — `session_id`/`world_id` as path
  components; UUID-validate (`_require_uuid`) before building any path, in the
  backend AND the MCP servers.
- **Cross-process locking** — in-process locks don't serialize backend /
  fs-manager / git-sync. *Per-world cross-process locking landed (Path A/A1): a
  portable `filelock` shared by fs-manager + git-sync (both derive the same
  path — `<WORLDS_ROOT>/.locks/<canonical_world_id>.lock` in per-world mode
  (UUID canonicalized, so spellings don't fragment), `<REPO_ROOT>/.sentinel-locks/shared.lock`
  in shared mode — outside the world tree so teardown's rmtree can't delete a
  held lock). New write
  paths must take it (`_acquire_world_lock`) — don't add an unguarded write.
  Also seeded: GitPython's in-memory index (`repo.index.add`/`commit`) resolves
  working-tree paths against the **process cwd**, so concurrent commits race —
  use the subprocess form (`repo.git.add`/`commit`, `cwd=repo.working_dir`).
  Residual (deferred): the lock is per-operation, not held by the backend
  across the apply→commit span — rare under one-player-per-world.*
- **Per-world isolation fallback** — when `SENTINEL_WORLDS_ROOT` is set, a write
  path with a **missing** `world_id` must NOT silently fall back to the shared
  `REPO_ROOT` (inter-world leak / master-pollution). Require it (422) and
  canonicalize (`str(uuid.UUID(...))`) at the route boundary; shared mode keeps
  `world_id` advisory. *(`_require_world_id_when_isolated` in both MCP servers.)*
- **Determinism where it's asserted** — anything claimed deterministic that
  depends on dict/set iteration, time, randomness, or filesystem ordering.
- **State-truthfulness / engine-authoritative fields (ADR-0004)** — the engine,
  not the DM, owns mechanically-determined state (a rolled death; `level`/`stats`
  on an enacted level-up). A DM `<world_update>` that overrides a committed outcome
  must be caught. Enforcement is **(a) dispatch-recompute-and-inject** (death-stakes
  RFC-0014, progression RFC-0017) or **(b) the fs-manager write-boundary guard**
  (unconditionally-immutable identity fields). **LESSON:** a write-boundary guard
  (b) CANNOT enforce a *conditionally*-writable field — the authorized and
  hallucinated writes are **byte-identical `<world_update>` ops** (`fact_extractor`
  emits `update`-only, so the LLM path can't even vary the op shape) and the field
  may be nested/turn-context-dependent — so those take mechanism (a). Placement
  contract: **engine computes → backend injects at dispatch → fs-manager guards**;
  never inside `apply_world_update` (no world state there) or an engine agent.
- **Entity-identity shadowing (LLM-reachable)** — the PC is resolved as the FIRST
  `role=="player"` entity in glob order (`find_player_character`), so an imposter
  entity file that sorts earlier shadows the real PC. **This IS on the LLM path**
  (codex, PR #186): `fact_extractor` passes `role` through (`_strip_action` strips
  only `action`) and its `update` op upserts to a *new* slug, so a hallucinated
  `<world_update>` introducing e.g. `0-imposter` with `role:"player"` shadows the PC
  — and because it's a different name/slug than the session PC, `enforce_progression`
  doesn't match it, so it also **bypasses RFC-0017's level/stats invariant**. Shared
  by progression + death-stakes. **RESOLVED 2026-08-12**: `find_player_character` now anchors on the session PC
  name via slug (no `role` fallback when the name is known), and
  `engine/identity.py::enforce_pc_identity` strips a `role:"player"` claim from any
  non-PC entity op at BOTH dispatch seams (stream + intro). Neutralize-not-delete:
  the character lands as an NPC.
- **Stale-cache-after-redeploy** — a cached `index.html` pointing at a purged
  hashed bundle → blank page.
- **Provider/API param compat** (`max_completion_tokens` vs `max_tokens`);
  **env/setup fragility** (PEP 668, bare `pip` in `install` recipes — note
  `dev-backend` now venv-autodetects via `venv_python`); **biased validation
  corpus** (one smoke transcript ≠ coverage).
- **Trusting a client-controlled header for a security/abuse decision** — keying
  a rate-limit, auth, or identity check on `X-Forwarded-For` (or any request
  header the client can set). Behind a proxy, only the hop the *trusted* proxy
  appends is reliable: count the **Nth-from-right** (per `SENTINEL_TRUSTED_PROXY_HOPS`),
  which naturally ignores any client-spoofed hops on the left — so the proxy need
  not overwrite inbound XFF. And uvicorn's default `--proxy-headers` must be
  **off** (it rewrites `request.client` from the spoofable *leftmost* hop).
  *(red-team #3: the per-IP rate-limit was XFF-spoofable until #92.)*

---

## Directory Conventions

- `docs/` — project documentation (BACKLOG.md, ROADMAP.md, VISION.md, QUICKSTART.md, ADRs)
  - `docs/blueprint-kb-manifest.txt` — the list of docs Blueprint's nightly `/knowledge` sync ingests (one repo-relative path per line). **Append a new ADR / RFC / operating doc when you commit it; remove on retirement.** Never list `data/`, `infrastructure/.env*`, `scratch/`, or churn docs (BACKLOG, ALPHA_FEEDBACK, handoffs).
- `backend/` — FastAPI production backend (`:8001`)
- `engine/` — pure-Python Inference Node package (agents, dispatch, schema)
- `mcp-servers/` — Python MCP server implementations (fs-manager, git-sync)
- `apps/sentinel-ui/` — React 19 + Vite frontend (the gated game app)
- `apps/sentinel-site/` — React 19 + Vite public landing + `/guide` SPA, served at the apex of `sentinelrpg.com` (separate from the gated game app; renders the shared `docs/alpha/TESTER_GUIDE.md`)
- `data/` — canonical world state (`state/*.json`) and lore (`lore/*.md`) under git
- `schemas/` — shared JSON Schema contracts
- `infrastructure/` — Docker Compose and environment configuration
- `scripts/` — shell scripts for automation and dev lifecycle
- `tests/` — pytest suites (Python)

**Chatlog home:** `/srv/projects/pkplab/chatlogs/project-sentinel/` (origin-core; transitioned 2026-06-05). The `~/.claude/projects/-srv-projects-project-sentinel/*.jsonl` paths are symlinks into that shared dir. New-session jsonls land at the old path; `/srv/projects/pkplab/chatlogs/sync.sh` migrates them periodically.

---

## Things to Know About This Project

- This is a cross-OS project. Do not write scripts or configs that assume linux-only.
- Replit was the original development platform. Migration is complete.
  Do not introduce new `@replit/*` dependencies.
- **Time reference defaults to Pacific Time (Russell's local time —
  America/Los_Angeles).** When stating "today", "tomorrow", "tonight", or
  any user-facing time-relative phrasing, compute it relative to Pacific
  Time — NOT the UTC date the harness's system reminders give. Pacific
  Time is **PDT (UTC−7) during DST** (roughly mid-March → early November)
  and **PST (UTC−8) the rest of the year** — so the harness/UTC offset
  varies. Either way UTC is **ahead** of Pacific Time, so the UTC date
  rolls **before** Pacific does; treating UTC as user-side "today"
  produces wrong-by-a-day claims (and in summer, wrong-by-an-hour on a
  cuspy time). When unsure of the current offset, fall back to
  `America/Los_Angeles` semantics rather than a fixed PST/UTC−8. See
  `feedback_time_equals_pst` memory for the full rule and mental model.
- **Daily patch-window cadence: 05:00–08:00 Pacific Time every day**
  (= 12:00–15:00 UTC in PST winter / 13:00–16:00 UTC in summer DST).
  Low-traffic slot for the closed-alpha cohort; ~30 sec backend restart +
  zero-downtime SPA rebuild fits comfortably. **Stack multi-day work
  across consecutive windows** rather than compressing it. ~60–90 min of
  focused work fits in a window — two queued PRs is the realistic ceiling.
  Pre-stage next-day PR the prior evening so the window is review + merge +
  deploy, not coding from scratch. See `project_daily_patch_window` memory.
- **React is the 1.0 frontend.** Decided 2026-04-15 by the landing of
  `feat/panel-ux-entity-cards` — the "undecided, do not build new
  frontend features" gate that previously lived here is resolved. See
  `docs/VISION.md` § "Resolved decisions" for the rationale. Frontend
  work is a normal feature-work pathway; the usual "plan-then-execute,
  wait for explicit approval" flow still applies like it does for any
  other task, but there's no longer a special stack-decision gate.
- `just` is the command runner. Add new recipes to `justfile` rather than creating
  standalone scripts unless the logic is complex enough to warrant a separate file.
- **Background shell polls must be BOUNDED** — always `for i in $(seq 1 N)` with a
  break condition, never a bare `until`/`while` loop. Three orphaned until-loops
  (PR-review polls from June sessions) survived their sessions and hammered the
  GitHub API every 10–15s for 3–7 DAYS before being caught in a server-stress hunt
  (2026-07-02). When origin-core feels stressed, check `pgrep -f "sleep 1[05]"`
  for leftover poll loops (and see the `project_reboot_recovery` memory for the
  full post-reboot / stress-hunt checklist).
- **The DM LLM is any OpenAI-compatible endpoint, configured in
  `infrastructure/.env`** (gitignored) via `OPENAI_BASE_URL` / `DM_MODEL` /
  `OPENAI_API_KEY`. The chezmoi template default is Groq
  (`llama-3.3-70b-versatile`); swap the three vars to route elsewhere
  (LiteLLM, real OpenAI, etc.). **Changing the LLM config — or any
  `infrastructure/.env` value — requires a FULL backend restart, not a
  `--reload`.** `config.Settings.load()` calls `load_dotenv()` with the default
  `override=False`, so it will not overwrite a var already in the live process's
  environment, and `uvicorn --reload` re-imports code but never re-reads the
  process env. A `.env` edit is therefore invisible until the process is killed
  and started fresh. When launching the backend yourself, `unset OPENAI_API_KEY
  OPENAI_BASE_URL DM_MODEL` first so a stale shell-exported value can't win over
  `.env`. Verify a turn (or the loaded config) after restarting — don't assume
  `--reload` caught it.
- **Public marketing site is LIVE at `sentinelrpg.com` (since 2026-06-30).**
  `apps/sentinel-site` (`@sentinel/site`, React 19 / Vite / Tailwind / wouter) is a
  separate **public, unauthenticated** SPA — routes `/` (landing) + `/guide` (renders
  the shared `docs/alpha/TESTER_GUIDE.md`) — that exists because the gated `/alpha/`
  basic_auth-401s OG/link-preview crawlers. It's the home for the share card.
  `sentinelrpg.online` 301→apex. Lane: the **SPA artifact + cutover is mine**;
  **DNS/TLS/hosting/edge is tailnet's** (placement = origin-core static behind gate;
  delivery = I drop `sentinelrpg-site-<sha>.tar.gz` in `/srv/handoff/sentinelrpg/`
  on merge, tailnet does the atomic symlink swap). "Sentinel RPG" = public brand;
  "Project Sentinel" = engine codename. See `reference_sentinel_public_domains` memory.
- **Game art via `genimg` (headless, dual-provider image gen).** `/srv/projects/genimg/genimg.sh`
  generates images for cards/genre-tiles/heroes across TWO providers (routed by model name):
  Gemini/Imagen (key `~/.config/genimg/gemini.env`) — `gemini-3-pro-image` = best text-in-image,
  `imagen-4.0` for aspect; and OpenAI gpt-image (key `~/.config/review-kit/openai.env`) —
  `gpt-image-2` newest, `--size`/`--quality`, no visible watermark. Format-aware finalizer
  honors your output extension.
  Pipeline: strip the visible Gemini sparkle (corner-flatness gate, or a wide→card crop
  removes it) → SynthID persists/disclosed → bake Sentinel provenance tEXt (Author=`Sentinel
  RPG`, Copyright=`© 2026 Sentinel RPG by Russalo`, Source=`https://sentinelrpg.com`,
  Disclaimer) → hash-verify served bytes. Firefly/Figma preferred for design-grade public
  work. See `reference_genimg_tool` memory.
- **Game art also via the OpenArt MCP (image + VIDEO gen).** A session-connected
  MCP (`mcp__claude_ai_openart__*`) — complements `genimg` by adding **video**
  (Wan 2.7 / Kling / PixVerse / Seedance; image→video, text→video). First use
  (2026-07-03): the 5 animated genre-tile loops in `apps/sentinel-ui/src/assets/generated/`
  (PR #175, live on the alpha). Recipe for a locked-framing animated tile:
  **Wan 2.7 image2video + identical start/end frames + a tripod prompt + camera
  motion in the negative + strip audio (`ffmpeg -an`)**. Provenance caveat: raw
  OpenArt output carries NO Sentinel tEXt — gated in-game art is fine, but
  public/branded art still needs the `genimg` provenance pass. See
  `reference_openart_animated_tile_recipe` memory.
- **Lorekeeper fold (DM cites canon) is BUILT + DORMANT (since 2026-07-01).**
  RFC-0011 (Slice 1) + RFC-0012 (Slice 2) + ADR-0006 landed a lore-retrieval
  step in the turn loop: the backend (`backend/state/lorekeeper.py`, IO)
  subprocesses **`poggio`** (a peer tool at `senlab/poggio` / `russalo/poggio`
  that vendors `trellis` — the retrieval substrate, **NOT ChromaDB**, retired by
  ADR-0006) to fetch ranked, provenance-carrying canon, and the pure engine
  (`engine/agents/lorekeeper.py`) renders it into the DM prompt. **Gated by
  `SENTINEL_LOREKEEPER_ENABLED` (default false = dormant)** and **fail-open**
  (missing/broken poggio → no canon, never breaks a turn). To make it live =
  **arm it**: build+install `poggio` on PATH (`cargo build --release`), `trellis
  >= 0.26` on PATH, flip the flag in a patch window (pin `poggio >= 0.2.0`).
  Channel with the poggio session: build/FRs → `russalo/poggio` issues (label
  `from:sentinel`); coordination → via Russell. See `project_lorekeeper_fold_state`
  + `project_poggio_session_json_softcontract` memories.
- **Sentinel runs on TWO hostnames now (since 2026-06-07).** The closed
  alpha is **live at `sentinel.russalo.com/alpha/`** (gate-fronted: DNS
  resolves to a separate gate machine that terminates TLS and reverse-
  proxies cleartext HTTP over tailnet to origin-core's Caddy — same shape
  as `blog.russalo.com`). The tailnet dev site at `sentinel.dev.russalo.com`
  stays up in parallel. **Origin-core never accepts a public connection
  directly** — listener isolation is enforced at the UFW firewall layer,
  NOT by `bind` in Caddy (origin-core's Caddy is multi-tenant with blog +
  Blueprint on the same wildcard `:80` listener; see
  `project_origin_core_caddy_is_multitenant` memory).
  The cutover landed: `SENTINEL_WORLDS_ROOT`, `SENTINEL_SESSION_TOKEN_SECRET`,
  `SENTINEL_RL_SESSION_CREATE_PER_HOUR=20`,
  `SENTINEL_RL_STREAM_PER_MINUTE=30`, `SENTINEL_LLM_DAILY_CEILING=10000`,
  `SENTINEL_MAX_CONCURRENT_STREAMS=10`, `SENTINEL_DEBUG=false`,
  `SENTINEL_TRUSTED_PROXY_HOPS=1` all armed in `infrastructure/.env` on
  origin-core; `just cutover-check` reports READY. Per-world routing
  applies ONLY to the mutable world state (session JSON in
  `data/state/core/sessions/`, session-log markdown in
  `data/lore/core/sessions/`, fs-manager write sets for entities /
  locations / items / world meta) — read-only shared assets
  (`schemas/`, the core-lore codex under `data/lore/core/` *outside*
  `sessions/`, persona presets) continue to load from the repo root
  and are NOT relocated per-world. The repo's contribution
  remains *artifacts + invariant*: the Caddy invite-gate template
  (`infrastructure/caddy/Caddyfile.example`, with the gate-fronted
  adjustments `http://` scheme + no `bind`), the systemd unit templates
  (`infrastructure/systemd/`), the **hard rule that any edge proxies
  ONLY the backend `:8001`** — never the MCP write layer `:8010`/`:8012`
  (`tests/test_caddy_invariant.py` guards it). What stays out of scope
  here: DNS, TLS certs, the deployed Caddyfile content, gate's own config
  — those are tailnet Claude's lane (see below). Verify a future cutover
  change safely with an **isolated stack** — armed fs-manager/git-sync/
  backend on alt ports with a temp `SENTINEL_WORLDS_ROOT` (direct env
  injection; `SENTINEL_SKIP_ENV_CHECK=1` if not loading `.env`) — so
  nothing touches the running live stack.
- **Local play/smoke sessions commit to the checked-out branch — UNLESS
  `SENTINEL_WORLDS_ROOT` is armed.** The engine's `git-sync` writes a
  per-turn `[sentinel] world=… session=… turn=…` commit (the `world=`
  prefix since ADR 0002 Slice 1 threads a per-session `world_id`) to
  whatever branch is checked out — normally `master` — on every turn.
  **On origin-core (post-2026-06-07 cutover) this is no longer a hazard**:
  `SENTINEL_WORLDS_ROOT=<WORLDS_ROOT>` (a path outside the code repo) is
  armed in `infrastructure/.env`, so all gameplay routes to per-world
  repos *outside* the code repo. **The hazard remains for any machine where
  the env var is unset** (any fresh clone, a contributor's laptop, a
  test box) — running a playthrough there pollutes the checked-out
  branch (this is what produced the 22 stray commits cleaned up
  2026-05-30, and what produced the 10 ahead-of-origin commits cleaned
  up by the 2026-06-07 cutover restart). **Fix on unconfigured machines:**
  `export SENTINEL_WORLDS_ROOT=~/sentinel-worlds` in your shell and run
  the servers via the individual recipes (`just fs-manager` / `just
  git-sync` / `just dev-backend`) — **not** `just start`, whose `env`
  prerequisite regenerates `.env` and clobbers the value (and the LLM
  key). See `docs/WORKSPACE.md` § "Local dev: keep gameplay out of the
  code repo".
- **The alpha deploys via the RFC-0015 dev→staging→prod PIPELINE (live since
  2026-07-04) — NOT build-in-place.** origin-core's Caddy roots `/alpha/*` at a
  sentinel-owned serve tree `/srv/serve/sentinel-alpha/` — `releases/<git-sha>/`
  (immutable `build:alpha` outputs) + a `current` symlink (what prod serves) + a
  `staging` symlink (the candidate). **`dist` is no longer the alpha's live dir**
  (it reverted to the tailnet dev site). **Deploy = three `just` recipes, from
  master, in a patch window:** `just build-alpha-release` (build:alpha →
  `releases/<sha>/` via `--outDir` + repoint `staging`; refuses off-master/dirty;
  never writes `dist`) → verify in a real browser at
  `https://sentinel-staging.dev.russalo.com/alpha/` → `just promote-alpha` (atomic
  `current` repoint, zero-downtime). Rollback = `just rollback-alpha`; inspect =
  `just alpha-status`. **The alpha build-in-place footgun is GONE** (only
  `promote-alpha` flips prod; build-alpha-release refuses to clobber a
  `current`/`staging`-referenced sha). **BUT NOTE:** only `just build-alpha-release`
  creates a release — a **raw** `pnpm --filter @sentinel/ui build:alpha` still
  writes Vite's default `apps/sentinel-ui/dist`, which now belongs to the **tailnet
  dev site** (`sentinel.dev.russalo.com/`), so a raw build:alpha overwrites the
  dev-site root with `/alpha/`-based assets → breaks the dev site (fix with
  `just build-site`). So: use the recipe, not the raw script.
  Still verify frontend logic with vitest (`pnpm --filter @sentinel/ui test`) +
  typecheck, not a build. Lane split unchanged: sentinel owns the serve-tree +
  recipes; tailnet owns Caddy's root → `current`, the staging host, the gate.
  See RFC-0015, `docs/WORKSPACE.md` § "Alpha deployment", `project_alpha_deploy_pipeline`.
- **Staging is a true pre-prod (RFC-0016, slices 1-3 landed 2026-07-04).** A
  parallel backend `:8101` + fs-manager `:8110` + git-sync `:8112` trio with its
  OWN world store (`~/sentinel-worlds-staging`, gate off) — so staging worlds
  never touch prod. `just staging-*` / `just stage-*` recipes + `infrastructure/systemd/sentinel-*-staging.service`
  units (which use a second `EnvironmentFile=<REPO_ROOT>/infrastructure/.env.staging`
  — absolute path — NOT `Environment=`,
  because per systemd.exec EnvironmentFile OVERRIDES Environment=). **Deterministic
  deploy GATE: `just stage-smoke`** — an ephemeral **mock-DM** trio
  (`SENTINEL_DM_MODE=mock`, `backend/mock_dm.py`, zero LLM) drives a scripted
  death-sequence fixture to a *verified* death, proving the full mechanics chain.
  `just stage-candidate <ref>` runs the trio from a git worktree at the candidate.
  Remaining (in the memory inbox): the origin-core bring-up + tailnet's
  `sentinel-staging.dev/alpha/api → :8101` repoint. See RFC-0016,
  `project_rfc0016_staging_preprod`.
- **Live alpha features shipped this week (cohort feedback channels +
  ambient surfaces).** As of 2026-06-12, the closed alpha at
  `sentinel.russalo.com/alpha/` has these shipped surfaces in addition to
  the game itself:
  (a) **DM action suggestions** — the DM emits `<action>label</action>`
  tags inline in narrative + a structured `suggestedActions` field in
  the world_update block; the SPA highlights both as clickable
  affordances (amber pills in a rail above the command bar + amber
  underlined inline). Click types the action into the input; player
  reviews + sends. See PR #112 + polish PR #113. (b) **In-product
  feedback form at `/alpha/feedback/`** — testers submit structured
  reports (subject, body, category, platform, browser, optional severity
  / repro / handle) that auto-capture worldId, sessionId, viewport,
  currentUrl, bundleHash, userAgent. Backend writes JSON to
  `<SENTINEL_FEEDBACK_ROOT>/YYYY-MM-DD/<ts>-<id>.json` (gitignored;
  configured in `infrastructure/.env` — origin-core points it at the
  repo-relative `feedback/` dir, but the path is environment-specific
  so don't hard-code it in docs or scripts).
  Per-IP rate limit `SENTINEL_RL_FEEDBACK_PER_HOUR=10`. Triage flow:
  read submissions on disk, graduate ripe items into
  `docs/ALPHA_FEEDBACK.md` + `docs/BACKLOG.md`. See PR #116.
  (c) **Tension meter** at the bottom of the world-state panel — renders
  the DM-emitted `world.tension` 0–10 as a colored progressbar with a
  categorical band ("Calm / Off-balance / Overdue / Critical"); the DM
  prompt's TENSION & ENCOUNTER PRESSURE block uses tension as encounter
  pressure (PR #124). (d) **Player Vitals silhouette** at the top of
  the same panel — an inked humanoid SVG whose body fills with an
  amber→blood wash as `health` drops (PR #127), with per-band opacity
  floors so the wash is visibly distinct at every damaged level on the
  dark codex palette (PR #128 visual-iteration fix), and a race-keyed
  geometry dispatch stub (`RACE_BODIES` map keyed by lowercased race
  name with prototype-safe lookup; PR #129). Per-race art is BACKLOG;
  every Fantasy race renders the human geometry today. The two
  ambient surfaces together — Vitals at the top, Tension at the bottom
  — read as a "you ↔ world" sandwich and surface a systemic layer the
  DM increasingly implies (see **Fantasy-flagship core systems**
  initiative in `docs/BACKLOG.md`).
- **`docs/ALPHA_FEEDBACK.md` is the capture surface for tester feedback;**
  `docs/BACKLOG.md` is the triaged-work surface. Items land in FEEDBACK
  first (one-line, dated, by category — bugs / UI-UX / general / future
  features) and graduate to BACKLOG when ripe with a `→ BACKLOG`
  cross-link. The on-disk feedback dir is the raw stream; the docs are
  the human-curated view.
- **Tailnet Claude owns the public-facing edge (now LIVE).** The lane
  split, validated through deployment 2026-06-07: *sentinel-side (mine):*
  the app, the access-layer cutover (env knobs armed in
  `infrastructure/.env` on origin-core), the structural edge artifacts
  (`infrastructure/caddy/Caddyfile.example` + `infrastructure/systemd/*.service`
  templates), and the **hard invariant Caddy proxies only `:8001`, never
  `:8010`/`:8012`** (the MCP write layer stays loopback;
  `tests/test_caddy_invariant.py` guards it — 15 tests including the
  gate-fronted invariants: `http://` scheme, hostname is the apex,
  hostname root returns 404, bare `/alpha` redirects to `/alpha/`, all
  app handles wrapped in `handle_path /alpha/*`, operator paths
  (`/api/sessions*`, `/api/admin*`, `/_status`) 404 on the edge).
  *tailnet-Claude-side:* DNS (apex points at gate, not origin-core), TLS
  certs (terminated at gate, cleartext over tailnet to origin-core),
  the live edge config on gate, cloud-key management, prod-LiteLLM
  build, and **operational page content in any deployed Caddyfile**
  (maintenance HTML, `handle_errors` blocks — see
  `project_caddy_handle_errors_lane` memory). The gate-fronted topology
  is captured in `project_gate_fronted_topology` memory; the multi-tenant
  origin-core Caddy constraint (which rules out `bind` in our template)
  is captured in `project_origin_core_caddy_is_multitenant`. Don't list
  DNS/cert/public-edge work as a sentinel gap or try to fix it here.
  Term precision: "tailnet Claude" is the project's deliberate term for
  this role (used throughout memory + commit messages + Caddyfile.example);
  keep it even when a review bot suggests genericizing it.
- **Cross-lane coordination protocol** (validated on the `handle_errors`
  loop 2026-06-06): when sentinel knows the shape of an artifact but
  tailnet (or another peer agent) owns its placement, *draft → relay → verify
  → commit*. Sentinel drafts the artifact + rationale + open questions; user
  relays to the peer; the peer's response is treated as authoritative on
  placement / ops concerns. Operational infrastructure (maintenance pages,
  runtime-iterating content) lives in the deployed artifact only — NOT mirrored
  in our template; a discoverability comment is the right amount of mirroring.
  Don't couple operational iteration to sentinel's `pnpm build` / PR cycle.
- **Cross-pollination with peer projects (Scanner / file-observer).** Lane split
  is **substrate ↔ interpreter**: file-observer observes (chatlog detection,
  reference_tokens, provenance vectors — "every time a raven flies by, write
  it down"); Sentinel interprets (what the raven means). Schemas fork at the
  consumer layer. **Soft external contracts** are named explicitly across the
  boundary: `backend/datasets.py::build_chatlog` mirrors
  `file_observer.scanner.CHATLOG_SPEAKER_LABEL_RE` (schema 1.3) — neither side
  changes it without routing through Russell first. The relationship is
  cross-pollination, NOT coordinated work: patterns and design lessons flow
  both ways (orthogonal-axes ladders, `rules_fingerprint` over stored IDs), but
  neither side files work for the other. Scanner's `scratch/scanner_sentinel_parallels.md`
  (2026-04-11) is load-bearing architectural scaffolding when Entity Sweeper
  spins up — see `project_entity_sweeper_direction` memory for the cross-link.

---

## Planning Docs: Near-Term vs Vision

Every planning document in this repo must explicitly separate **near-term target**
from **vision target**. The split is structural — either two files or two clearly
labeled sections — never blended into prose.

- **Near-term target** — what ships in the next 1–3 PRs. Concrete, linked to
  `docs/BACKLOG.md` IDs, stack and architecture assumed fixed. This is a
  commitment, not a wishlist.
- **Vision target** — what Sentinel points at beyond the near-term. Aspirational,
  open questions allowed, stack choices explicitly up for debate. This is a
  direction, not a plan.

**Two files vs one file with two sections:**
- Use **two files** when the vision has enough surface area to rot slower than
  execution (e.g. `docs/ROADMAP.md` and a separate `docs/VISION.md`, or
  `docs/FRONTEND_PLAN.md` and a separate stack-decision note). Add a one-line
  pointer from each to the other.
- Use **one file with two labeled sections** when the topic is small enough to
  stay coherent (e.g. `docs/TESTING.md` with "Current" and "Vision" sections).

When writing a new planning doc, default to this split without being asked.
When revising an existing planning doc that blends the two, flag it and propose
the separation before editing.

---

## Common Commands

`just` is the entry point for everything. `just` with no args lists all recipes.

**Setup**
- `just env` — regenerate `infrastructure/.env` from the chezmoi template (OS-aware: Docker socket path, Python binary)
- `just install` — one-stop installer: pnpm workspace + all Python deps (MCP servers, FastAPI backend, engine package, pytest). Fresh clone should be runnable after `just env && just install`.
- `just install-backend` — reinstall the FastAPI backend's Python deps alone

**Run the stack**
- `just start` — full stack: Docker (ChromaDB) → wait healthy → both MCP servers in background
- `just health` — pass/fail table for every service; exits non-zero if anything is down
- `just reset` — wipe Docker volumes and restart from scratch
- `just up` / `just down` / `just down-volumes` / `just ps` / `just logs [service]` — raw Docker Compose passthroughs
- `just fs-manager` / `just git-sync` — run an individual MCP server in verbose dev mode (ports 8010 / 8012)

**Dev servers**
- `just dev-backend` — FastAPI backend on `:8001` (`uvicorn backend.main:app --reload`)
- `just dev-frontend` — `apps/sentinel-ui` Vite dev server
- `just dev` — frontend + backend together

**Build & typecheck**
- `just build` — `pnpm build` across the workspace
- `just typecheck` — `pnpm typecheck` (no emit)

**Tests**
- `just test` — Python schema tests + all workspace JS tests (`pnpm -r --if-present run test`)
- `just test-schemas` — Python schema validation only (`pytest tests/`)
- Single Python test: `pytest tests/path/to/test_file.py::test_name`
- Single JS package: `pnpm --filter <pkg-name> test`
- **CI's `Lint Python` job runs BOTH `ruff check` AND `ruff format --check`** over
  `engine/ backend/ tests/ scripts/ mcp-servers/`. Run **`ruff format`** (not just
  `ruff check`) before pushing — the lint job fails on a formatting diff even when
  the linter is clean (burned a review round 2026-07-08).

**Session lifecycle**
- `just start-session` — fetch, branch status, open backlog items, structure check
- `just end-session` — backlog + structure reminder before closing
- `just check-structure` — verify all documented paths exist

---

## Architecture at a Glance

> **Canonical state lives on disk.** Per **[ADR 0001](docs/adr/0001-data-canonical-source-of-truth.md)**, `data/state/*.json` + `data/lore/*.md` + git is the single source of truth. All writes go through `engine/` → `fs-manager` → `git-sync`. Phase 1 replaced Django with FastAPI; Phase 2 removed Postgres from the stack entirely. No database queries in the turn loop.

Sentinel is a two-node agentic system with a strict filesystem firewall between them. Understanding this split is required before editing anything in `engine/`, `mcp-servers/`, or `schemas/`.

**The two nodes**
- **Inference Node** (`engine/`) — pure-Python package housing the DM and Fact-Extractor agents. **Never granted direct filesystem access.** Generates narrative, then emits a structured `<world_update>` JSON payload. Live and wired into the FastAPI backend; the engine→fs-manager→git-sync path runs end-to-end. The **Lorekeeper** read-side fold is BUILT (dormant) — but per the engine boundary its retrieval IO lives in the backend, not here; `engine/agents/lorekeeper.py` only *renders* the retrieved canon (see the Lorekeeper bullet above + `engine/README.md` for the boundary contract).
- **Infrastructure Node** (`mcp-servers/` + `infrastructure/`) — the git-backed hybrid filesystem under `data/` (the only path from Inference → disk). ChromaDB is still in the Compose stack (currently `stopped`) but its planned RAG/Lorekeeper role was **retired by ADR-0006** in favor of the `poggio`/`trellis` retrieval substrate (deterministic + citable, where vector RAG fought Sentinel's invariants).

The two nodes communicate over a Tailscale mesh in production; locally they run side-by-side on the same host.

**The MCP Bridge** — two Python servers, each on a fixed port:
- `fs-manager` (`:8010`) — only thing that writes `data/state/*.json` and `data/lore/*.md`
- `git-sync`  (`:8012`) — atomic commit after each world update

**The core loop** (see `ARCHITECTURE.md` for the full diagram):
1. Player action → DM agent → narrative text
2. Fact-Extractor parses `<world_update>` tags out of the narrative
3. Payload validated against `schemas/apply_world_update.schema.json` (Draft 2020-12). **Invalid payloads are rejected and fed back to the DM** — schema failure is a first-class control-flow path, not an error case.
4. Dispatcher calls fs-manager to apply state changes, then git-sync to commit
5. Next turn reads the updated `data/state/*.json` directly (no cache layer)

Per **[ADR 0004](docs/adr/0004-state-truthfulness.md)** (state truthfulness, Accepted 2026-07-08), the engine — not the DM — owns *mechanically-determined* state, and the DM can't override a committed mechanical outcome. Between steps 2 and 4 the backend orchestration (`backend/routes/stream.py`) recomputes engine-owned outcomes from trusted inputs + stored state and **injects them authoritatively over the DM's payload** — the RFC-0014 death-stakes and RFC-0017 progression (`level`/`stats`) mechanism. See the "State-truthfulness / engine-authoritative fields" hunt-list entry for the two enforcement mechanisms + the placement contract.

**Hybrid storage under `data/`** — human-readable Markdown for lore, machine-readable JSON for state, everything under git. Namespace separation is enforced at write time by fs-manager:
- `data/{lore,state}/core/` — Core team only; writes require the trusted `?namespace=core` query param the backend sets on dispatch (`engine.apply_world_update(namespace=…)`), **not** a field in the LLM-parsed body (red-team #7). The loopback boundary (ADR 0003) is the control for direct fs-manager callers.
- `data/{lore,state}/community/<pack>/` — community packs, additive only
- Protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`, `core_faction_id`) are immutable to community payloads — enforced in code by fs-manager's `check_protected_fields()` against the `PROTECTED_FIELDS` set in `mcp-servers/fs-manager/server.py` (not a JSON-schema keyword).

**Backend** — `backend/` is a FastAPI app on `:8001`. It serves `GET /healthz`, `POST /api/session/new`, `POST /api/stream` (SSE), `GET /api/world/{world_id}` (resume hydration — the world's session + world state), and `GET /api/sessions*` (the `/data` training browser). It reads mutable world state from the active world's `data/state/*.json` (the shared root when `SENTINEL_WORLDS_ROOT` is unset), while read-only shared assets (`schemas/`, presets, core-lore codex) always load from the repo root; it calls `engine/` for turn handling and dispatches writes through `engine.apply_world_update` → fs-manager → git-sync. No ORM, no database queries. Per **[ADR 0002](docs/adr/0002-world-identity-and-isolation.md)**, Slices 1–5 have landed (resume completeness, the "my worlds" picker, hard-delete teardown, and backend provisioning at session-create): every session is minted a `world_id` (UUID) threaded through both dispatch calls, the backend resolves a turn's world from its `session_id`, and worlds are provisioned at creation (git-sync `init_world`); when `SENTINEL_WORLDS_ROOT` is set, the MCP servers **and** backend route to a per-world `data/` tree / git repo under it. The env var is **unset by default** (per-world routing dormant; single shared tree) — the cutover is now an operational env flip (see `docs/WORKSPACE.md` § "Per-world isolation cutover"), gated on the tracer-soak in `tests/test_world_isolation_tracer_soak.py`. Per-world cross-process write locking (`filelock`, shared by fs-manager + git-sync) landed (Path A/A1). Per **[ADR 0003](docs/adr/0003-access-gating-and-public-exposure.md)** the access layer (Slices A+B) is in across **three orthogonal dimensions — rate, spend, and concurrency**: per-world HMAC session tokens enforced on world-scoped routes; per-IP/per-world rate limits (`SENTINEL_RL_*`); global daily LLM-call ceiling (`SENTINEL_LLM_DAILY_CEILING`); and a max-concurrent in-flight `/api/stream` cap (`SENTINEL_MAX_CONCURRENT_STREAMS`, added 2026-06-06 as the closed-alpha-blocker third dimension — hard rejects with 503 + `Retry-After: 5` at cap, no queueing). **All opt-in and dormant by default** (each armed by its respective env var; closed-alpha cutover sets the concurrency cap to `=10`). The MCP network-isolation invariant (both servers refuse an all-interfaces bind unless `SENTINEL_ALLOW_PUBLIC_BIND=1`; Caddy must never proxy `:8010`/`:8012`) and a backend cutover config-agreement check (refuses per-world startup unless both MCP `/health` report `worlds_root: true`) landed (Path A/A2). ADR 0003 Slice C has also landed (Path A/A3): the Caddy invite-gate template (`infrastructure/caddy/Caddyfile.example`, guarded by `tests/test_caddy_invariant.py`) and systemd unit templates (`infrastructure/systemd/`). The remaining public-exposure prerequisite is the **operational cutover** — arming the `SENTINEL_*` env knobs across all three services + deploying the edge (`docs/WORKSPACE.md` § "Production deployment" / "Per-world isolation cutover"). The access layer was red-teamed + hardened in the 2026-06-04 audit (PRs #92–#94: ungated `/api/sessions*` excluded from the edge, an `X-Forwarded-For`-spoofable rate-limit key fixed, and fs-manager protected-field/namespace gaps closed).

**Frontend** — `apps/sentinel-ui/` (`@sentinel/ui`), React 19 + Vite + Tailwind v3. Talks to the FastAPI backend via fetch + SSE. The game plays at a world's own URL — `/w/<world_id>` (wouter route) — so it's shareable and survives a refresh; on a fresh load the `useWorldHydration` hook rebuilds the scroll + world-state panels + persona from `GET /api/world/{world_id}`. `/` redirects to `/create`. React is the ratified 1.0 frontend stack as of 2026-04-15 (see `docs/VISION.md` § "Resolved decisions"); normal feature-work rules apply.

**Polyglot tooling**
- pnpm workspace (Node 24, pnpm 10) — `pnpm-workspace.yaml` covers `apps/*` and `scripts`
- Python 3.11+ for the MCP servers, the FastAPI backend, and the engine package — each has its own `requirements.txt`
- `chezmoi` generates `infrastructure/.env` from `.chezmoi/infrastructure/private_dot_env.tmpl` — that's why `just env` exists, and why you should never hand-write `infrastructure/.env`. The template is host-gated (PR #156): a host with a `~/.sentinel-armed` marker renders the armed access-layer knobs + LiteLLM→Gemini routing + the age-decrypted session secret (0600); every other host gets dormant dev defaults. `just env` on origin-core is therefore safe + authoritative now — not a clobber hazard.

**Cross-OS constraint** — this project targets macOS, Linux, and Windows. The chezmoi template handles OS-specific values (Docker socket path, Python binary). Never write linux-only shell in a `justfile` recipe without providing the equivalent for other platforms.

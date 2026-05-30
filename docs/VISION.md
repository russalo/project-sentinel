# Project Sentinel — Vision

> **Scope:** where Sentinel is pointing, explicitly *not* a commitment.
> This doc is allowed to contain open questions, stack bets that aren't
> final, and directions that may never ship in their current form.
> For the "what ships next" commitment, see [`ROADMAP.md`](./ROADMAP.md).

_Last updated: 2026-04-15_

---

## The core thesis

**"The world runs. You just play in it."**

Sentinel is an autonomous RPG world engine built around one structural
bet: an LLM should never touch the filesystem directly. Narrative flows
through a DM agent, state changes are extracted into a validated
`<world_update>` payload, and every write goes through a schema-enforced
MCP server before it lands on disk. The result is a system that can run
a campaign for months without human DM intervention and without
corrupting its own world state.

The bet that makes this interesting: **Markdown + JSON + git is
sufficient as the canonical store.** Entities, factions, lore, and
session logs all live as files under `data/`, version-controlled by
git, queried by re-reading the relevant file (not by database round-trip).
At v1.0 scale — hundreds of entities, not millions — this is cheap,
auditable, and survives everything from `git log` inspection to manual
editing by a human contributor when the AI gets it wrong.

ADR 0001 is the load-bearing decision under this. Phases 1 and 2 have
landed. Everything else in this document flows from that commitment.

---

## Resolved decisions

Things that were in "Open questions" and got answered. Kept here as a
short retrospective so future agents can see how we got where we are.

### The 1.0 frontend stack → React (decided 2026-04-15)

`apps/sentinel-ui/` is React 19 + Vite + Tailwind v3 + Zustand. The
question sat as an open item for weeks — the app existed because the
Replit-era scaffolding left it behind, not because a first-principles
evaluation picked it, and the decision was deferred to avoid premature
commitment. Alternatives considered: a terminal-native client, a local
desktop app (Electron/Tauri), an embedded pane inside Obsidian / Discord
/ VS Code.

**The answer landed by action, not by meeting.** On 2026-04-15, the
`feat/panel-ux-entity-cards` branch shipped real `EntityCard` primitives,
click-to-inspect wiring on the left-panel lists, and activated right-panel
tabs. Shipping those features on the React app is a de-facto commitment
— you don't build them twice — and the user explicitly endorsed making
the decision explicit in the docs when that branch merged.

**Rationale:**
- The existing React prototype is close enough to 1.0 shape that a
  from-scratch rewrite in another stack would cost more than it saves.
- React's component model fits the "entity card + panel + drawer"
  pattern naturally; the alternatives' strengths (terminal aesthetic,
  desktop wrapper, embedded tool) don't pay rent against the UX
  complexity the Panel UX BACKLOG item requires.
- The Panel UX work itself is validating the choice by producing real
  features. A decision that makes the next PR possible is the right
  kind of decision to make.

**What this unblocks:**
- Feature work on `apps/sentinel-ui/` no longer needs the "do not build
  new frontend features without explicit direction" gate from `CLAUDE.md`.
- The Panel UX BACKLOG item stops being "blocked on stack decision" and
  becomes "in progress" — though the ADR that was previously listed as
  a prerequisite is itself being deferred until Entity Sweeper and
  system log work begin (see the BACKLOG entry's "Before implementation:
  ADR" paragraph for the reframing).

**What this does NOT decide:**
- Whether Sentinel ever ships additional client shapes alongside React
  (a terminal client as a diegetic alternative, a CLI for automation).
  That's a post-1.0 question. "React is the 1.0 client" doesn't mean
  "React is the only client forever."

### The genre / preset content system → shipped (decided 2026-04-15)

The original VISION question was "what does each genre actually contain,
and how does the WorldCreation form's choices get composed into the DM
intro prompt?" The plan was a vision-level item: each genre / persona /
mood / region as a content bundle under `data/lore/core/presets/`, with a
backend pipeline that loads the matching bundle at session-create time.
The bridge implementations (Layer 1 in PR #20, Layer 1.5 persona
resolution in PR #33) were deliberate placeholders — they wired the
fields through and pushed descriptive strings into the intro prompt as
free-form context, but didn't load authored preset content.

**The answer landed by execution.** PR #39 ("World Generation Layer 2 —
preset content + generation pipeline") shipped the real thing. What's
now real:

- **Authored preset content under `data/lore/core/presets/`** in TOML
  format, one file per preset:
  - 5 genres: cyberpunk, fantasy, horror, sci-fi, western
  - 3 personas: chronicler, cowboy, oracle
  - 6 moods: fast-paced, gritty, humorous, lore-heavy, neutral, ominous
  - 20 regions, genre-scoped under `regions/<genre>/<slug>.toml`
    (4 regions per genre)
- **`backend/presets.py`** — minimal loader (`load_preset` +
  `get_prompt_fragment`). Lenient by design: missing files return
  `None`, which lets the engine fall through to Layer 1's free-form
  label handling without the frontend needing to know which presets
  exist on disk.
- **`engine/agents/dm.py::_build_intro_messages`** now injects a
  "WORLD FOUNDATIONS" paragraph block above the existing one-line
  "CREATION CONTEXT" block when any `*_prompt` fragment is set.
  Suppression rule: when a Layer 2 prompt fragment is present, the
  corresponding bare-label line is omitted from CREATION CONTEXT so
  the same information doesn't appear twice.
- **70+ new tests** in `tests/backend/test_presets.py` and
  `tests/engine/test_dm.py` covering the loader, the pipeline, and
  the engine's preset-aware prompt composition.

**Why this happened by execution rather than ADR:** the file layout
turned out small enough to self-document via the shipped TOML files
and the `backend/presets.py` docstring. The author of PR #39
deliberately skipped writing an ADR (per the BACKLOG entry's order-
of-operations checklist, step 1 was "write an ADR" but steps 2–4
shipped first). Reasonable call for content-shape decisions that are
easier to read in code than to specify in prose.

**What this does NOT decide:**
- **Community pack composition** — the schema for declaring a pack's
  presets in `community.json` is still future work. PR #39 only ships
  the core layer; the community mirror (`data/lore/community/<author>/
  presets/<type>/`) loader and validation pipeline doesn't exist yet.
- **Programmatic seed-entity merging** — region preset files describe
  their canonical NPCs, locations, and opening situations in prose
  inside `prompt_fragment`, which the LLM reads and typically honors,
  but there's no structured guarantee. An optional `seed_entities`
  TOML block on region files (characters, locations, factions, items
  with schema-valid fields), merged into the initial
  `apply_world_update` payload before dispatch, is the next step in
  the WC Layer 2 BACKLOG entry's checklist. Gated on the world
  identity ADR.
- **Per-persona file directories** with split `system_prompt.md` /
  `voice_rules.md` / `persona.md` / `persona.json` (the layout the
  original DM Personas & Content Framework BACKLOG entry envisioned).
  PR #39 shipped a simpler one-TOML-file-per-preset layout instead.
  If the richer layout ever becomes necessary, the loader can be
  extended; for now the simpler shape works.
- **Action catalogs, mechanical resolution presets, additional
  content types** — generalizing the "preset" pattern to the rest
  of the framework (action sets, dice systems, etc.) is still future
  work. PR #39 proves the pattern, doesn't fully exhaust it.

---

## Open questions (the "not-yet-decided" list)

These are the things I'm deliberately leaving unresolved until evidence
forces a choice. Each one is a seam where the project could diverge
meaningfully.

### World identity and multi-session support

Right now the backend creates a new session UUID on every
`POST /api/session/new` but there's no concept of "the same world across
multiple sessions" or "resume where I left off." The architecture
assumes one world per clone of the repo. That's the simplest possible
answer and it's load-bearing for the "git is the canonical store"
story (git doesn't want to arbitrate between parallel histories), but
it breaks down as soon as a player wants to run two characters in the
same world or resume a session after closing the tab.

The open question: does Sentinel ever support *multiple parallel worlds*
in one clone? A `world_id` in every commit message and every entity
record would unlock it, but it also fragments the git history and
complicates every read path. The alternative is "one world per clone,
git branch to fork" — lower complexity, higher ceremony.

An ADR should settle this before the Panel UX work ships, because the
system-log tab's backend endpoint needs to know what it's filtering by.

**2026-04-15 update — this is no longer just a design question.** The
2026-04-15 live smoke test confirmed that starting a "new world" in
the UI does not wipe `data/state/core/`: entities, items, and
locations authored in prior sessions are still on disk and still in
the DM's context on the next run. Referencing "AR15" mapped onto a
`Ray Gun` the player had authored in an earlier session. The urgency
tier on this question is now **prerequisite for the minimum-viable-
structure research loop below** — isolated smoke-test runs require
session → world isolation, and today there is no code path that
provides it. See also the `docs/BACKLOG.md` Smoke-Test Findings
section for the cross-session bleed entry and the `just reset-world`
recipe proposed as the minimum-viable unblocker ahead of the full ADR.

### Mechanical resolution (dice, probability, rules)

During the first live smoke test, the player observed they could type
literally any action and the DM would improvise a plausible outcome.
That's fine for freeform storytelling but it means there are no game
*mechanics* — no dice, no stats, no resolution system. At some point
Sentinel either:

- Stays pure-narrative and leans into "the DM decides" as a feature
- Adds a `combat-roller`-style MCP tool for deterministic resolution
  of rolls, and wires it into the DM prompt so the model asks for
  rolls instead of adjudicating them
- Adopts a specific TTRPG system (D&D 5e, PbtA, FitD) and bakes its
  rules into the DM system prompt and the schema

The right answer almost certainly depends on genre. Fantasy-combat-heavy
campaigns benefit from dice; conversation-driven campaigns don't. The
genre/preset content system that landed in PR #39 (see "Resolved
decisions" above) is the natural place to attach mechanical rules
to a specific genre — a `mechanical_resolution` field on a genre
preset's TOML could declare "this genre uses the dice subsystem" or
"this genre is pure-narrative." Implementation deferred until either
a real session needs it or someone writes a content pack that depends
on it.

**2026-04-15 reframe.** Mechanical resolution is one point on a
larger curve, not an isolated feature. The 2026-04-15 smoke test
showed that `tension`, `level`, `hp`, and `danger` are already moving
on narrative vibes with no rules — not because the DM is broken, but
because there is no wall telling it *which* numeric deltas require
grounding. The question "should we have dice" is really a sub-
question of "what is the minimum wall that prevents ungrounded
numeric deltas" — which belongs under the minimum-viable-structure
research loop below. Treat this section as a pointer to that one,
not as a standalone open question.

### The minimum-viable-structure research loop

This is the frame the 2026-04-15 smoke test surfaced — it was hiding
inside the other open questions until the walkthrough revealed that
every "should we have X" debate on this list is secretly the same
question: *how much structure does an autonomous LLM-driven world
need before it stops going off the rails, and no more?*

**The thesis.** Sentinel's interesting contribution isn't "ships with
N rules." It's a methodology and an evidence base: *"here is the
minimum viable rule set for a coherent autonomous world, and here is
the curve of coherence gain per added wall."* Nobody in this space
has published that curve. Pure-LLM-freeform (AI Dungeon) and pure-
TTRPG-port (D&D Beyond bots) are the two degenerate endpoints.
Everything in between is unexplored.

**Why this is a research program, not a feature.** Every individual
wall that shows up on the BACKLOG (mechanical resolution, player
authority, action catalogs, entity singularity, class compatibility,
PC ownership, character ownership) is debated on this project as if
it were a design question with a right answer. The 2026-04-15 smoke
test changed the frame: these are empirical questions, and the answer
depends on running the same scenario against progressively stricter
schemas and watching what happens. The floor is the rules you can't
live without. The ceiling is the rules that start making the DM feel
like a rules lawyer. Both ends are discoverable; nobody has looked.

**The shape of the loop.**

1. Start with the current near-zero-constraint baseline. The
   2026-04-15 transcript at `docs/smoke-tests/2026-04-15-baseline.md`
   is the first data point — the "turn 0, no walls" run. Twelve
   distinct failure classes in six turns.
2. Run a scripted smoke scenario. Same inputs every time, so
   regressions and gains are visible. This is why the harness
   prerequisite matters — manual walkthroughs don't compose.
3. Add one constraint layer. Candidates in rough order of expected
   leverage: (a) entity singularity DM system prompt rule, (b)
   player-authority gate on mechanically-significant entities, (c)
   PC ownership schema flags, (d) schema enum enforcement on
   `status` / `type`, (e) ungrounded-delta rule for numeric stats,
   (f) DM refusal authority rule, (g) class/genre compatibility at
   WorldCreation, (h) action catalogs per genre, (i) mechanical
   resolution system per genre. Order isn't fixed — the harness
   measures it.
4. Measure coherence. Qualitative first (does the transcript read
   as sane, does the DM still feel alive, does the player still
   have agency?), eventually measurable (schema-valid entity
   references / total entity references, contradictions per 100
   turns, player-authored entity count, ungrounded-stat-delta
   count, lazy-fabrication count).
5. Find the knee of the curve. The point where adding more schema
   stops improving coherence and starts making the DM feel like a
   rules lawyer. That's the minimum viable structure.

**Prerequisites.** This is not a deliverable today — it's a frame for
deciding what to build. Two concrete enablers need to land first
before any of the loop is measurable:

- **Session → world isolation.** The research loop needs clean runs;
  clean runs need a reset path. See the "World identity and multi-
  session support" question above — this is why its urgency tier was
  promoted on 2026-04-15, and why the `just reset-world` BACKLOG
  enabler exists as the minimum-viable unblocker ahead of the full
  ADR.
- **A repeatable smoke harness.** Scripted player inputs, pinned LLM
  sampler config, captured transcripts, diff tool. See the
  corresponding BACKLOG enabler. Probably lives in `tests/smoke/`
  and depends on (a) world reset and (b) a "headless session"
  backend mode that doesn't need a browser.

**What this does NOT commit to.** It does not commit to shipping a
specific set of walls. It does not commit to publishing the curve.
It does not commit to mechanical resolution, or dice, or PbtA. It
commits to the *methodology* — that from here on, decisions about
walls are made by running the harness, not by debating them in
planning docs. The debate still happens; the debate just has
evidence to lean on.

**How this changes the BACKLOG.** The individual wall items
(entity singularity, player authority, PC ownership, schema enum,
ungrounded deltas, etc.) stay where they are. They become candidate
wall-additions on the research loop. Each time one is implemented,
the harness runs and a new transcript is captured at
`docs/smoke-tests/YYYY-MM-DD-<wall-name>.md`, and the VISION doc
gets a one-line retrospective naming what the wall moved. Over time
the smoke-tests directory becomes the empirical log; the BACKLOG
becomes the candidate queue; and this section becomes the frame that
ties them together.

**Connection to the architectural commitments.** This research loop
does not threaten ADR 0001 or the Inference/Infrastructure split.
Every wall on the list above is either a schema change, a prompt
change, or a validation rule at the engine boundary — all things that
live on the Inference Node side and flow through the fs-manager →
git-sync path the ADR already defines. The loop is *about* finding
the right shapes for the payloads that flow through the bridge, not
about rerouting the bridge.

### Background simulation

The world currently freezes between player turns. A long-held aspiration
is background simulation — a scheduled tick that advances faction
resources, shifts NPC moods, updates the time-of-day, and emits
`<world_update>` payloads without player input. "The world runs. You
just play in it." This is what makes Sentinel interesting as a
long-running sandbox rather than an on-demand story generator.

Open question: scheduling architecture. APScheduler inside the backend?
A separate long-running worker on the Infrastructure Node? A cron job?
And what's the cadence — every N minutes, every N real-world hours,
gated by player activity? The answer probably differs between
"I'm playing right now" and "the campaign has been idle for three
weeks."

### The Porter / Airlock / `.spak` pipeline

`ARCHITECTURE.md` §8 describes a package format (`.spak`) for sharing
world states between machines, with a Veil scrubber for export (PII
tokenization, exclude raw logs) and an Airlock for import (isolated
extraction, schema validation, path sanitization, vector re-embedding).
It's designed but not built.

This is the piece that turns Sentinel from "run a world on your own
machine" into "a multiverse of shareable worlds." It's the right
direction but the implementation cost is high and the audience for it
doesn't exist yet. Ship it when the first external contributor asks
for it, not before.

### Lorekeeper + ChromaDB RAG

ChromaDB is still in the infrastructure stack (Phase 2 kept it) but
nothing writes to it or reads from it today. The Lorekeeper agent
would change that: on each turn, query ChromaDB for semantically
relevant lore from `data/lore/core/codex/` and `data/lore/community/`
and inject the top-K results into the DM's context window.

The open question isn't whether this should happen — it obviously
should — it's *when*. The DM agent is already running out of
`engine/agents/dm.py` (PR #12 landed that migration), so the
"hook-in point" precondition is already satisfied. The real remaining
precondition is "enough lore to query to make the RAG earn its
complexity" — today the `data/lore/core/codex/` tree is sparse, so
even a perfect Lorekeeper wouldn't return much useful context. When
that changes, Lorekeeper becomes actionable.

### Community packs and the gateway

`schemas/community_manifest.schema.json` exists. `data/{lore,state}/community/<pack>/`
is a real code path in fs-manager with namespace enforcement and
protected-field blocking. What's missing is everything *around* it:
no published packs, no validation CI, no pack discovery mechanism,
no way to install one other than `git clone`ing it into place.

The vision is a proper plugin ecosystem — someone publishes a
"northern-wastes-expansion" pack, another player runs
`porter install northern-wastes`, the Airlock validates it, and
their next session has 5 new NPCs and a new faction. The gap between
"the fs-manager enforces the namespace rules" and "anyone can install
a community pack" is mostly product and policy work, not engineering.

### Governance: the Sentinel Charter

If Sentinel ever has more than a handful of contributors, someone has
to decide things like: who can elevate a community pack to Core canon?
How are schema deprecations handled? Who has commit access to
`data/state/core/`? The placeholder answer is "the Sentinel Charter —
a governance document ratified by the community." The real answer is:
this does not matter until there IS a community, and trying to
pre-write governance for a one-person project is a waste of time.
Worth listing here so it doesn't get forgotten, but it's the last
item on the list for a reason.

---

## What this implies for architecture

A few of the open questions have architectural consequences that are
worth naming even though the questions aren't settled:

- **The Inference Node boundary stays strict.** Every direction above
  that touches state (background sim, Lorekeeper, Porter) still has to
  go through the engine → fs-manager → git-sync path. The boundary
  isn't up for debate; what's up for debate is which agents the
  Inference Node contains and how often they run.
- **ChromaDB stays.** Phase 2 dropped Postgres but kept ChromaDB
  precisely because Lorekeeper + RAG is a concrete vision item that
  depends on it. If Lorekeeper gets cut, ChromaDB gets cut with it,
  but not before.
- **The `data/` tree is the API.** Every future feature that reads
  world state reads JSON files, not a database. Every future feature
  that writes state does so through a schema. This is the one
  architectural commitment that does not flex.

---

## How this document gets updated

- When a vision item becomes concrete enough to commit to: move it to
  `ROADMAP.md` under "In flight" or "Ready but unscheduled," and leave
  a one-line reference here pointing to the near-term entry.
- When a vision item gets explicitly rejected or superseded: delete it
  (or move it to a "Rejected" section at the bottom with a one-line
  reason).
- When reality overtakes a vision item (it silently shipped in a PR
  without being formally promoted): note the PR number inline and
  move the item to `ROADMAP.md`'s "landed" tail.
- When a stack decision lands: move the item from "Open questions" up
  to "Resolved decisions" with a dated retrospective. The 2026-04-15
  React decision is the working example of how this should look.

This doc is allowed to be wrong, incomplete, and over-ambitious. That
is the point. `ROADMAP.md` is where the commitments live.

# Project Sentinel — Vision

> **Scope:** where Sentinel is pointing, explicitly *not* a commitment.
> This doc is allowed to contain open questions, stack bets that aren't
> final, and directions that may never ship in their current form.
> For the "what ships next" commitment, see [`ROADMAP.md`](./ROADMAP.md).

_Last updated: 2026-04-14_

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

`apps/sentinel-ui/` is React 19 + Vite + Tailwind v4 + Zustand. The
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
campaigns benefit from dice; conversation-driven campaigns don't. This
ties to the Genre System direction below.

### The genre system

A WorldCreation form sends `genre`, `tone`, `starting_region`, and
`mood` to the backend today — and they're silently dropped. The vision
is that each genre is a proper content bundle:
`data/lore/core/presets/genres/<genre>.md` for human-readable prompt
guidance, `data/state/core/presets/genres/<genre>.json` for structured
metadata (key tropes, tone shifts, "forbidden moves", UI color palette).
Fantasy gets one set; Sci-Fi, Western, Horror, Cyberpunk each get their
own. The DM prompt includes the relevant preset at session creation.

This is a lot of content authoring work before it becomes load-bearing.
Near-term path is "Layer 1" — just wire the fields through and feed them
to the prompt as free-form strings. The full preset system is vision work.

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

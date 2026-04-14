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

## Open questions (the "not-yet-decided" list)

These are the things I'm deliberately leaving unresolved until evidence
forces a choice. Each one is a seam where the project could diverge
meaningfully.

### The 1.0 frontend stack

`apps/sentinel-ui/` today is React 19 + Vite + Tailwind v4 + Zustand.
It exists because it's what the Replit-era scaffolding left behind, not
because a first-principles evaluation chose it. The rules in `CLAUDE.md`
explicitly flag the 1.0 frontend as undecided and forbid new feature
work until the decision is ratified.

The real question isn't React-vs-something-else — it's *what shape of
client does Sentinel want*:

- A single-window web app (the current direction)
- A terminal-native client (fits the diegetic aesthetic better, smaller
  surface area, zero-install contributor story)
- A local desktop app wrapping the backend (Electron / Tauri — removes
  the deploy-a-webserver step for solo players)
- An embedded pane inside an existing tool (Obsidian plugin, Discord bot,
  VS Code extension — lowers the barrier to "where the player already is")

Until the Panel UX ADR forces the question, I'm holding the line against
adding features to the current React app. If React stays, the Panel UX
ADR becomes the next piece of work. If it doesn't, the current app
becomes a reference prototype and the real client gets designed from
scratch.

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
should — it's *when*. Until the DM agent is migrated out of
`backend/api/dm_ai.py` into `engine/agents/dm.py`, there's no clean
place for the Lorekeeper to hook in. Until there's enough lore to
query, the RAG doesn't earn its complexity. Both preconditions need
to happen before this becomes actionable.

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
- When the stack decisions land: the "1.0 frontend stack" question
  above gets replaced with the ratified choice and a pointer to the
  ADR that made it.

This doc is allowed to be wrong, incomplete, and over-ambitious. That
is the point. `ROADMAP.md` is where the commitments live.

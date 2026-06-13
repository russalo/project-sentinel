# RFCs — Request For Comments

This directory holds **RFCs**: lightweight design notes for per-feature
decisions and minor iterations. RFCs are deliberately smaller and
shorter-lived than ADRs.

If you're not sure whether a decision needs an RFC, an ADR, or neither —
read the next section before starting.

---

## RFCs vs ADRs

`docs/adr/` and `docs/rfc/` are two different commitments with two
different lifetimes.

**ADRs** (`docs/adr/`) are for long-lived architectural commitments —
the load-bearing decisions that, if reversed, would force a rewrite of
multiple subsystems. ADRs are heavy on context, list rejected
alternatives, and almost never get superseded. Examples: ADR 0001
(`data/` is canonical), ADR 0002 (world identity and isolation), ADR 0003
(access gating).

**RFCs** are for per-feature designs and minor iterations. An RFC has
**one** decision, fits in 50–150 lines, and is expected to either land
or get superseded within a handful of PRs. Examples of the kind of thing
an RFC is for: the wire shape of a new SSE event, the schema fields for
a new agent role, the UX flow for a new panel, the format of a new
log line.

| | ADR | RFC |
|---|---|---|
| Scope | Architectural, cross-cutting | Single feature or iteration |
| Length | Long (often 200+ lines) | 50–150 lines |
| Lifetime | Years; rarely superseded | Weeks–months; routine to supersede |
| Rejected alternatives | Required | Optional |
| Lands when | Design session reaches consensus | RFC PR merges |

When in doubt, write the RFC. If during the RFC PR review it becomes
clear the decision is actually architectural, promote it to an ADR
before merging — don't fold an ADR-shaped commitment into an RFC.

---

## When to write an RFC

Write one when:

- You're proposing a new feature whose shape isn't obvious from the
  existing code, and you want feedback before implementation.
- You're changing the wire/schema/UX contract of an existing feature in
  a way that ripples to other code or to testers.
- An item in `docs/BACKLOG.md` has matured enough that it needs a design
  before it can be picked up.
- You want a written record of *why* a small decision went the way it
  did, separate from the commit message.

Don't write one for:

- Routine bug fixes (a commit message is enough).
- Pure refactors with no behavior change.
- One-off scripts or tooling tweaks.

---

## Numbering and filenames

RFCs are numbered sequentially, four digits, with a kebab-case slug:

```
docs/rfc/0001-suggested-action-pills.md
docs/rfc/0002-fact-extractor-second-pass.md
docs/rfc/0003-feedback-form-redaction.md
```

The number is permanent; the slug can be adjusted before merge if the
scope shifts. Once merged, treat both as immutable — supersede with a
new RFC rather than renaming.

Pick the next free number by looking at this README's index (below) or
`ls docs/rfc/`. Two RFCs racing for the same number is fine — the second
one to land just bumps to the next number in their PR.

---

## Lifecycle

An RFC moves through four states in its front matter:

- **Draft** — Open PR, under discussion. The RFC may change shape
  significantly.
- **Accepted** — PR merged. The design is agreed; implementation may not
  have started yet, or may be in progress.
- **Implemented** — The feature has landed and the RFC matches what
  shipped. If the implementation diverged from the RFC, either update
  the RFC to match or supersede it.
- **Superseded** — A newer RFC (or an ADR) has replaced this one. The
  front matter must link the replacement.

State transitions happen in PRs, not in this README. Update the front
matter of the RFC file itself; the index below gets refreshed when
convenient.

A **Superseded** RFC stays on disk — don't delete it. The history is
the point.

---

## Front matter format

Every RFC starts with this block:

```markdown
# RFC NNNN — <Title>

**Status:** Draft | Accepted | Implemented | Superseded
**Date:** YYYY-MM-DD (date the RFC was first opened)
**Author:** <name>; <other contributors if any>
**Implements:** BACKLOG item description, or "—"
**Supersedes:** RFC NNNN (link), or "—"
**Superseded by:** RFC NNNN (link), or "—" (only filled when status becomes Superseded)
```

If the RFC implements a `docs/BACKLOG.md` item, paste the item's
one-line description verbatim so the link survives even after the
backlog entry is removed.

---

## Section structure

See `TEMPLATE.md` for the canonical layout. The sections are:

1. **Context** — what's true now, why this is coming up. Keep it
   factual; the user already knows the project.
2. **Proposal** — the actual design. Be concrete: field names, file
   paths, function signatures, wire shapes.
3. **Open Questions** — anything you genuinely don't know yet. Empty is
   fine if there are none; don't manufacture questions.
4. **Acceptance Criteria** — what "Implemented" looks like. Bulleted,
   testable.
5. **Out of Scope** — what this RFC is *not* committing to, especially
   adjacent work that might look like it belongs here.
6. **Cross-links** — related ADRs, RFCs, BACKLOG items, PRs, memory
   files.

Sections may be empty (use `—`) but should not be omitted — uniform
structure makes the index of RFCs scannable.

---

## How `docs/BACKLOG.md` feeds in

`docs/BACKLOG.md` is the **harvest pool**: a running stream of
half-formed ideas, surfaced bugs, deferred work, and "we should think
about this" notes. It's deliberately low-friction to append to and is
becoming gitignored — it's a personal scratchpad, not a contract.

RFCs are how a backlog item **graduates** into something that gets
built:

1. An item lives in `BACKLOG.md` until someone (usually Russell) decides
   it's ripe.
2. The next step is an RFC PR — copy the backlog one-liner into the RFC
   front matter's `Implements:` field, then flesh out the design.
3. When the RFC merges (Accepted), the BACKLOG item can be removed —
   the RFC is now the authoritative description of the work.
4. The implementation PR(s) reference the RFC number in their
   description.

If a backlog item is too small to need an RFC, just do it — the commit
message is the record.

---

## PR workflow

1. Branch off `master`: `git checkout -b rfc/NNNN-<slug>`.
2. Copy `TEMPLATE.md` to `docs/rfc/NNNN-<slug>.md` and fill it in.
3. Open the PR. Title: `RFC NNNN — <title>`.
4. Discussion happens in PR comments. Update the RFC file in response
   to feedback; the PR is the discussion thread.
5. On merge: status flips from **Draft** to **Accepted** (in the same
   PR; flip it just before the squash-merge, or in a follow-up commit
   if the merge is what triggers the decision).
6. Implementation PRs reference the RFC. When the last implementation
   PR merges, flip status to **Implemented** in a small follow-up.
7. If the design needs to change after Accepted, open a new RFC that
   supersedes the old one rather than editing the old one substantively.
   Minor corrections (typos, dead links) can be edited in place.

---

## Index

_Currently empty. New RFCs land below under their lifecycle bucket._

### Draft

- [RFC 0001 — PlayerVitals vitality-fill model](0001-player-vitals-vitality-fill.md) — _opened 2026-06-13. Inverts the silhouette wash from wound-spreading to vitality-draining; expands the status enum for unconscious vs dead._

### Accepted

_None._

### Implemented

_None._

### Superseded

_None._

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

- **Draft** — Living in conversation / scratch / a local planning file.
  **Not committed.** Design is being discussed and may change shape
  significantly. The Draft stage exists in this project but does NOT
  have a corresponding PR (see "PR workflow" below).
- **Accepted** — The RFC file lands committed, **in the same PR as the
  implementation** (or the first implementation PR if multi-step). The
  design is agreed *and* the diff that fulfills it is on the same
  review surface.
- **Implemented** — The feature has landed and the RFC matches what
  shipped. For single-PR RFCs this happens at the same merge as
  Accepted (so a small RFC can land directly as Implemented). For
  multi-PR RFCs, status flips from Accepted to Implemented when the
  last acceptance criterion checks off. If the implementation
  diverged from the RFC, either update the RFC to match or supersede
  it.
- **Superseded** — A newer RFC (or an ADR) has replaced this one. The
  front matter must link the replacement.

State transitions happen in the same PRs that drive the implementation;
update the front matter of the RFC file itself. The index below gets
refreshed when convenient.

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
about this" notes. It's deliberately low-friction to append to.

RFCs are how a backlog item **graduates** into something that gets
built:

1. An item lives in `BACKLOG.md` until someone (usually Russell) decides
   it's ripe.
2. The next step is **drafting the RFC in conversation** — propose the
   shape, surface alternatives, converge on direction. The RFC content
   takes form here, not in a PR.
3. When direction is set, the RFC file is **created on the
   implementation branch**, alongside the diff that fulfills it. Both
   land in the same PR; status on landing is **Accepted** (or
   **Implemented** if the same PR finishes the work). The BACKLOG
   item can be removed in the same merge — the RFC is now authoritative.

If a backlog item is too small to need an RFC, just do it — the commit
message is the record.

---

## PR workflow

Project Sentinel's RFC convention is **draft-in-conversation, accepted-on-implementation**:
no "Draft RFC NNNN" PRs. The Draft stage lives in the discussion that produced
the design; the RFC file lands committed only when it's ready to be Accepted.

1. **Draft in conversation.** Propose the design inline; iterate
   alternatives, code snippets, tradeoffs. Use a scratch file under
   `~/.claude/plans/<slug>.md` if it's long. **Don't open a PR for the
   draft.**
2. **Pick a number.** The next free integer in `docs/rfc/` (e.g.
   `ls docs/rfc/`). Two designs racing for the same number is fine —
   the second one to land just bumps in their PR.
3. **Land RFC + implementation together.** When direction is set,
   create `docs/rfc/NNNN-<slug>.md` from `TEMPLATE.md` on the
   implementation branch, alongside the code that fulfills it. Open
   one PR. Title: `feat(...): <feature> (RFC NNNN — <slug>)` or similar.
   - For single-PR RFCs (small enough that the whole feature lands at
     once): set `Status: Implemented` directly.
   - For multi-PR RFCs: set `Status: Accepted` on the first
     implementation PR. Each subsequent PR references the RFC by
     number. The last implementation PR flips status to
     **Implemented**.
4. **If the design needs to change after Accepted**, open a new RFC
   that supersedes the old one rather than editing the old one
   substantively. Minor corrections (typos, dead links) can be edited
   in place.

**Exception — the bootstrap.** PR #136 (the PR that introduced this
RFC system) landed `RFC 0001` as `Draft` in a doc-only PR. That was
the one-time bootstrap case: adopting the convention itself without
a paired implementation. RFC 0001 will flip to Accepted / Implemented
when its implementation PR lands. Future RFCs follow the
draft-in-conversation pattern above.

---

## Index

_Currently empty. New RFCs land below under their lifecycle bucket._

### Draft

_None._

### Accepted

_None._

### Implemented

- [RFC 0001 — PlayerVitals vitality-fill model](0001-player-vitals-vitality-fill.md) — _opened 2026-06-13, implemented 2026-06-14. Bottom-up vitality fill (Diablo orb idiom); solid blood, no gradient; status enum expanded to `alive | unconscious | dead | unknown | missing`; skull-and-crossbones pose for dead, humanoid + Zzz caption for unconscious; min-vitality floor of 12 SVG units at HP > 0._
- [RFC 0002 — System messages](0002-system-messages.md) — _opened 2026-06-14, implemented 2026-06-14. Operator-to-cohort broadcast channel; player surface in Settings drawer with gear-dot unread indicator; tailnet-only admin UI at `/admin/messages` (no in-band auth — Caddy topology IS the credential); soft delete + pin + optional expiry; minimal markdown body (*italic*, **bold**, [link](url))._
- [RFC 0003 — Tester guide](0003-tester-guide.md) — _opened 2026-06-16, implemented 2026-06-16. In-app onboarding doc rendered from `docs/alpha/TESTER_GUIDE.md` at `/guide`; entry via HelpCircle icon in TopBar; minimal-markdown renderer extracted from `MessageCard` to `utils/minimalMarkdown.js` and extended with headings, lists, blockquotes, code spans (still safe-scheme link allowlist)._

### Superseded

_None._

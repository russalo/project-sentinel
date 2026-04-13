# Architecture Decision Records

This directory holds the Architecture Decision Records (ADRs) for Project Sentinel.

An ADR is a short, long-lived document that captures **one decision** — the
context that forced it, the options considered, the choice made, and the
consequences that follow. ADRs are append-only: once an ADR is accepted, it
stays in the repo forever, even if a later ADR supersedes it. This preserves
the reasoning trail so future contributors (and future-you) can understand
*why* the system looks the way it does, not just what it looks like today.

## When to write an ADR

Write an ADR when a decision:

- Affects more than one subsystem, or defines how subsystems talk to each other
- Commits the project to a particular technology, data representation, or boundary
- Walks back or re-interprets something the existing docs claim
- Would be hard to reverse once code lands on it
- Took real debate or analysis to reach — the kind of decision where "why did
  we do it this way?" would otherwise get answered by reconstructing a chat log

Do **not** write an ADR for:

- Coding-style choices (those belong in `CONTRIBUTING.md` or linter config)
- One-file refactors with no cross-cutting impact
- Things already documented in `README.md`, `ARCHITECTURE.md`, or `CLAUDE.md`
  unless you're explicitly overriding what they say

When in doubt, err on the side of writing one. ADRs are cheap; reconstructing
lost reasoning is expensive.

## Format

Each ADR lives in its own file named `NNNN-short-kebab-title.md`, where
`NNNN` is a zero-padded four-digit sequence number. Numbers are never reused
and never reordered, even if an ADR is later superseded.

Every ADR opens with a small metadata block:

```markdown
# ADR NNNN — Title in sentence case

**Status:** Proposed / Accepted / Superseded by ADR NNNN / Deprecated
**Date:** YYYY-MM-DD
**Deciders:** names or roles involved in the decision
**Supersedes:** ADR NNNN (if applicable)
```

Followed by these sections, in order:

- **Context** — what's going on in the codebase and what forced the decision
- **Decision drivers** — the values, constraints, and priorities being weighed
- **Options considered** — each viable option, with honest pros and cons
- **Decision** — the chosen option, stated plainly
- **Rationale** — why this option over the others, including anything that
  required analysis or arithmetic rather than just preference
- **Consequences** — what changes as a result, grouped positive / negative / neutral
- **Implementation implications** — concrete follow-up work the decision
  implies, with pointers to `docs/BACKLOG.md` items where appropriate
- **References** — related ADRs, relevant source files, external docs, and
  the conversation or PR that produced the decision

Long-form is the default. These documents are read rarely but deeply, and
terseness rewrites poorly when the context is reconstructed years later.

## Superseding

If a later ADR replaces an earlier one, do NOT delete the earlier one. Set
its status to `Superseded by ADR NNNN`, add a forward-pointer at the top, and
leave the original reasoning intact. A superseded ADR is still a valuable
historical record — it tells you what the project used to believe and why it
changed its mind.

## Index

- [ADR 0001 — `data/` is the canonical source of truth](0001-data-canonical-source-of-truth.md)

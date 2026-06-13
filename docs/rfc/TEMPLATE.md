# RFC NNNN — <Short, declarative title>

**Status:** Draft
**Date:** YYYY-MM-DD
**Author:** <name>
**Implements:** <BACKLOG one-liner verbatim, or "—">
**Supersedes:** <RFC NNNN link, or "—">
**Superseded by:** —

---

## Context

What's true in the codebase right now, and why this RFC exists. Two or
three paragraphs is usually enough. Assume the reader knows the
project; don't re-explain the architecture.

If this RFC was triggered by a specific bug, PR comment, tester
report, or backlog item, name it.

---

## Proposal

The actual design. Be concrete:

- Field names, types, defaults.
- File paths that will be added, changed, or removed.
- Function or endpoint signatures.
- Wire shape (request/response, SSE event payload, schema diff).
- UX shape (component placement, interaction flow) when relevant.

If the proposal touches a schema under `schemas/`, paste the diff or
the new fragment here. If it touches an API contract, show the before
and after.

Snippets are welcome. Pseudo-code is welcome. A diagram is welcome if
it earns its place.

---

## Open Questions

Things you genuinely don't know yet and want feedback on. One question
per bullet. Mark each as resolved (in-place) as the PR discussion
answers them; don't strip them — the resolution is the record.

- [ ] Question one.
- [ ] Question two.

If there are no open questions, write `—` and move on.

---

## Acceptance Criteria

What "Implemented" looks like. Bulleted, testable, ordered roughly by
build sequence.

- [ ] Criterion one.
- [ ] Criterion two.
- [ ] Criterion three.

These get checked off as the implementation PRs land. When all are
checked, flip the RFC status to **Implemented**.

---

## Out of Scope

What this RFC is deliberately *not* committing to. Especially useful
for adjacent work that a reader might assume belongs here.

- Item one.
- Item two.

If nothing is meaningfully adjacent, write `—`.

---

## Cross-links

- Related ADRs: <ADR NNNN, or "—">
- Related RFCs: <RFC NNNN, or "—">
- BACKLOG items: <link or one-liner, or "—">
- PRs: <#NN, filled in as they land>
- Memory: <relevant memory filenames, or "—">

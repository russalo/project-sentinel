# RFC 0003 — Tester Guide (in-app onboarding doc)

**Status:** Implemented
**Date:** 2026-06-16
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** Tester-facing onboarding doc for the closed alpha cohort
**Supersedes:** —
**Superseded by:** —

---

## Context

The closed alpha at `sentinel.russalo.com/alpha/` has been live since
2026-06-07. Testers arriving today get a URL, basic_auth credentials,
and an implicit expectation that the surfaces will explain themselves.
Several recent surfaces (PlayerVitals silhouette, tension meter,
system-messages drawer, two-row action pill rail) need framing the UI
itself can't provide. A handful of visible surfaces are also placeholder
today (Day counter frozen at 1, TopBar seed-share showing hardcoded
`ABC-DEF-GHI-JKL`, DM pill colors all amber, every fantasy race rendering
the human silhouette, permadeath mode having no underlying mechanism).
Without flagging these, testers report them as bugs and the operator
spends triage cycles re-explaining.

A doc audit completed 2026-06-16
(`scratch/tutorial/audit-2026-06-16.md`) classified every visible
surface as **Active** (does something) or **Cosmetic so far** (visible
but not wired up yet). Russell's calibration: testers should see a
binary classification, not the engineer-facing three-tier framing — they
need "this does X, this doesn't do anything yet," not the mechanism.

The doc itself is drafted at `docs/alpha/TESTER_GUIDE.md` (3 sections,
~140 lines, behavior-only). This RFC covers the surface layer — how
testers reach it.

## Proposal

**Source of truth:** committed markdown at `docs/alpha/TESTER_GUIDE.md`.
Single file, lives in the repo, iterated via normal PRs.

**Tester surface:** new SPA route `/alpha/guide` (alias `/guide` on the
tailnet dev hostname via the wouter `Router base`). A new `Guide.jsx`
page imports the markdown as a raw string via Vite's `?raw` import,
renders it with an extended minimal-markdown helper, and displays it in
the codex font + layout used elsewhere in the app.

**Entry point:** new icon in TopBar, between the feedback `MessageSquare`
icon and the settings `Settings` icon. Lucide-react `HelpCircle`. Single
tap, no modal, no popup, no auto-open. Testers discover the guide by
seeing the icon — same UX cost as feedback/settings.

**Renderer extension:** the markdown helper in
`apps/sentinel-ui/src/components/shell/MessageCard.jsx`
(`renderMinimalMarkdown`) handles italic / bold / links today. Extract
it to its own module (`apps/sentinel-ui/src/utils/minimalMarkdown.js` or
similar) and extend with:

- `# heading` / `## heading` / `### heading` — three levels
- `- item` — unordered list (single nesting, no nested lists)
- `> quote` — blockquote (the "Cosmetic so far" callouts in the guide)
- `` `code` `` — inline code spans

Preserve the existing safe-scheme allowlist (`http`, `https`, `mailto`
only; `javascript:` / `data:` / `file:` rendered as text). The same
extended helper continues to back `MessageCard` so the message-card
markdown stays consistent and the renderer is tested in one place.

**No backend changes.** No new endpoints. Markdown is bundled into the
SPA at build time via the `?raw` import — same gate as the rest of the
app (basic_auth at the edge / topology on tailnet).

**No persistence.** No "I read this" acknowledgement, no localStorage
flag, no read-state. The doc is short enough that a tester can re-read
it on demand; tracking adds friction without value.

## Resolved Questions

Resolved by Russell 2026-06-16:

1. **Single-source vs build-copy → Vite `?raw` import.** No build-time
   copy step. The Vite config (`vite.config.js`) will need its
   `server.fs.allow` (and equivalent for build) extended to include the
   repo root so the SPA can import
   `../../docs/alpha/TESTER_GUIDE.md?raw`. If `fs.allow` proves brittle
   in build mode, fall back to a symlink inside
   `apps/sentinel-ui/src/content/`, but the source of truth stays at
   `docs/alpha/`.

2. **Icon placement → recommended (between feedback and settings).**
   `HelpCircle` from `lucide-react`, `aria-label="Tester guide"`,
   `title="Tester guide"`. **Forward-looking note:** if the TopBar icon
   cluster gets crowded as more features land, the guide entry may
   migrate into the settings drawer (alongside the Messages section
   shipped in RFC 0002). The `/guide` route remains; only the surface
   point of entry changes. Not blocking; revisit when the next icon
   contends for space.

3. **Mobile layout → Russell verifies on device.** No special mobile
   work assumed in the implementation; layout is plain markdown-in-a-
   column. Russell will confirm during review and any tweaks land as
   follow-up commits on the same branch before merge.

## Acceptance Criteria

- [ ] `docs/alpha/TESTER_GUIDE.md` lands in the repo (already drafted)
- [ ] `?` icon (`HelpCircle`) added to TopBar between feedback and
      settings, with `aria-label="Tester guide"`
- [ ] New SPA route `/guide` (resolves to `/alpha/guide` on the public
      build via the wouter `Router base`)
- [ ] `Guide.jsx` page renders the markdown with headings, lists,
      blockquotes, code spans, and the existing italic/bold/link
      behavior
- [ ] Unsafe URL schemes refused by the renderer (test coverage in the
      existing `MessageCard.test.jsx` extended for the new shapes; or
      moved to `minimalMarkdown.test.js` if the helper is extracted)
- [ ] Renderer is the single source — `MessageCard` and `Guide` import
      the same `renderMinimalMarkdown`
- [ ] Page is fully readable on a mobile viewport (≤375px wide); the
      narrow screen does not cause horizontal scroll
- [ ] Doc surfaces "Cosmetic so far" blocks visually (the blockquote
      styling is enough; no special background)
- [ ] RFC 0003 file (`docs/rfc/0003-tester-guide.md`) lands as
      **Implemented** in the same PR
- [ ] `docs/rfc/README.md` index updated to list RFC 0003 in the
      Implemented bucket

## Out of Scope

- **Interactive in-product tour** with tooltip overlays or guided
  walkthroughs. The doc is enough for the alpha; revisit if testers
  ask.
- **First-load auto-popup / onboarding modal.** Deliberately rejected —
  forced modals don't suit a small invited cohort.
- **Per-section anchor links / table of contents.** The doc is short
  enough not to need them.
- **Multi-language.** English-only for the alpha.
- **Operator edit-in-app.** Guide is edited via PR; not an admin surface.
- **Fixing the cosmetic-so-far items** (Day counter freeze, seed-share
  hardcoded display, DM pill tone rendering, race-keyed silhouette art,
  permadeath mechanism). Each is its own BACKLOG entry; this RFC only
  documents them honestly. The doc gets revised as those items land.
- **Replacing the existing `MessageCard.jsx` markdown helper.** This
  RFC extracts and extends it; it does not introduce a markdown library
  dependency (still ~80 lines of hand-written regex). Adopting
  `react-markdown` or similar is a separate decision.

## Cross-links

- Doc draft: `docs/alpha/TESTER_GUIDE.md` (drafted 2026-06-16, in repo)
- Audit that drove the doc: `scratch/tutorial/audit-2026-06-16.md`
  (gitignored snapshot — re-verify before relying on it months from now)
- Sibling pattern: `docs/rfc/0002-system-messages.md` (in-app surface,
  gated by SPA bundle, no in-band auth, minimal markdown body)
- Existing renderer: `apps/sentinel-ui/src/components/shell/MessageCard.jsx`
  (`renderMinimalMarkdown`)
- BACKLOG entries for the items the guide flags as cosmetic-so-far:
  - DM pill tone restoration with player legend (line 699)
  - Day counter wiring (no entry yet — graduate from the audit)
  - Seed-share TopBar hookup (no entry yet — graduate from the audit)
  - Per-race silhouette art (no entry yet — graduate from the audit)
  - Permadeath mechanism (no entry yet — graduate from the audit)

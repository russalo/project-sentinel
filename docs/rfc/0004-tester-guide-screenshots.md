# RFC 0004 — Tester Guide screenshots + renderer extensions

**Status:** Implemented
**Date:** 2026-06-16
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** Annotated screenshots for the tester guide; renderer extensions
**Supersedes:** —
**Superseded by:** —

---

## Context

RFC 0003 landed the tester guide as a text-only doc rendered in-app at
`/guide`. Russell's calibration during the doc draft: every visible
button and field needs to be called out by letter-coded markers on
screenshots, not just described in prose. Two motivations:

- A diagram-with-legend reads faster than walls of bulleted text.
- The doc audit (`scratch/tutorial/audit-2026-06-16.md`) surfaced a
  handful of "cosmetic so far" surfaces (Day counter, hardcoded seed
  display, DM pill colors, race-stub silhouette, permadeath mechanism).
  Letter-coded annotations let those be flagged on the screenshot
  itself, not just in prose.

The 2026-06-15 bot review of RFC 0003 (gemini-code-assist + codex) also
left three real findings the renderer needed to address before we layered
more on:

- Lexicographic odd-index loophole in `renderEmphasis` and
  `renderCodeAndEmphasis` (literal markers in non-match text could in
  principle false-positive)
- The tokenizer ended lists at the first non-`- ` line — but the doc
  draft used wrapped continuations
- Ordered lists (`1.` `2.`) weren't recognized at all, so the "Taking a
  turn" section would render as prose paragraphs with literal-number
  prefixes

This RFC bundles those three fixes with the new surface so the renderer
extensions land in one coherent unit.

## Proposal

**Annotated-screenshot pipeline**

- `scripts/src/screenshot-guide.mjs` — Playwright (Chromium) script.
  Per-screen config: `{url, waitFor, prep, annotations: [{key, selector,
  label, placement}]}`. The script navigates, optionally pre-seeds form
  state or store data, injects an SVG overlay layer with amber-circled
  letters at each selector's bounding box, and snaps a full-page PNG to
  `apps/sentinel-ui/public/guide/<name>.png`.
- Four screens covered: `creation`, `worlds-list`, `game`, `settings`.
  The `game` and `settings` screens use Russell's actual `Trog` world
  (`2097371f-…`) for real persisted state.
- `placement` per annotation: `'top-left'` (default), `'below'`,
  `'above'`, `'right'`. TopBar icons use `'below'` because the 36px
  circle covers the 18px icons at top-left.
- Dev-mode handle `window.__sentinelStores` (Vite-tree-shaken in prod)
  lets the script populate the ephemeral `chatStore.suggestedActions`
  field so the DM pill rail is visible in the `game` screenshot.
- One-time setup for new contributors: `pnpm install` and `npx
  playwright install chromium`. Documented in the script's header.

**Renderer extensions** (in `apps/sentinel-ui/src/utils/minimalMarkdown.jsx`)

- `![alt](path)` image markdown. Paths are resolved against
  `import.meta.env.BASE_URL`, so `![](guide/x.png)` works on both `/`
  and `/alpha/` builds without rewriting.
- Auto-anchor IDs on `#`, `##`, `###` headings — slugified from text
  (lowercase, strip punctuation, collapse whitespace to dashes).
  Duplicate slugs get `-1`, `-2`, etc. suffixes.
- `[label](#anchor)` in-page anchor links — no `target="_blank"`, no
  scheme-allowlist check (anchors are always safe).
- `{{toc}}` block marker — expands at render time to a `<nav>` with one
  `<li><a>` per `##` heading in document order. `#` (title) and `###`
  (subsection) excluded to keep the TOC scannable.
- Ordered list support (`1. item`, `2. item`) → `<ol>`.
- Wrapped list continuations: an indented non-marker line under the
  most recent list item is appended to that item with a space separator.
  Applies to both `<ul>` and `<ol>`.
- Odd-index defensive check: when `String.split(EMPHASIS_RE)` returns
  alternating non-match / match parts, only the odd-indexed (matched)
  parts are inspected for emphasis wrapping. Same for code spans. The
  even-indexed text segments pass through verbatim.

**Doc rewrite** (`docs/alpha/TESTER_GUIDE.md`)

- Restructured to per-screen sections matching the four screenshots.
- Each section: `![alt](guide/<name>.png)` + a lettered bullet list (A,
  B, C, …) keyed to the markers in the image.
- `{{toc}}` placed near the top so testers can jump straight to the
  screen they want help with.
- "Cosmetic so far" callouts use blockquote markdown — visually
  distinct as amber-left-border italic text.

**TopBar icon placement decision** (resolved 2026-06-16)

- The HelpCircle `?` icon stays between feedback and settings as
  shipped in RFC 0003. No move to drawer for v2 of this RFC.

## Resolved Questions

Resolved by Russell across the 2026-06-16 implementation session:

1. **Granularity** — per-screen, lettered circles on every element,
   matching text legend below.
2. **Screenshot authoring** — Playwright bundled Chromium on origin-core
   (already in the Playwright cache). Script + PNGs both checked in.
3. **State source for HUD shots** — real Trog world via the local
   backend (rather than mocked API responses). The script depends on
   that world existing on the local backend; flagged in the script
   header so a future operator knows what to update if the world is
   deleted.
4. **Vite raw import** — `apps/sentinel-ui/vite.config.js`'s
   `server.fs.allow` extended to include the repo root (shipped in RFC
   0003).
5. **TopBar marker placement** — letters placed BELOW the icons rather
   than top-left, since a 36px circle covers an 18px icon.

## Acceptance Criteria

- [x] `scripts/src/screenshot-guide.mjs` runs end-to-end and produces
      four annotated PNGs at `apps/sentinel-ui/public/guide/{creation,
      worlds-list, game, settings}.png`.
- [x] Renderer supports `![alt](path)`, heading anchor IDs, in-page
      anchor links, `{{toc}}` marker, ordered lists, wrapped-list
      continuations.
- [x] Odd-index defensive check applied to emphasis and code-span
      rendering (PR #140 bot finding regressions closed).
- [x] `docs/alpha/TESTER_GUIDE.md` restructured to per-screen format,
      `{{toc}}` placed near the top, blockquote callouts for the
      cosmetic-so-far items.
- [x] 271+ SPA tests pass with new coverage for image markdown, anchor
      IDs, in-page links, ordered lists, wrapped continuations, and
      `{{toc}}` rendering.
- [x] RFC 0004 lands as **Implemented** in the same PR.
- [x] `docs/rfc/README.md` index updated.
- [ ] Russell verifies the rendered guide on mobile during PR review;
      any tweaks land as follow-up commits on this branch before merge.

## Out of Scope

- **Mocked API responses for HUD screenshots.** We use the real Trog
  world; mocking the full world-hydration response shape was deferred
  to keep the script small. If Trog ever goes away the script will
  break loudly; that's the documented signal to update the UUID or
  add a fixture world.
- **Interactive walkthrough / tooltip overlays.** Same scope-out as
  RFC 0003 — the doc + screenshots are enough for the alpha.
- **Multiple viewport sizes.** Single desktop viewport (1280×900) only;
  mobile layout is verified by hand during PR review, not by the
  script.
- **Migrating the HelpCircle into the settings drawer.** Forward-looking
  note in RFC 0003 still stands; revisit when the TopBar icon cluster
  contends for space.
- **Fixing any of the cosmetic-so-far surfaces flagged in the doc.**
  Each is its own BACKLOG entry; the guide gets revised as those land.

## Cross-links

- Doc: `docs/alpha/TESTER_GUIDE.md`
- Renderer: `apps/sentinel-ui/src/utils/minimalMarkdown.jsx` + its
  tests at `apps/sentinel-ui/src/utils/minimalMarkdown.test.jsx`
- Screenshot script: `scripts/src/screenshot-guide.mjs`
- Generated PNGs: `apps/sentinel-ui/public/guide/{creation,worlds-list,
  game,settings}.png`
- Sibling: `docs/rfc/0003-tester-guide.md` (the RFC that introduced
  the guide; this RFC layers screenshots + renderer extensions on top)
- Audit that drove both RFCs: `scratch/tutorial/audit-2026-06-16.md`
  (gitignored)
- BACKLOG candidates flagged on screenshots (already in the doc's
  cosmetic-so-far callouts):
  - Day counter wiring
  - TopBar seed-share hookup
  - DM pill tone restoration with player legend (line 699 of BACKLOG)
  - Per-race silhouette art
  - Permadeath mechanism

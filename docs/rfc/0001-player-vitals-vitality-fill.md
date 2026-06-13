# RFC 0001 — PlayerVitals vitality-fill model

**Status:** Draft
**Date:** 2026-06-13
**Author:** Russell Pfister (design decisions); drafted by Claude subagent
**Implements:** `docs/BACKLOG.md` § "Invert PlayerVitals fill metaphor: vitality-remaining (red), not damage-taken (red)"
**Supersedes:** —
**Superseded by:** —

---

## Context

The HP silhouette shipped across PRs #127–#132 currently uses a **wound-spreading**
fill: a `<rect>` clipped to the body, anchored at `y=0`, whose height grows from
the top down as HP drops. At HP=100 the silhouette is an empty outline; at HP=0
it is fully washed red. The wash itself is a `<radialGradient>` (`#8c3a3a` core
fading to `#c9973a` at the edges), with intensity stepped per band on top of the
geometric fill.

Russell loaded the v3 component at HP=55 and surfaced a **mental-model
mismatch**: the rect-growing-from-the-head idiom reads as "the wound is
spreading" (a *negative*-space metaphor — damage gains territory), but the
intuition every game UI has trained for two decades is the **Diablo orb**
(*positive*-space metaphor — vitality is a vessel that drains from the top).
A 55%-full vessel says "you have 55 left"; a 45%-tall wound stain says "you
have lost 45." Same number, opposite emotional read. The 55-state screenshot
read as "barely scratched" when it should have read as "more than half gone."

What's already in place and stays:

- The clip-path + style-driven CSS height transition from PR #131. The
  browser-animation plumbing is correct; only the math, the rect's `y`, and the
  gradient choice change.
- The shared `HUMAN_BODY_PATH` constant feeding both the `<clipPath>` and the
  visible outline (per [[feedback_visual_iteration_inline_svg]] — single source
  of truth so the wash can never escape the silhouette).
- The race dispatch `RACE_BODIES` from PR #129.

What flips:

- Fill direction (top-down → bottom-up).
- Fill style (radial gradient → solid blood).
- Status enum (binary alive/dead → ternary alive/unconscious/dead, plus the
  existing `unknown`/`missing` placeholder states).
- Minimum-floor behavior at very low HP.

## Proposal

### 1. Top-down drain (Diablo orb idiom)

Vitality fills the body from the **feet up**. The damaged region — the part
*missing* the wash — sits at the top. **`vitalityY` is derived from the
floored vitality height** (see section 4), not the raw proportional value —
otherwise at the floor cliff (HP=1) the rect's `y` and `height` disagree by a
few SVG units and the rect overflows the bottom of the viewport.

```js
const SVG_HEIGHT = 180;
// vitalityHeightFor() applies the floor + status overrides; see section 4.
const vitalityHeight = vitalityHeightFor(hp, status);
const vitalityY = SVG_HEIGHT - vitalityHeight; // anchor at the bottom
```

```jsx
<rect
  x="0"
  width="100"
  fill={BLOOD}
  clipPath="url(#vitals-body-clip)"
  style={{
    y: vitalityY,
    height: vitalityHeight,
    transition: 'y 400ms, height 400ms',
  }}
/>
```

At HP=100 the rect is full-height, full-width inside the clip. At HP=55 the
**bottom 55%** of the silhouette is red, the **top 45%** is empty outline. At
HP=0 the rect is collapsed and the silhouette is hollow.

### 2. Solid fill, no gradient

Drop `<radialGradient id="vitals-damage">` entirely. The fill is a single flat
token — the project's blood palette `#8c3a3a` — across the whole vitality
region.

```js
const BLOOD = '#8c3a3a'; // project blood-palette token
```

Per-band opacity stepping (`washOpacityFor`) goes away with the gradient. A
single saturated red reads cleanly against the codex background without
needing intensity modulation; the *area* of the fill is now doing the work the
intensity-stepping was trying to do (and doing it badly — see the original
HP=55 screenshot).

### 3. Three body geometries dispatched by status

The status enum expands from binary to ternary at the rendering layer.
PlayerVitals dispatches one of **three** body paths based on `player.status`:

- `alive` → `HUMAN_BODY_PATH` (the standing silhouette already in the file).
- `unconscious` → `UNCONSCIOUS_BODY_PATH` (downed but recoverable — saving
  throw, healing, time can revive).
- `dead` → `DEAD_BODY_PATH` (terminal; no in-game path back).

```js
function bodyPathFor(race, status) {
  // Case- and whitespace-tolerant status compare — DM emits vary
  // ('Dead' vs 'DEAD' vs ' dead '). PR #132 already shipped this
  // normalization pattern for the existing `isDead` check; keep it
  // consistent here.
  const s = typeof status === 'string' ? status.trim().toLowerCase() : '';
  if (s === 'dead') return DEAD_BODY_PATH;
  if (s === 'unconscious') return UNCONSCIOUS_BODY_PATH;
  return raceBody(race); // existing RACE_BODIES dispatch
}
```

Per-race art is **not** dispatched for unconscious / dead in v1 — both poses are
single shared paths, in the same stub-then-content shape `RACE_BODIES` already
uses. Race-specific downed/dead variants slot in later without re-architecting.

**The pose ARTWORK for unconscious and dead is deferred** (Open Question
below). This RFC scopes the **dispatch** and the **status-enum expansion**
only.

### 4. Minimum vitality floor

At HP=1 a strict `(hp/100) * 180` yields `1.8` SVG units — a sliver the eye
cannot resolve against a 180-unit body. The component would visually hit zero
before HP did, lying about a still-conscious character.

Hold a floor at HP > 0:

```js
const MIN_VITALITY_HEIGHT = 12; // SVG units; thin strip at the feet
function vitalityHeightFor(hp, status) {
  // Same normalization as bodyPathFor (above) — single helper in the
  // implementation, here inlined for clarity.
  const s = typeof status === 'string' ? status.trim().toLowerCase() : '';
  if (s === 'dead' || s === 'unconscious') return 0;
  if (hp <= 0) return 0;
  const proportional = (hp / 100) * SVG_HEIGHT;
  return Math.max(MIN_VITALITY_HEIGHT, proportional);
}
```

Plain-language guarantee: **even at HP=1, the player can see they have
SOMETHING left.** The floor only releases when HP literally hits 0 OR status
flips to `unconscious` / `dead`.

## Open Questions

These are the only two:

1. **What do the unconscious and dead poses look like?** A horizontal supine
   silhouette is the obvious starting point for both; what distinguishes them
   visually — a slumped-vs-prone curve, an opacity drop, a small visual
   marker — is undecided. Deferred to a follow-on visual-iteration PR after
   the dispatch lands (this is the BACKLOG-able art task, mirroring the
   per-race authoring split). Status colors / band labels for these states
   also fall here.

2. **Exact spelling of the unconscious status string the DM emits.** Candidates:
   `"unconscious"`, `"downed"`, `"incapacitated"`, `"knocked out"`. The
   case-insensitive `statusStr` normalization already in PlayerVitals handles
   casing; the question is the canonical lexeme to commit to in the DM prompt
   + Fact-Extractor schema. Resolving this requires a one-line decision from
   Russell + an engine-prompt update; the rendering side accepts whatever
   spelling lands.

## Acceptance Criteria

**Tests** (extend `PlayerVitals.test.jsx`):

- HP=100, alive → vitality rect height = 180, y = 0; no gradient `<def>` in the
  rendered SVG.
- HP=55, alive → vitality rect height = 99, y = 81 (bottom 55%, top 45% empty).
- HP=1, alive → vitality rect height = `MIN_VITALITY_HEIGHT` (12), y = 168 (the
  floor is held).
- HP=0, alive → vitality rect height = 0 (silhouette fully empty, no floor).
- status=`unconscious` → renders `UNCONSCIOUS_BODY_PATH`; vitality height = 0;
  band label distinct from `dead`.
- status=`dead` → renders `DEAD_BODY_PATH`; vitality height = 0; band label
  `Fallen` (or whatever the open question resolves).
- Status casing variants (`Dead`, `UNCONSCIOUS`, `Unconscious`) all normalize
  correctly.

**Visual** (Russell-eye check on the alpha):

- HP=55 reads as **"more than half full"**, not "barely scratched."
- HP=1 is unmistakably non-empty (the floor strip is visible at the feet).
- HP=0-alive (a transient before status flips) reads as empty-but-standing,
  distinct from `unconscious` (downed pose) and `dead` (terminal pose).

## Out of Scope

- **Per-race silhouettes for the unconscious / dead poses.** Single shared path
  per pose in v1; per-race variants are a follow-on stub-then-content step.
- **Core Systems death-stakes spec.** What HP=0 *mechanically* means
  (save-vs-die, permadeath flag enforcement, revival rules) is filed under
  Core Systems → Fantasy Flagship in `docs/BACKLOG.md` and is independent of
  the rendering decision here. This RFC commits only to *visualizing* the
  three states.
- **Audio cues** on state transitions (vitality crossing a band threshold,
  the unconscious / dead pose flip). Distinct surface.
- **Healing animation direction.** Restoring HP fills the rect upward
  symmetrically by the same math; no separate spec needed.

## References

- `apps/sentinel-ui/src/components/world-state/PlayerVitals.jsx` — the
  component this RFC modifies.
- PRs #127, #128, #129, #130, #131, #132 — the inline-SVG silhouette,
  per-band opacity, race-dispatch stub, mobile-layout fix, style-driven
  height animation, and most recent wound-spread tuning.
- `docs/BACKLOG.md` — "Core Systems — Fantasy as Flagship Model" → "Death
  stakes" sub-bullet; "Author race-specific silhouette geometries" (per-race
  authoring this RFC's pose dispatch mirrors).
- [[feedback_visual_iteration_inline_svg]] — inline-SVG + shared-path-constant
  + stub-then-content pattern this RFC adheres to (geometry stays inline; the
  pose dispatch is a stub-then-content split; PR body should call out
  iteration knobs).
- `docs/adr/README.md` — RFC formatting follows the ADR shape, lighter.

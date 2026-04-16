# Plan: Turn UX — Entity Name Highlights + Suggestion Pills

## Context

Two features surfaced during the 2026-04-14 smoke test that make the
narrative feel like a game rather than a chat window:

1. **Entity name highlights** — DM prose is plain text; known character,
   location, and faction names should be visually distinct and clickable
   to open the entity card. Pure frontend, no backend changes.

2. **Action suggestion pills** — The DM always ends turns with implied
   choices buried in prose. Surfacing them as clickable pills that fill
   the command bar gives the player a clear action vocabulary without
   forcing free-form typing. Requires one prompt addition; the backend
   SSE passthrough already handles unknown fields in `<world_update>`.

---

## Branch

`feat/turn-ux-narrative-enhancements`

---

## Deliverables

### 1 — `src/utils/highlightEntities.js` (new)

Pure function, no React, no store imports.

```js
/**
 * Split `text` into plain and highlighted segments.
 *
 * @param {string} text
 * @param {{ name: string, type: string }[]} namedEntities
 * @returns {{ text: string, entity: { name: string, type: string } | null }[]}
 */
export function highlightEntities(text, namedEntities) { ... }
```

Rules:
- Filter out names shorter than 3 chars (avoids matching pronouns / common words)
- Sort remaining names by length descending before building the regex —
  ensures "The Breach" matches before "Breach" in overlapping cases
- Build one `RegExp` with alternation, `gi` flags, `\b` word-boundary anchors
- Split text on matches; preserve original casing in the rendered span
- Return `[{ text, entity: null }, { text, entity: { name, type } }, ...]`
- If `namedEntities` is empty or produces no matches, return
  `[{ text, entity: null }]` (no-op)

### 2 — `src/components/narrative/HighlightedText.jsx` (new)

```jsx
// Props: { text: string, className?: string }
export function HighlightedText({ text, className }) { ... }
```

- Reads `characters`, `locations`, `factions` from `useWorldStore`
- Builds entity list with singular type keys to match `PanelRouter`:
  `characters → 'character'`, `locations → 'location'`, `factions → 'faction'`
  (items excluded — item names in prose are rarely unambiguous enough to
  highlight safely; can be added later)
- Calls `highlightEntities(text, entities)` → segments
- Renders plain segments as text, highlighted segments as:
  ```jsx
  <button
    className="text-amber underline decoration-dotted cursor-pointer hover:text-amber/80"
    onClick={() => setSelectedEntity({ name }, type)}
  >
    {segment.text}
  </button>
  ```
  `setSelectedEntity(entity, type)` signature matches `uiStore.js:17` —
  first arg is object with `.name`, second is type string. Calling it also
  sets `rightPanelCollapsed: false` (already wired in the store).
- Falls back gracefully when `worldStore` is empty (session not started):
  just renders the plain text div.

### 3 — `src/components/narrative/NarrativeScroll.jsx` (modified)

Single line change in the `dm` message renderer:

```jsx
// Before:
<div className="text-ink font-crimson leading-relaxed prose-narrative">
  {msg.content}
</div>

// After:
<HighlightedText
  text={msg.content}
  className="text-ink font-crimson leading-relaxed prose-narrative"
/>
```

No other changes to `NarrativeScroll`.

---

### 4 — `engine/prompts/dm.py` (modified)

Add `suggestedActions` to the FORMAT block inside `DM_SYSTEM_PROMPT`,
after the `items` array:

```json
"suggestedActions": [
  {"label": "short imperative phrase ≤40 chars", "tone": "aggressive|defensive|clever|cautious|social"}
]
```

Add one rule line:

```
- Always include 2–4 suggestedActions reflecting the player's most
  natural next moves. Labels are short imperative phrases (≤40 chars).
  Tone is optional but helps the frontend style the pill.
```

No other backend changes. `_parse_frontend_hint` in `backend/routes/stream.py`
already returns the full parsed `<world_update>` dict; unknown fields (including
`suggestedActions`) pass through to the frontend automatically.

### 5 — `src/stores/worldStore.js` (modified)

Two additions:

```js
// Initial state
suggestedActions: [],

// In applyUpdate(), after the items block:
next.suggestedActions = worldUpdate.suggestedActions ?? [];

// New action
clearSuggestedActions: () => set({ suggestedActions: [] }),
```

`applyUpdate` overwrites `suggestedActions` on every `world_update` event,
so a DM that omits the field silently clears the pills — no stale state.

### 6 — `src/components/shell/CommandBar.jsx` (modified)

Two additions:

**Read from store:**
```js
const { suggestedActions, clearSuggestedActions } = useWorldStore(
  (s) => ({ suggestedActions: s.suggestedActions, clearSuggestedActions: s.clearSuggestedActions })
);
```

**Call clear on submit:**
```js
clearSuggestedActions();
```
added inside `handleSubmit` after `sendAction(action, sessionId)`.

**Pill row** rendered inside the `<footer>`, above the input row, only
when pills exist and streaming is not active:

```jsx
{suggestedActions.length > 0 && !isStreaming && (
  <div className="flex flex-wrap gap-2 pb-2">
    {suggestedActions.map((sa, i) => (
      <button
        key={i}
        onClick={() => setInput(sa.label)}
        className="px-3 py-1 text-xs rounded-full border border-border
                   text-ether hover:text-ink hover:border-amber transition-colors"
      >
        {sa.label}
      </button>
    ))}
  </div>
)}
```

Clicking fills `input` state; player still reviews and submits manually.
Pills disappear the moment the player hits Enter (cleared by `handleSubmit`)
and reappear after the next `[DONE]` if the DM emits them.

Tone → pill colour is deferred. The neutral pill style above is
consistent with the design system and works for all tones. Tone-based
colouring can be a quick followup if it reads well in practice.

---

## Tests

### `src/utils/highlightEntities.test.js` (new)

| Test | What it guards |
|---|---|
| empty entity list → one plain segment | no-op path |
| single entity, one match → three segments | basic split |
| entity name at start of string | no leading plain segment |
| entity name at end of string | no trailing plain segment |
| case-insensitive match | "russalo" matches entity "Russalo" |
| longest name matches first | "The Breach" not split into "The" + "Breach" |
| name < 3 chars is skipped entirely | short-name guard |
| partial word not matched ("cat" in "catch") | word-boundary guard |
| unknown name not highlighted | non-entity text stays plain |
| multiple entities in one string | all matched, correct types |

### `src/components/shell/CommandBar.test.jsx` (new)

| Test | What it guards |
|---|---|
| no pills when `suggestedActions` is empty | default state |
| pills render with correct labels | basic render |
| pills hidden when `isStreaming` is true | in-flight guard |
| clicking a pill sets the input value | fill-not-submit contract |
| submitting clears pills | `clearSuggestedActions` called |

---

## File summary

| File | Action |
|---|---|
| `engine/prompts/dm.py` | Add `suggestedActions` to FORMAT + one rule |
| `apps/sentinel-ui/src/stores/worldStore.js` | Add field + applyUpdate handler + clear action |
| `apps/sentinel-ui/src/components/shell/CommandBar.jsx` | Add pill row + clear on submit |
| `apps/sentinel-ui/src/components/narrative/NarrativeScroll.jsx` | Swap dm renderer to `HighlightedText` |
| `apps/sentinel-ui/src/utils/highlightEntities.js` | New — pure highlight utility |
| `apps/sentinel-ui/src/components/narrative/HighlightedText.jsx` | New — highlight render component |
| `apps/sentinel-ui/src/utils/highlightEntities.test.js` | New — 10 unit tests |
| `apps/sentinel-ui/src/components/shell/CommandBar.test.jsx` | New — 5 unit tests |

8 files. No schema changes. No new backend routes. One Python prompt edit.

---

## Not in scope

- Tone-based pill colouring (deferred — try neutral first)
- Item name highlights (too noisy; revisit after testing character/location/faction)
- `suggestedActions` in session-start turn (intro response uses a different
  code path; pills only appear after the first gameplay turn)
- System Log Phase 2 backend hydration (separate backlog item)
- EntityCard diff mode / card pulsing (separate backlog item)

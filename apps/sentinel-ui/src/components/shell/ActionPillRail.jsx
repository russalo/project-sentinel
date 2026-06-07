// ActionPillRail — clickable action suggestions sitting above the command bar.
//
// Two sources, stacked as separate rows:
//   - DM-emitted, per-turn (`suggestedActions: [{label, tone}]` from the
//     `world_update` SSE event). All rendered in amber to match the inline
//     `<action>` highlights in NarrativeText — same visual = same mechanism.
//     The DM-emitted `tone` field is still parsed and persisted in the
//     `world_update` block, but is NOT visualized today (decided 2026-06-07
//     with Russell: dropped for v1, deferred until we can convey color
//     meaning to the player via a legend / tooltip — BACKLOG entry filed).
//   - Always-available, frontend-rule-based ("Look around", "Wait", "Rest",
//     "Inventory"). Visible every turn so the player always has options even
//     when the DM forgets to emit suggestions. Neutral styling — reads as a
//     permanent extension of the command bar.
//
// Click behavior on EITHER source: types the label into the command bar
// input (via chatStore.setInput). Does NOT auto-submit — the player reviews
// + can edit before sending. Same contract as the inline `<action>` highlights
// in NarrativeText, so all three surfaces feel like one mechanism.
//
// Fallback when nothing's suggested: only the always-available rail is shown.

import { useChatStore } from '../../stores/chatStore';

// Static rule-based suggestions. Kept here rather than in a separate config
// file because the list is short and visually-coupled (this rail is the only
// place that renders them). Add cautiously — every pill takes screen space.
const ALWAYS_AVAILABLE = ['Look around', 'Wait', 'Rest', 'Inventory'];

// DM pills: amber to match the inline `<action>` highlights in NarrativeText.
// Always-available pills: neutral — reads as a default chrome element.
// Both share the same shape (rounded-full border pill); only the color
// changes so the rails are visually separable but consistent.
const DM_PILL_CLASS = 'border-amber/60 text-amber hover:bg-amber/10';
const ALWAYS_AVAILABLE_CLASS = 'border-border text-dust hover:bg-codex';

export function ActionPillRail() {
  const setInput = useChatStore((state) => state.setInput);
  const suggestedActions = useChatStore((state) => state.suggestedActions);

  // Deduplicate DM suggestions against always-available labels (case-insensitive)
  // — if the DM suggests "Look around" we render it ONCE, as the always-available
  // pill (so the visual placement is stable across turns).
  //
  // Defensively validate each entry is `{label: string, …}` BEFORE calling
  // .toLowerCase() — the LLM occasionally emits malformed shapes (label as
  // number, null, or a nested object) and we shouldn't TypeError-crash the
  // pill rail and take the whole turn UI down with it. (gemini HIGH on PR #112.)
  const alwaysAvailableLabels = new Set(
    ALWAYS_AVAILABLE.map((label) => label.toLowerCase()),
  );
  const dmPills = (suggestedActions || []).filter(
    (a) =>
      a &&
      typeof a === 'object' &&
      typeof a.label === 'string' &&
      a.label.length > 0 &&
      !alwaysAvailableLabels.has(a.label.toLowerCase()),
  );

  // Two stacked rows: DM-sourced pills on top (per-turn, amber to match
  // the inline action highlights, collapsed when there are none),
  // always-available pills below (static baseline — same set every turn,
  // neutral chrome styling so they read as a permanent extension of the
  // command bar rather than as DM output). Russell's UX feedback
  // 2026-06-07: the previous single-row tone-rainbow mix made it hard to
  // distinguish turn-specific suggestions from defaults, and color
  // meaning wasn't conveyed to the player anyway.
  const PILL_CLASSES = 'px-2.5 py-1 rounded-full border text-xs font-crimson transition-colors focus:outline-none focus:ring-1 focus:ring-amber';

  return (
    <div className="px-3 lg:px-6 pt-2 pb-1">
      {dmPills.length > 0 && (
        <div
          className="flex flex-wrap gap-1.5 mb-1.5"
          role="group"
          aria-label="DM-suggested actions"
        >
          {dmPills.map((action, i) => (
            <button
              key={`dm-${i}-${action.label}`}
              type="button"
              onClick={() => setInput(action.label)}
              className={`${PILL_CLASSES} ${DM_PILL_CLASS}`}
              aria-label={`Suggested action: ${action.label}`}
              title={action.label}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
      <div
        className="flex flex-wrap gap-1.5"
        role="group"
        aria-label="Always-available actions"
      >
        {ALWAYS_AVAILABLE.map((label) => (
          <button
            key={`always-${label}`}
            type="button"
            onClick={() => setInput(label)}
            className={`${PILL_CLASSES} ${ALWAYS_AVAILABLE_CLASS}`}
            aria-label={`Always-available action: ${label}`}
            title={label}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

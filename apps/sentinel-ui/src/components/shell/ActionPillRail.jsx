// ActionPillRail — clickable action suggestions sitting above the command bar.
//
// Two sources:
//   - Always-available, frontend-rule-based ("Look around", "Wait", "Rest",
//     "Inventory"). Visible every turn so the player always has options even
//     when the DM forgets to emit suggestions. Neutral styling.
//   - DM-emitted, per-turn (`suggestedActions: [{label, tone}]` from the
//     `world_update` SSE event). Tone-colored. Refreshed every turn.
//
// Click behavior on EITHER source: types the label into the command bar
// input (via chatStore.setInput). Does NOT auto-submit — the player reviews
// + can edit before sending. Same contract as the inline `<action>` highlights
// in NarrativeText, so the two surfaces feel like one mechanism.
//
// Fallback when nothing's suggested: only the always-available rail is shown.

import { useChatStore } from '../../stores/chatStore';

// Static rule-based suggestions. Kept here rather than in a separate config
// file because the list is short and visually-coupled (this rail is the only
// place that renders them). Add cautiously — every pill takes screen space.
const ALWAYS_AVAILABLE = [
  { label: 'Look around', tone: 'neutral' },
  { label: 'Wait', tone: 'neutral' },
  { label: 'Rest', tone: 'neutral' },
  { label: 'Inventory', tone: 'neutral' },
];

// Tone → Tailwind classes for the DM-emitted pills. Neutral palette is used
// for both always-available pills (no DM source) and DM pills that emit an
// unknown tone (defense against prompt drift). The amber/accent color matches
// the inline `<action>` highlight in NarrativeText so the click affordance
// reads as the same mechanism on both surfaces.
const TONE_CLASSES = {
  aggressive: 'border-rust/60 text-rust hover:bg-rust/10',
  defensive:  'border-cobalt/60 text-cobalt hover:bg-cobalt/10',
  clever:     'border-amber/60 text-amber hover:bg-amber/10',
  curious:    'border-moss/60 text-moss hover:bg-moss/10',
  cautious:   'border-ether/60 text-ether hover:bg-ether/10',
  neutral:    'border-border text-dust hover:bg-codex',
};

function classFor(tone) {
  return TONE_CLASSES[tone] || TONE_CLASSES.neutral;
}

export function ActionPillRail() {
  const setInput = useChatStore((state) => state.setInput);
  const suggestedActions = useChatStore((state) => state.suggestedActions);

  // Deduplicate DM suggestions against always-available labels (case-insensitive)
  // — if the DM suggests "Look around" we render it ONCE, as the always-available
  // pill (so the visual placement is stable across turns).
  const alwaysAvailableLabels = new Set(
    ALWAYS_AVAILABLE.map((a) => a.label.toLowerCase()),
  );
  const dmPills = (suggestedActions || []).filter(
    (a) => a && a.label && !alwaysAvailableLabels.has(a.label.toLowerCase()),
  );

  return (
    <div
      className="flex flex-wrap gap-1.5 px-3 lg:px-6 pt-2 pb-1"
      role="group"
      aria-label="Suggested actions"
    >
      {dmPills.map((action, i) => (
        <button
          key={`dm-${i}-${action.label}`}
          type="button"
          onClick={() => setInput(action.label)}
          className={`px-2.5 py-1 rounded-full border text-xs font-crimson transition-colors focus:outline-none focus:ring-1 focus:ring-amber ${classFor(action.tone)}`}
          aria-label={`Suggested action: ${action.label}`}
          title={action.label}
        >
          {action.label}
        </button>
      ))}
      {ALWAYS_AVAILABLE.map((action) => (
        <button
          key={`always-${action.label}`}
          type="button"
          onClick={() => setInput(action.label)}
          className={`px-2.5 py-1 rounded-full border text-xs font-crimson transition-colors focus:outline-none focus:ring-1 focus:ring-amber ${classFor(action.tone)}`}
          aria-label={`Always-available action: ${action.label}`}
          title={action.label}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}

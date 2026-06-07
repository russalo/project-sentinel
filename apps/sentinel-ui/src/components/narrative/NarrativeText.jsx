// NarrativeText — renders DM narrative prose with inline `<action>...</action>`
// tags expanded into clickable highlighted spans. Click types the action's
// label into the command bar (chatStore.setInput) — does NOT auto-submit,
// matching the BACKLOG-#474 spec.
//
// The plain-text-only fallback is intentional: if the DM forgets the tags or a
// tag arrives half-written during streaming, the regex misses it and the
// content renders as plain text. No crash, no styling glitch — just no
// highlight on that phrase. The pill rail still surfaces whatever's in
// `suggestedActions` so the player has options regardless.

import { parseActionTags } from '../../utils/parseActionTags';
import { useChatStore } from '../../stores/chatStore';

export function NarrativeText({ children, className = '' }) {
  const setInput = useChatStore((state) => state.setInput);
  const text = typeof children === 'string' ? children : '';
  const segments = parseActionTags(text);

  // Fast path: nothing to highlight. Avoid wrapping each char in a span.
  if (segments.length === 0 || segments.every((s) => s.type === 'text')) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (seg.type === 'text') {
          return <span key={i}>{seg.content}</span>;
        }
        // Action span — styled distinctly + clickable. Tailwind classes match
        // the existing amber/accent palette (apps/sentinel-ui's color tokens
        // use amber for highlights / discovery / interactive accents).
        return (
          <button
            key={i}
            type="button"
            onClick={() => setInput(seg.label)}
            className="inline text-amber underline decoration-dotted decoration-amber/60 underline-offset-2 hover:text-amber/80 hover:decoration-amber focus:outline-none focus:ring-1 focus:ring-amber rounded-sm transition-colors"
            aria-label={`Suggest action: ${seg.label}`}
          >
            {seg.label}
          </button>
        );
      })}
    </span>
  );
}

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
//
// Polish (2026-06-07):
//   1. Trailing punctuation immediately after a `</action>` close tag is
//      glued onto the action's *display* (not its click label). Without this,
//      a long action span ending at the right edge of the column would push
//      the trailing `?` / `,` / `.` onto its own line — looks orphaned.
//   2. `*word*` markdown emphasis in text segments renders as <em>. Bold
//      `**word**` is deferred — single-asterisk only for now.

import { Fragment } from 'react';
import { parseActionTags } from '../../utils/parseActionTags';
import { useChatStore } from '../../stores/chatStore';

const TRAILING_PUNCT_RE = /^([.,;:!?]+)(.*)$/s;
const EMPHASIS_RE = /(\*[^*\n]+?\*)/g;

// Coalesce trailing punctuation from a text segment immediately following an
// action into the action's `trailingPunct` field. Click label stays clean;
// only the visual display picks up the punctuation. Prevents orphan-line
// punctuation when the preceding action span fills the column width.
function coalesceTrailingPunctuation(segments) {
  const out = [];
  let i = 0;
  while (i < segments.length) {
    const seg = segments[i];
    const next = segments[i + 1];
    if (seg.type === 'action' && next && next.type === 'text') {
      const m = next.content.match(TRAILING_PUNCT_RE);
      if (m) {
        const [, punct, rest] = m;
        out.push({ ...seg, trailingPunct: punct });
        if (rest && rest.length > 0) {
          out.push({ type: 'text', content: rest });
        }
        i += 2;
        continue;
      }
    }
    out.push(seg);
    i += 1;
  }
  return out;
}

// Render a text segment with `*word*` → <em>word</em>. Single-asterisk only.
// Returns an array of React nodes (text spans + em). Adjacent text runs are
// not coalesced — the caller keys directly by index. Empty asterisk pairs
// `**` or `*  *` (only whitespace inside) fall through as literal text.
function renderEmphasis(content) {
  if (!content || !content.includes('*')) {
    return content;
  }
  const parts = content.split(EMPHASIS_RE);
  return parts.map((p, i) => {
    if (
      p.length > 2 &&
      p.startsWith('*') &&
      p.endsWith('*') &&
      p.slice(1, -1).trim().length > 0
    ) {
      return <em key={i}>{p.slice(1, -1)}</em>;
    }
    return p;
  });
}

const ACTION_BTN_CLASS =
  'inline text-amber underline decoration-dotted decoration-amber/60 ' +
  'underline-offset-2 hover:text-amber/80 hover:decoration-amber ' +
  'focus:outline-none focus:ring-1 focus:ring-amber rounded-sm transition-colors';

export function NarrativeText({ children, className = '' }) {
  const setInput = useChatStore((state) => state.setInput);
  const text = typeof children === 'string' ? children : '';
  const segments = coalesceTrailingPunctuation(parseActionTags(text));

  // Fast path: no actions to highlight, no asterisks to format → return the
  // string as-is for the cheap rendering case.
  if (
    segments.length === 0 ||
    (segments.every((s) => s.type === 'text') && !text.includes('*'))
  ) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (seg.type === 'text') {
          return <Fragment key={i}>{renderEmphasis(seg.content)}</Fragment>;
        }
        const display = seg.trailingPunct ? seg.label + seg.trailingPunct : seg.label;
        return (
          <button
            key={i}
            type="button"
            onClick={() => setInput(seg.label)}
            className={ACTION_BTN_CLASS}
            aria-label={`Suggest action: ${seg.label}`}
          >
            {display}
          </button>
        );
      })}
    </span>
  );
}

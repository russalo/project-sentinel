// Parse `<action>...</action>` tags from DM narrative text into a list of
// segments. Each segment is either a plain-text run or an action span. The
// caller decides how to render — typically NarrativeText wraps actions in a
// clickable element.
//
// Tag shape — the DM prompt asks for inline tags wrapping action prose:
//
//   "Do you <action>strike with shadow magic</action> or <action>flee</action>?"
//
// The tags are byte-identical to the labels emitted in `world_update`'s
// `suggestedActions` array, so a click on either surface (inline highlight or
// pill rail) types the same string into the command bar. See engine/prompts/dm.py
// for the DM-side contract.
//
// Why a tolerant regex rather than a real HTML parser: the surrounding text is
// narrative prose, not markup. We don't want to invoke DOMParser on every
// streamed token (`streamBuffer` updates on every token; mid-stream a tag may be
// half-written). The regex skips half-tags safely — anything that doesn't match
// `<action>...</action>` stays as plain text and the user sees it briefly until
// the closing tag arrives.

const ACTION_RE = /<action>([\s\S]*?)<\/action>/g;

/**
 * Parse narrative text into an array of segments:
 *   { type: 'text', content: string }
 *   { type: 'action', label: string }
 *
 * Adjacent text segments are NOT coalesced — the caller can map directly over
 * the result and key by index. Empty `<action></action>` tags (no inner text)
 * are dropped (treated as malformed).
 */
export function parseActionTags(text) {
  if (!text) return [];
  const segments = [];
  let lastIndex = 0;
  // Clone the regex per call — global regexes carry lastIndex state across
  // invocations and produce wrong results when reused.
  const re = new RegExp(ACTION_RE.source, 'g');
  let match;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }
    const label = match[1].trim();
    if (label) {
      segments.push({ type: 'action', label });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', content: text.slice(lastIndex) });
  }
  // Empty input or input that's only malformed tags produces no segments; the
  // caller should treat that as "nothing to render."
  return segments;
}

/**
 * Extract just the action labels (in order) without the surrounding text.
 * Useful when reconciling inline highlights against the `suggestedActions`
 * structured field — see ActionPillRail.
 */
export function extractActionLabels(text) {
  return parseActionTags(text)
    .filter((s) => s.type === 'action')
    .map((s) => s.label);
}

// Parse `<action>...</action>` tags from DM narrative text into a list of
// segments. Each segment is either a plain-text run or an action span. The
// caller decides how to render — typically NarrativeText wraps actions in a
// clickable element.
//
// Tag shape — the DM prompt asks for inline tags wrapping action prose:
//
//   "Do you <action>strike with shadow magic</action> or <action>flee</action>?"
//
// ...but the model DRIFTS. Observed on the alpha: `<action label="Retrieve the
// silver locket" tone="curious">retrieve the silver locket</action>` — attributes
// the prompt never asked for (tone belongs in the separate `suggestedActions`
// array). A tag-name-only regex missed those and the raw markup rendered as
// literal text in the narrative. We therefore accept ANY attributes, and a
// self-closing form, and keep using the inner prose as the label so the sentence
// still reads naturally — falling back to a `label` attribute when there is no
// inner text. (The "malformed-LLM-output intolerance" hunt pattern: parse
// defensively, never assume the model held the format.)
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

// group 1 = raw attributes (possibly empty), group 2 = inner text (undefined for
// a self-closing tag). `\b` keeps `<actionable>` from matching.
// The attribute run consumes quoted values as UNITS, so a `>` or `/>` inside a
// quoted attribute can't be mistaken for the end of the opening tag.
//
// The three alternatives are NON-OVERLAPPING on purpose: the unquoted branch
// excludes quote characters, so a quoted value has exactly one way to match. An
// ambiguous version (`[^>]` able to consume quotes too) backtracks exponentially
// on an INCOMPLETE opening tag — and `NarrativeText` reparses `streamBuffer` on
// every streamed token, so a model emitting a dozen-plus attributes could freeze
// the tab mid-turn (codex).
//
// `(?=[\s/>])` requires a real tag-name delimiter rather than `\b`, which would
// also match before `-` or `:` and turn `<action-menu>` / `<action:foo>` into
// actions. The unquoted branch also excludes `<` so an INCOMPLETE opening tag
// can't swallow a later valid one — that spanned the match across both and
// silently deleted the narrative text between them (codex).
const ACTION_RE =
  /<action(?=[\s/>])((?:"[^"]*"|'[^']*'|[^>"'<])*?)\s*(?:\/>|>([\s\S]*?)<\/action>)/gi;
const LABEL_ATTR_RE = /\blabel\s*=\s*"([^"]*)"|\blabel\s*=\s*'([^']*)'/i;

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
  // Carry the ORIGINAL flags — rebuilding with a bare 'g' would silently drop the
  // `i` and leave mixed-case markup (`<Action>`) rendering as raw prose.
  const re = new RegExp(ACTION_RE.source, ACTION_RE.flags);
  let match;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }
    // Prefer the inner prose (it reads as part of the sentence); fall back to a
    // `label` attribute when the tag carries no inner text.
    const attrs = match[1] || '';
    const inner = (match[2] || '').trim();
    const attrMatch = inner ? null : attrs.match(LABEL_ATTR_RE);
    const label = inner || (attrMatch ? (attrMatch[1] ?? attrMatch[2] ?? '').trim() : '');
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

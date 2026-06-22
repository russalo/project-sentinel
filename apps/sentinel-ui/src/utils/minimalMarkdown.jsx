// Hand-written minimal-markdown renderer — shared by tester-facing surfaces
// that want a tiny, safe markdown surface without pulling in a library.
//
// Started as the inline-emphasis + safe-link renderer baked into
// MessageCard.jsx for RFC 0002 system messages. Extracted to its own module
// for RFC 0003's tester guide, then extended in RFC 0004 to add images,
// anchor-linked headings, ordered lists, wrapped-list continuations, an
// auto-TOC marker, and an odd-index-only emphasis pass (closing the
// false-positive case the bots flagged on RFC 0003).
//
// Two entry points:
//   - `renderInline(text)` — a single line of inline markdown. Returns a
//     flat array of React nodes.
//   - `renderMarkdown(text)` — a full document. Detects block-level
//     structure and renders each block's content via `renderInline`.
//
// Surface, by design:
//   - Inline: `*italic*`, `**bold**`, `***bold-italic***`,
//     `[label](url)`, `[label](#anchor)` (in-page nav), `![alt](path)`
//     (resolved against `import.meta.env.BASE_URL` so the same path
//     works in `/` and `/alpha/` builds), `` `code` ``
//   - Block: `# H1`, `## H2`, `### H3` (each gets an `id` derived from its
//     text), `- item` and `1. item` lists (single-level, supports
//     indented wrapped continuations), `> quote` blockquotes, blank-line-
//     separated paragraphs, `{{toc}}` marker (expands to a list of links
//     to every `##` heading in document order)
//   - Links: http/https/mailto for external, `#anchor` for in-page.
//     Other schemes render label as plain text.
//
// Out of scope:
//   - Tables, nested lists, fenced code blocks, HTML passthrough,
//     footnotes, autolinks, reference-style links.

import { Fragment } from 'react';

// Inline patterns. Order matters where they're applied sequentially:
//   images extracted FIRST so the `!` doesn't get mistaken for plain text
//   in front of a link.
//   links extracted second so they aren't fragmented by emphasis/code matchers.
//   code spans third so backticks inside emphasis literals don't confuse
//   the emphasis splitter.
//   emphasis last with alternation ordered longest-first so `***x***` wins
//   over `**x**` over `*x*`.
const IMAGE_RE = /!\[([^\]\n]*)\]\(([^)\s]+)\)/g;
const LINK_RE = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;
const CODE_RE = /(`[^`\n]+?`)/g;
const EMPHASIS_RE = /(\*\*\*[^*\n]+?\*\*\*|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g;

// Allowlist link schemes. Anything else (`javascript:`, `data:`, `file:`)
// renders as the label text without an anchor so a malicious markdown
// author can't smuggle a script URL into a tester's browser.
const SAFE_URL_RE = /^(https?:\/\/|mailto:)/i;

// Resolve an image path against the SPA's base URL. Markdown like
// `![](guide/creation.png)` becomes `/guide/creation.png` in default
// builds and `/alpha/guide/creation.png` in alpha builds — same source,
// both hostnames work.
function resolveAssetPath(path) {
  if (typeof path !== 'string' || !path) return path;
  if (/^(https?:\/\/|data:|\/)/i.test(path)) return path;
  // BASE_URL is `/` or `/alpha/`; strip a leading `./` then concat.
  const base =
    (typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL) || '/';
  const cleanPath = path.replace(/^\.\//, '');
  // base always ends with `/`; cleanPath does not start with `/` here.
  return base + cleanPath;
}

// `String.prototype.split` with a capturing regex returns alternating
// non-match / match parts: even indices = the text BETWEEN matches,
// odd indices = the matched substrings. Only odd-indexed parts came
// from the regex, so only they can legitimately be wrapped. Even-indexed
// parts that *happen* to start/end with the marker chars (`*`, `` ` ``)
// are literal text — the regex deliberately didn't match them, and
// wrapping them would be a false positive. (gemini-medium on PR #140.)

function renderEmphasis(content, keyPrefix) {
  if (!content || !content.includes('*')) return content;
  const parts = content.split(EMPHASIS_RE);
  return parts.map((p, i) => {
    const k = `${keyPrefix}-em-${i}`;
    // Only odd indices are matched groups.
    if (i % 2 === 0) return p;
    if (p.length > 6 && p.startsWith('***') && p.endsWith('***')) {
      return (
        <strong key={k} className="font-bold">
          <em className="italic">{p.slice(3, -3)}</em>
        </strong>
      );
    }
    if (p.length > 4 && p.startsWith('**') && p.endsWith('**')) {
      return <strong key={k} className="font-bold">{p.slice(2, -2)}</strong>;
    }
    if (p.length > 2 && p.startsWith('*') && p.endsWith('*')) {
      return <em key={k} className="italic">{p.slice(1, -1)}</em>;
    }
    return p;
  });
}

function renderCodeAndEmphasis(content, keyPrefix) {
  if (!content) return content;
  if (!content.includes('`')) return renderEmphasis(content, keyPrefix);
  const parts = content.split(CODE_RE);
  return parts.map((p, i) => {
    const k = `${keyPrefix}-c-${i}`;
    if (i % 2 === 1 && p.length > 2 && p.startsWith('`') && p.endsWith('`')) {
      return (
        <code
          key={k}
          className="font-mono text-sm bg-void/40 px-1 py-0.5 rounded text-amber"
        >
          {p.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={k}>{renderEmphasis(p, k)}</Fragment>;
  });
}

// Image markdown — extracted before link markdown to avoid the `!` being
// orphaned in front of a `[...](...)`. Returns an array of {type, value}
// tokens for the rest of the inline pipeline to consume.
function splitImages(text) {
  const tokens = [];
  let lastIdx = 0;
  let match;
  IMAGE_RE.lastIndex = 0;
  while ((match = IMAGE_RE.exec(text)) !== null) {
    if (match.index > lastIdx) {
      tokens.push({ type: 'text', value: text.slice(lastIdx, match.index) });
    }
    tokens.push({
      type: 'image',
      alt: match[1] || '',
      src: resolveAssetPath(match[2]),
    });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIdx) });
  }
  return tokens;
}

// Render a text segment through the link pipeline (which also handles code +
// emphasis). Called for each text token between image matches.
function renderTextWithLinks(text, keyPrefix) {
  if (typeof text !== 'string' || text.length === 0) return [];
  const out = [];
  let lastIdx = 0;
  let match;
  let segIdx = 0;
  LINK_RE.lastIndex = 0;
  while ((match = LINK_RE.exec(text)) !== null) {
    const [full, label, url] = match;
    const before = text.slice(lastIdx, match.index);
    if (before) {
      out.push(
        <Fragment key={`${keyPrefix}-t-${segIdx++}`}>
          {renderCodeAndEmphasis(before, `${keyPrefix}t${segIdx}`)}
        </Fragment>,
      );
    }
    if (url.startsWith('#')) {
      // In-page anchor — same-tab navigation, no scheme check needed
      // (`#` is always safe).
      out.push(
        <a
          key={`${keyPrefix}-h-${segIdx++}`}
          href={url}
          className="text-amber underline decoration-dotted decoration-amber/60 underline-offset-2 hover:text-amber/80 hover:decoration-amber"
        >
          {renderCodeAndEmphasis(label, `${keyPrefix}h${segIdx}`)}
        </a>,
      );
    } else if (SAFE_URL_RE.test(url)) {
      out.push(
        <a
          key={`${keyPrefix}-l-${segIdx++}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber underline decoration-dotted decoration-amber/60 underline-offset-2 hover:text-amber/80 hover:decoration-amber"
        >
          {renderCodeAndEmphasis(label, `${keyPrefix}l${segIdx}`)}
        </a>,
      );
    } else {
      out.push(
        <Fragment key={`${keyPrefix}-u-${segIdx++}`}>
          {renderCodeAndEmphasis(label, `${keyPrefix}u${segIdx}`)}
        </Fragment>,
      );
    }
    lastIdx = match.index + full.length;
  }
  const tail = text.slice(lastIdx);
  if (tail) {
    out.push(
      <Fragment key={`${keyPrefix}-t-${segIdx++}`}>
        {renderCodeAndEmphasis(tail, `${keyPrefix}t${segIdx}`)}
      </Fragment>,
    );
  }
  return out;
}

// Split a line into image / text tokens, then render each text segment
// through the link → code → emphasis pipeline. Returns a flat array of
// React nodes.
export function renderInline(text) {
  if (typeof text !== 'string' || text.length === 0) return [];
  const tokens = splitImages(text);
  const out = [];
  let i = 0;
  for (const tok of tokens) {
    if (tok.type === 'image') {
      out.push(
        <img
          key={`img-${i++}`}
          src={tok.src}
          alt={tok.alt}
          className="block max-w-full h-auto rounded my-4 border border-border"
        />,
      );
    } else {
      const segs = renderTextWithLinks(tok.value, `t${i++}`);
      for (const s of segs) out.push(s);
    }
  }
  return out;
}

// Back-compat re-export — the original name shipped in RFC 0002's
// MessageCard. Kept so existing imports continue to work.
export const renderMinimalMarkdown = renderInline;

// Block-level styles.
const H1_CLASS = 'font-cinzel text-2xl text-amber mt-6 mb-3 first:mt-0';
const H2_CLASS = 'font-cinzel text-xl text-amber mt-5 mb-2 first:mt-0';
const H3_CLASS = 'font-cinzel text-lg text-amber mt-4 mb-2 first:mt-0';
const P_CLASS = 'mb-3 leading-relaxed';
const UL_CLASS = 'list-disc list-inside mb-3 space-y-1 pl-2';
const OL_CLASS = 'list-decimal list-inside mb-3 space-y-1 pl-2';
const LI_CLASS = 'leading-relaxed';
const BLOCKQUOTE_CLASS =
  'border-l-2 border-amber/60 pl-4 my-4 text-ether italic';
const TOC_CLASS = 'mb-6 pb-3 border-b border-border';
const TOC_HEADER_CLASS = 'font-cinzel text-sm text-amber uppercase tracking-wide mb-2';
const TOC_LIST_CLASS = 'list-disc list-inside space-y-1 text-sm';

// Block-opener regexes. Each captures the content following the marker.
const H1_RE = /^# +(.*)$/;
const H2_RE = /^## +(.*)$/;
const H3_RE = /^### +(.*)$/;
const UL_RE = /^- +(.*)$/;
const OL_RE = /^\d+\. +(.*)$/;
const QUOTE_RE = /^> ?(.*)$/;
const TOC_RE = /^\{\{toc\}\}$/;
// Indented continuation: starts with whitespace and has at least one
// non-whitespace character after.
const CONTINUATION_RE = /^\s+\S/;

function isBlockOpener(line) {
  return (
    H1_RE.test(line) ||
    H2_RE.test(line) ||
    H3_RE.test(line) ||
    UL_RE.test(line) ||
    OL_RE.test(line) ||
    QUOTE_RE.test(line) ||
    TOC_RE.test(line.trim())
  );
}

// Slugify a heading's plain text into an anchor ID. Lowercase, strip
// non-word characters (keep dashes), collapse whitespace into dashes,
// trim leading/trailing dashes. Bare-bones; if collisions happen, the
// caller suffixes `-1`, `-2`, etc.
function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[*_`~]/g, '')         // strip emphasis/code markers
    .replace(/[^\w\s-]/g, '')        // strip punctuation
    .trim()
    .replace(/\s+/g, '-')            // spaces → dashes
    .replace(/-+/g, '-')             // collapse runs of dashes
    .replace(/^-|-$/g, '');
}

// Collect a list block (consecutive list-marker lines + their wrapped
// continuation lines). Returns {items, nextI}. `markerRe` is UL_RE or OL_RE.
function collectListBlock(lines, startI, markerRe) {
  const items = [];
  let i = startI;
  const firstMatch = lines[i].match(markerRe);
  items.push(firstMatch[1]);
  i += 1;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') break;
    const m = line.match(markerRe);
    if (m) {
      items.push(m[1]);
      i += 1;
      continue;
    }
    // Continuation — indented non-marker line under the previous item.
    // Append to the most recent item with a single space separator so the
    // wrapped doc-source line ends up as one logical text run.
    if (CONTINUATION_RE.test(line) && items.length > 0) {
      items[items.length - 1] += ' ' + line.trim();
      i += 1;
      continue;
    }
    break;
  }
  return { items, nextI: i };
}

// Tokenize markdown into block descriptors.
function tokenize(text) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  // Global set of every slug we've already emitted. Used to guarantee
  // unique heading IDs even when a base slug + dedup suffix would
  // collide with a literal heading-text slug (e.g. `## Section` then
  // `## Section`  → slugs `section`, `section-1`; followed by a literal
  // `## Section 1` heading that would also slug to `section-1`). The
  // suffix counter increments until the result isn't in this set.
  const assignedSlugs = new Set();
  // Per-position counter for headings whose text slugifies to empty
  // (pure-punctuation or whitespace-only). Falls back to `heading-N`
  // so the rendered `<h?>` still has a stable, valid id.
  let emptySlugCounter = 0;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    if (TOC_RE.test(line.trim())) {
      blocks.push({ type: 'toc' });
      i += 1;
      continue;
    }
    const headingMatch =
      (line.match(H3_RE) && { level: 3, text: line.match(H3_RE)[1].trim() }) ||
      (line.match(H2_RE) && { level: 2, text: line.match(H2_RE)[1].trim() }) ||
      (line.match(H1_RE) && { level: 1, text: line.match(H1_RE)[1].trim() });
    if (headingMatch) {
      let baseSlug = slugify(headingMatch.text);
      if (!baseSlug) {
        emptySlugCounter += 1;
        baseSlug = `heading-${emptySlugCounter}`;
      }
      // Find the first suffix variant not already in use. `section` →
      // try `section`; if taken try `section-1`, `section-2`, …
      let slug = baseSlug;
      let suffix = 1;
      while (assignedSlugs.has(slug)) {
        slug = `${baseSlug}-${suffix}`;
        suffix += 1;
      }
      assignedSlugs.add(slug);
      blocks.push({
        type: `h${headingMatch.level}`,
        content: headingMatch.text,
        slug,
      });
      i += 1;
      continue;
    }
    if (UL_RE.test(line)) {
      const { items, nextI } = collectListBlock(lines, i, UL_RE);
      blocks.push({ type: 'ul', items });
      i = nextI;
      continue;
    }
    if (OL_RE.test(line)) {
      const { items, nextI } = collectListBlock(lines, i, OL_RE);
      blocks.push({ type: 'ol', items });
      i = nextI;
      continue;
    }
    if (QUOTE_RE.test(line)) {
      const quoteLines = [line.match(QUOTE_RE)[1]];
      i += 1;
      while (i < lines.length) {
        const nextQ = lines[i].match(QUOTE_RE);
        if (!nextQ) break;
        quoteLines.push(nextQ[1]);
        i += 1;
      }
      blocks.push({ type: 'quote', lines: quoteLines });
      continue;
    }
    // Paragraph: consecutive non-blank, non-block-marker lines.
    const paraLines = [line];
    i += 1;
    while (i < lines.length) {
      const l = lines[i];
      if (l.trim() === '') break;
      if (isBlockOpener(l)) break;
      paraLines.push(l);
      i += 1;
    }
    blocks.push({ type: 'p', content: paraLines.join(' ') });
  }
  return blocks;
}

// Render a tokenized list of blocks. Heading anchor IDs come from the
// `slug` field assigned in tokenize(). The `{{toc}}` block expands at
// render time using the already-tokenized list of h2 entries.
export function renderMarkdown(text) {
  if (typeof text !== 'string' || text.length === 0) return [];
  const blocks = tokenize(text);
  return blocks.map((b, i) => {
    const key = `b-${i}`;
    switch (b.type) {
      case 'h1':
        return (
          <h1 key={key} id={b.slug} className={H1_CLASS}>
            {renderInline(b.content)}
          </h1>
        );
      case 'h2':
        return (
          <h2 key={key} id={b.slug} className={H2_CLASS}>
            {renderInline(b.content)}
          </h2>
        );
      case 'h3':
        return (
          <h3 key={key} id={b.slug} className={H3_CLASS}>
            {renderInline(b.content)}
          </h3>
        );
      case 'ul':
        return (
          <ul key={key} className={UL_CLASS}>
            {b.items.map((item, j) => (
              <li key={`${key}-li-${j}`} className={LI_CLASS}>
                {renderInline(item)}
              </li>
            ))}
          </ul>
        );
      case 'ol':
        return (
          <ol key={key} className={OL_CLASS}>
            {b.items.map((item, j) => (
              <li key={`${key}-li-${j}`} className={LI_CLASS}>
                {renderInline(item)}
              </li>
            ))}
          </ol>
        );
      case 'quote':
        return (
          <blockquote key={key} className={BLOCKQUOTE_CLASS}>
            {b.lines.map((line, j) => (
              <p key={`${key}-q-${j}`} className="mb-1 last:mb-0">
                {renderInline(line)}
              </p>
            ))}
          </blockquote>
        );
      case 'toc': {
        const h2s = blocks.filter((bb) => bb.type === 'h2');
        if (h2s.length === 0) return null;
        return (
          <nav key={key} className={TOC_CLASS} aria-label="Table of contents">
            <div className={TOC_HEADER_CLASS}>Contents</div>
            <ul className={TOC_LIST_CLASS}>
              {h2s.map((h, j) => (
                <li key={`${key}-toc-${j}`}>
                  <a
                    href={`#${h.slug}`}
                    className="text-amber hover:text-amber/80 underline decoration-dotted decoration-amber/60 underline-offset-2"
                  >
                    {/* Pass through renderInline so a heading like
                        `## **Important** notes` or `## The `worldId`
                        field` renders styled in the TOC link, not as
                        literal markdown source. */}
                    {renderInline(h.content)}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        );
      }
      case 'p':
      default:
        return <p key={key} className={P_CLASS}>{renderInline(b.content)}</p>;
    }
  });
}

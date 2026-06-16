// Hand-written minimal-markdown renderer — shared by tester-facing surfaces
// that want a tiny, safe markdown surface without pulling in a library.
//
// Started as the inline-emphasis + safe-link renderer baked into
// MessageCard.jsx for RFC 0002 system messages. Extracted + extended for
// RFC 0003's tester guide, which needs block-level structure (headings,
// lists, blockquotes) in addition to inline emphasis and links.
//
// Two entry points:
//   - `renderInline(text)` — a single line of inline markdown (emphasis,
//     links, code spans). Returns a flat array of React nodes.
//   - `renderMarkdown(text)` — a full document. Detects block-level
//     structure (headings, lists, blockquotes, paragraphs) and renders
//     each block's content via `renderInline`.
//
// Surface, by design (RFC 0002 + RFC 0003):
//   - Inline: `*italic*`, `**bold**`, `***bold-italic***`, `[label](url)`,
//     `` `code` ``
//   - Block: `# H1`, `## H2`, `### H3`, `- item` (single-level lists),
//     `> quote` (single-level blockquotes), blank-line-separated paragraphs
//   - Links: http/https/mailto only. Other schemes render label as plain text.
//
// Out of scope (deliberately not supported):
//   - Tables, nested lists, ordered lists, fenced code blocks, images,
//     HTML passthrough, footnotes, autolinks, reference-style links.

import { Fragment } from 'react';

// Inline patterns. Order matters where they're applied sequentially:
//   links extracted FIRST so they aren't fragmented by emphasis/code matchers.
//   code spans extracted second so backticks inside emphasis literals don't
//   confuse the emphasis splitter.
//   emphasis last with alternation ordered longest-first so `***x***` wins
//   over `**x**` over `*x*`.
const LINK_RE = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;
const CODE_RE = /(`[^`\n]+?`)/g;
const EMPHASIS_RE = /(\*\*\*[^*\n]+?\*\*\*|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g;

// Allowlist link schemes. Anything else (`javascript:`, `data:`, `file:`)
// renders as the label text without an anchor so a malicious markdown
// author can't smuggle a script URL into a tester's browser.
const SAFE_URL_RE = /^(https?:\/\/|mailto:)/i;

function renderEmphasis(content, keyPrefix) {
  if (!content || !content.includes('*')) return content;
  const parts = content.split(EMPHASIS_RE);
  return parts.map((p, i) => {
    const k = `${keyPrefix}-em-${i}`;
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

// Apply code-span replacement on top of an emphasis-rendered fragment.
// Code spans are pure text-level (no nested emphasis) — splitting around the
// CODE_RE preserves the code spans as literal `` `text` `` tokens that get
// wrapped in <code>, while everything else flows through renderEmphasis.
function renderCodeAndEmphasis(content, keyPrefix) {
  if (!content) return content;
  if (!content.includes('`')) return renderEmphasis(content, keyPrefix);
  const parts = content.split(CODE_RE);
  return parts.map((p, i) => {
    const k = `${keyPrefix}-c-${i}`;
    if (p.length > 2 && p.startsWith('`') && p.endsWith('`')) {
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

// Split a single line into alternating text + link segments, then run code-
// and emphasis-rendering on the non-link segments. Returns a flat array of
// React nodes (or an empty array for empty input).
export function renderInline(text) {
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
        <Fragment key={`t-${segIdx++}`}>
          {renderCodeAndEmphasis(before, `t${segIdx}`)}
        </Fragment>,
      );
    }
    if (SAFE_URL_RE.test(url)) {
      out.push(
        <a
          key={`l-${segIdx++}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber underline decoration-dotted decoration-amber/60 underline-offset-2 hover:text-amber/80 hover:decoration-amber"
        >
          {renderCodeAndEmphasis(label, `l${segIdx}`)}
        </a>,
      );
    } else {
      // Unsafe URL scheme — drop the anchor, render the label as text.
      out.push(
        <Fragment key={`u-${segIdx++}`}>
          {renderCodeAndEmphasis(label, `u${segIdx}`)}
        </Fragment>,
      );
    }
    lastIdx = match.index + full.length;
  }
  const tail = text.slice(lastIdx);
  if (tail) {
    out.push(
      <Fragment key={`t-${segIdx++}`}>
        {renderCodeAndEmphasis(tail, `t${segIdx}`)}
      </Fragment>,
    );
  }
  return out;
}

// Back-compat re-export — the original name shipped in RFC 0002's
// MessageCard. Kept so existing imports (tests, MessageCard.jsx) continue to
// work without churn.
export const renderMinimalMarkdown = renderInline;

// Block-level styles. Headings get a slight top margin so they don't crowd
// the previous block; paragraphs and list items inherit codex prose
// styling from the parent container.
const H1_CLASS = 'font-cinzel text-2xl text-amber mt-6 mb-3 first:mt-0';
const H2_CLASS = 'font-cinzel text-xl text-amber mt-5 mb-2 first:mt-0';
const H3_CLASS = 'font-cinzel text-lg text-amber mt-4 mb-2 first:mt-0';
const P_CLASS = 'mb-3 leading-relaxed';
const UL_CLASS = 'list-disc list-inside mb-3 space-y-1 pl-2';
const LI_CLASS = 'leading-relaxed';
const BLOCKQUOTE_CLASS =
  'border-l-2 border-amber/60 pl-4 my-4 text-ether italic';

// Recognize block-level openers at start-of-line. Each regex matches the
// marker AND captures the content following it on the same line.
const H1_RE = /^# +(.*)$/;
const H2_RE = /^## +(.*)$/;
const H3_RE = /^### +(.*)$/;
const LIST_RE = /^- +(.*)$/;
const QUOTE_RE = /^> ?(.*)$/;

// Tokenize markdown text into an array of block descriptors. A block is one
// of: heading (h1/h2/h3), paragraph (a run of non-blank text lines that
// aren't otherwise classified), list (consecutive `- ` lines), or quote
// (consecutive `> ` lines).
function tokenize(text) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    const h3 = line.match(H3_RE);
    if (h3) {
      blocks.push({ type: 'h3', content: h3[1].trim() });
      i += 1;
      continue;
    }
    const h2 = line.match(H2_RE);
    if (h2) {
      blocks.push({ type: 'h2', content: h2[1].trim() });
      i += 1;
      continue;
    }
    const h1 = line.match(H1_RE);
    if (h1) {
      blocks.push({ type: 'h1', content: h1[1].trim() });
      i += 1;
      continue;
    }
    const li = line.match(LIST_RE);
    if (li) {
      const items = [li[1]];
      i += 1;
      while (i < lines.length) {
        const nextLi = lines[i].match(LIST_RE);
        if (!nextLi) break;
        items.push(nextLi[1]);
        i += 1;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }
    const q = line.match(QUOTE_RE);
    if (q) {
      const quoteLines = [q[1]];
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
    // Paragraph: collect consecutive non-blank, non-block-marker lines.
    const paraLines = [line];
    i += 1;
    while (i < lines.length) {
      const l = lines[i];
      if (l.trim() === '') break;
      if (H1_RE.test(l) || H2_RE.test(l) || H3_RE.test(l) ||
          LIST_RE.test(l) || QUOTE_RE.test(l)) break;
      paraLines.push(l);
      i += 1;
    }
    blocks.push({ type: 'p', content: paraLines.join(' ') });
  }
  return blocks;
}

// Render a tokenized list of blocks. Each block is given a key so React
// doesn't complain about the array; blocks don't share keys with inline
// nodes (those keys live inside renderInline).
export function renderMarkdown(text) {
  if (typeof text !== 'string' || text.length === 0) return [];
  const blocks = tokenize(text);
  return blocks.map((b, i) => {
    const key = `b-${i}`;
    switch (b.type) {
      case 'h1':
        return <h1 key={key} className={H1_CLASS}>{renderInline(b.content)}</h1>;
      case 'h2':
        return <h2 key={key} className={H2_CLASS}>{renderInline(b.content)}</h2>;
      case 'h3':
        return <h3 key={key} className={H3_CLASS}>{renderInline(b.content)}</h3>;
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
      case 'p':
      default:
        return <p key={key} className={P_CLASS}>{renderInline(b.content)}</p>;
    }
  });
}

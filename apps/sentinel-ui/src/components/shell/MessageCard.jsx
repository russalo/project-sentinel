// MessageCard — single system-message card rendered in the Settings drawer's
// Messages section (RFC 0002). Title + timestamp + minimal-markdown body.
//
// Markdown surface is intentionally tiny (Russell 2026-06-14): *italic*,
// **bold**, and [label](url). Anything richer is out of scope; the operator
// can fall through to plain text for everything else. We don't reuse
// NarrativeText.jsx because that parser is also handling <action> tags and
// trailing-punctuation coalescing — different problem.

// Order matters: longest emphasis first so **bold** doesn't get mis-snatched
// as two *italic* runs. Links are matched separately and split before
// emphasis processing, so a `*word*` inside a link label still renders italic.
const LINK_RE = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;
const EMPHASIS_RE = /(\*\*\*[^*\n]+?\*\*\*|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g;

// Allowlist link schemes — http/https/mailto only. Anything else
// (`javascript:`, `data:`, `file:`) renders as the label text without an
// anchor so a malicious operator can't smuggle script into a tester's browser.
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

// Split a string into alternating text + link segments, then run emphasis
// rendering on the text segments and on the link labels. Output is a flat
// array of React nodes.
export function renderMinimalMarkdown(text) {
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
        <span key={`t-${segIdx++}`}>{renderEmphasis(before, `t${segIdx}`)}</span>,
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
          {renderEmphasis(label, `l${segIdx}`)}
        </a>,
      );
    } else {
      // Unsafe URL scheme — render the label as plain text, drop the link.
      out.push(
        <span key={`u-${segIdx++}`}>{renderEmphasis(label, `u${segIdx}`)}</span>,
      );
    }
    lastIdx = match.index + full.length;
  }
  const tail = text.slice(lastIdx);
  if (tail) {
    out.push(
      <span key={`t-${segIdx++}`}>{renderEmphasis(tail, `t${segIdx}`)}</span>,
    );
  }
  return out;
}

const CATEGORY_LABEL = {
  info: 'Info',
  warning: 'Warning',
  release: 'Release',
  maintenance: 'Maintenance',
};

const CATEGORY_CLASS = {
  info: 'text-ether border-ether/40',
  warning: 'text-amber border-amber/60',
  release: 'text-emerald-400 border-emerald-400/40',
  maintenance: 'text-rose-400 border-rose-400/40',
};

function formatTimestamp(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function MessageCard({ message }) {
  const category = message.category || 'info';
  const catLabel = CATEGORY_LABEL[category] || category;
  const catClass = CATEGORY_CLASS[category] || CATEGORY_CLASS.info;

  // Body lines split on paragraph breaks. We don't render full markdown
  // paragraphs — each newline-separated line is its own <p>.
  const lines = (message.body || '').split(/\n+/).filter((l) => l.length > 0);

  return (
    <article
      className="rounded border border-border bg-void/30 p-3"
      aria-label={`System message: ${message.title}`}
    >
      <header className="flex items-start justify-between gap-2 mb-1">
        <h3 className="font-cinzel text-sm text-amber leading-snug">
          {message.pinned ? <span aria-label="Pinned">📌 </span> : null}
          {message.title}
        </h3>
        <span
          className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border ${catClass}`}
        >
          {catLabel}
        </span>
      </header>
      <div className="text-xs text-ether mb-2" title={message.published_at}>
        {formatTimestamp(message.published_at)}
      </div>
      <div className="text-sm text-ink font-crimson space-y-2 leading-relaxed">
        {lines.map((line, i) => (
          <p key={i}>{renderMinimalMarkdown(line)}</p>
        ))}
      </div>
    </article>
  );
}

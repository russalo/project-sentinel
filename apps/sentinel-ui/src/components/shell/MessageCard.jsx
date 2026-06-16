// MessageCard — single system-message card rendered in the Settings drawer's
// Messages section (RFC 0002). Title + timestamp + minimal-markdown body.
//
// Markdown rendering is delegated to the shared helper at
// `utils/minimalMarkdown.js` (extracted for RFC 0003 — tester guide). Body
// stays line-oriented: each non-blank line of the message body is its own
// `<p>` rendered via the inline-only path (`renderMinimalMarkdown`). The
// guide page is the only consumer of the block-level renderer; messages
// stay flat to keep the drawer card compact.

import { renderMinimalMarkdown } from '../../utils/minimalMarkdown';

// Re-export so existing MessageCard.test.jsx callers (which test
// `renderMinimalMarkdown` directly through this module) continue to work.
export { renderMinimalMarkdown };

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

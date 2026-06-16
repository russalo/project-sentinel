// Guide — the tester-facing onboarding doc, rendered in-app (RFC 0003).
//
// Source of truth is the markdown at `docs/alpha/TESTER_GUIDE.md` (a path
// outside the SPA tree). Vite's `?raw` import inlines its contents into the
// bundle at build time; the canonical file is edited via normal repo PRs.
// `vite.config.js` extends `server.fs.allow` to the repo root so the import
// works in dev mode too.

import { Link } from 'wouter';
import { ArrowLeft } from 'lucide-react';
import guideMarkdown from '../../../../docs/alpha/TESTER_GUIDE.md?raw';
import { renderMarkdown } from '../utils/minimalMarkdown';

export default function Guide() {
  return (
    <div className="min-h-screen bg-void text-ink font-crimson">
      <header className="bg-codex border-b border-border px-4 lg:px-6 py-3 flex items-center gap-3">
        <Link
          href="/"
          className="text-dust hover:text-amber transition-colors p-1"
          aria-label="Back to worlds"
          title="Back to worlds"
        >
          <ArrowLeft size={18} />
        </Link>
        <h1 className="font-cinzel text-xl text-amber">Tester Guide</h1>
      </header>
      <main className="max-w-3xl mx-auto px-4 lg:px-6 py-6">
        <article>{renderMarkdown(guideMarkdown)}</article>
      </main>
    </div>
  );
}

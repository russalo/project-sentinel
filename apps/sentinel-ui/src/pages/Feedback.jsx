// Feedback — in-product form posting to POST /api/feedback.
//
// Captures user-entered subject/body/category/platform/browser plus optional
// severity/repro/handle, AND auto-captures worldId, sessionId (from
// playerStore when populated), viewport, currentUrl, bundleHash (build-time
// constant), userAgent (server reads from the request header — not sent in
// the body). worldId+sessionId being null is informative — distinguishes
// in-session feedback from "can't get in" reports.
//
// Layout: subject (single-line), body (textarea), category (radio), platform
// + browser (text), then a collapsible "More detail" toggle for the optional
// fields so the form doesn't intimidate first-time submitters. Submit button
// disabled while submitting or when required fields are empty.

import { useState } from 'react';
import { Link, useLocation } from 'wouter';
import { ArrowLeft, CheckCircle2 } from 'lucide-react';
import { usePlayerStore } from '../stores/playerStore';
import { API_BASE } from '../api/client';

// Build-time constant — set by Vite to the current bundle hash when the
// chunk filename is known. Defaults to 'dev' when the env isn't set.
const BUNDLE_HASH = import.meta.env.VITE_BUNDLE_HASH || 'dev';

const CATEGORIES = [
  { value: 'bug', label: 'Bug' },
  { value: 'ui-ux', label: 'UI / UX' },
  { value: 'general', label: 'General' },
  { value: 'feature', label: 'Feature request' },
];

const SEVERITIES = [
  { value: '', label: '— not set —' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];

const REPRODUCIBLE = [
  { value: '', label: '— not set —' },
  { value: 'yes', label: 'Yes, every time' },
  { value: 'sometimes', label: 'Sometimes' },
  { value: 'no', label: 'No, just the once' },
];

export default function Feedback() {
  const [, setLocation] = useLocation();
  const worldId = usePlayerStore((s) => s.worldId);
  const sessionId = usePlayerStore((s) => s.sessionId);

  const [form, setForm] = useState({
    subject: '',
    body: '',
    category: 'bug',
    platform: '',
    browser: '',
    severity: '',
    reproducible: '',
    handle: '',
  });
  const [showOptional, setShowOptional] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submittedId, setSubmittedId] = useState(null);

  const handleChange = (field) => (e) => {
    setForm({ ...form, [field]: e.target.value });
    if (submitError) setSubmitError(null);
  };

  const valid =
    form.subject.trim().length > 0 &&
    form.body.trim().length > 0 &&
    form.platform.trim().length > 0 &&
    form.browser.trim().length > 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    const payload = {
      subject: form.subject.trim(),
      body: form.body.trim(),
      category: form.category,
      platform: form.platform.trim(),
      browser: form.browser.trim(),
      // Pydantic accepts null OR omitted for optionals; keep them present-null
      // so the on-disk record shape is consistent regardless of user input.
      severity: form.severity || null,
      reproducible: form.reproducible || null,
      handle: form.handle.trim() || null,
      worldId: worldId || null,
      sessionId: sessionId || null,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      currentUrl: window.location.href.split('?')[0],
      bundleHash: BUNDLE_HASH,
    };
    try {
      const res = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      // Defensively normalize the response — a non-object body (null, array,
      // string) would TypeError on data.id otherwise. Bad payloads collapse
      // to {} and we surface a clean error via the HTTP status. (gemini
      // medium on PR #116.)
      const raw = await res.json().catch(() => ({}));
      const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
      if (!res.ok) {
        const detail = data.detail?.detail || data.detail || `HTTP ${res.status}`;
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      setSubmittedId(data.id || 'unknown');
    } catch (err) {
      setSubmitError(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  // Success state — replaces the form rather than overlaying. Player sees a
  // clear confirmation + a back-to-the-game link. No auto-redirect — let them
  // land here and process the success before moving on.
  if (submittedId) {
    return (
      <div className="min-h-screen bg-void text-ink flex flex-col items-center justify-center px-6 py-12">
        <div className="max-w-md w-full text-center">
          <CheckCircle2 size={48} className="mx-auto mb-4 text-amber" />
          <h1 className="font-cinzel text-2xl text-amber mb-2">Feedback received</h1>
          <p className="text-dust mb-2">Thank you — your report has been logged.</p>
          <p className="text-xs text-ether mb-8 font-mono">id: {submittedId}</p>
          <Link
            href={worldId ? `/w/${worldId}` : '/'}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber text-void rounded hover:bg-amber/90 transition-colors"
          >
            <ArrowLeft size={16} />
            Back to the game
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-void text-ink">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <header className="mb-6">
          <Link
            href={worldId ? `/w/${worldId}` : '/'}
            className="inline-flex items-center gap-1 text-sm text-dust hover:text-amber transition-colors mb-3"
          >
            <ArrowLeft size={14} /> Back
          </Link>
          <h1 className="font-cinzel text-3xl text-amber mb-2">Send feedback</h1>
          <p className="text-sm text-dust">
            Bug reports, UI/UX gripes, general impressions, or feature requests —
            all welcome. The form auto-captures your world + session id when
            you're in a session, plus browser + viewport. No screenshots in v1.
          </p>
        </header>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Required: subject */}
          <label className="flex flex-col gap-1">
            <span className="text-sm text-dust">Subject</span>
            <input
              type="text"
              value={form.subject}
              onChange={handleChange('subject')}
              maxLength={140}
              required
              disabled={submitting}
              className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
              placeholder="Pills overlap text on iOS"
            />
          </label>

          {/* Required: category */}
          <fieldset className="flex flex-col gap-1">
            <legend className="text-sm text-dust">Category</legend>
            <div className="flex flex-wrap gap-2 mt-1">
              {CATEGORIES.map((c) => (
                <label
                  key={c.value}
                  className={`px-3 py-1.5 rounded-full border text-sm cursor-pointer transition-colors ${
                    form.category === c.value
                      ? 'border-amber/60 text-amber bg-amber/10'
                      : 'border-border text-dust hover:bg-codex'
                  }`}
                >
                  <input
                    type="radio"
                    name="category"
                    value={c.value}
                    checked={form.category === c.value}
                    onChange={handleChange('category')}
                    disabled={submitting}
                    className="sr-only"
                  />
                  {c.label}
                </label>
              ))}
            </div>
          </fieldset>

          {/* Required: body */}
          <label className="flex flex-col gap-1">
            <span className="text-sm text-dust">Description</span>
            <textarea
              value={form.body}
              onChange={handleChange('body')}
              maxLength={4000}
              required
              disabled={submitting}
              rows={6}
              className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50 resize-y font-crimson leading-relaxed"
              placeholder="What happened? What were you expecting?"
            />
            <span className="text-xs text-ether self-end">
              {form.body.length}/4000
            </span>
          </label>

          {/* Required: platform + browser side-by-side */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-sm text-dust">Platform</span>
              <input
                type="text"
                value={form.platform}
                onChange={handleChange('platform')}
                maxLength={80}
                required
                disabled={submitting}
                className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
                placeholder="iOS / Windows 11 / macOS / etc"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-sm text-dust">Browser</span>
              <input
                type="text"
                value={form.browser}
                onChange={handleChange('browser')}
                maxLength={80}
                required
                disabled={submitting}
                className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
                placeholder="Chrome / Safari / Firefox"
              />
            </label>
          </div>

          {/* Optional fields — collapsible */}
          <button
            type="button"
            onClick={() => setShowOptional((v) => !v)}
            className="text-sm text-amber hover:text-amber/80 transition-colors self-start"
          >
            {showOptional ? '− Hide optional details' : '+ Add optional details'}
          </button>

          {showOptional && (
            <div className="flex flex-col gap-4 pl-4 border-l-2 border-border">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-sm text-dust">Severity</span>
                  <select
                    value={form.severity}
                    onChange={handleChange('severity')}
                    disabled={submitting}
                    className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
                  >
                    {SEVERITIES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-sm text-dust">Reproducible</span>
                  <select
                    value={form.reproducible}
                    onChange={handleChange('reproducible')}
                    disabled={submitting}
                    className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
                  >
                    {REPRODUCIBLE.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-sm text-dust">
                  Your name or handle <span className="text-ether">(optional)</span>
                </span>
                <input
                  type="text"
                  value={form.handle}
                  onChange={handleChange('handle')}
                  maxLength={80}
                  disabled={submitting}
                  className="bg-codex border border-border rounded px-3 py-2 text-ink focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
                  placeholder="Only if you want a follow-up"
                />
              </label>
            </div>
          )}

          {/* Auto-capture notice — surface what's being included so testers
              aren't surprised. Lists the fields explicitly. */}
          <div className="text-xs text-ether border-t border-border pt-3">
            Also includes (auto-captured): your viewport size, the page URL you're
            on, the SPA build hash{worldId ? `, your world id, and your session id` : ''}.
          </div>

          {submitError && (
            <div className="border border-rust/60 bg-rust/10 text-rust text-sm px-3 py-2 rounded">
              {submitError}
            </div>
          )}

          <button
            type="submit"
            disabled={!valid || submitting}
            className="px-4 py-2.5 bg-amber text-void rounded hover:bg-amber/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed self-start font-medium"
          >
            {submitting ? 'Submitting…' : 'Send feedback'}
          </button>
        </form>
      </div>
    </div>
  );
}

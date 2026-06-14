import { Router, Route } from 'wouter';
import { AppShell } from './components/shell/AppShell';
import WorldCreation from './pages/WorldCreation';
import WorldList from './pages/WorldList';
import DataBrowser from './pages/DataBrowser';
import Feedback from './pages/Feedback';
import AdminMessages from './pages/AdminMessages';
import './index.css';

// Router base mirrors the Vite build's base. import.meta.env.BASE_URL is set
// by Vite's `base` config — '/' for default builds (tailnet dev site) or
// '/alpha/' for `pnpm build:alpha` (closed-alpha at sentinel.russalo.com/alpha/).
// Wouter expects no trailing slash and treats '' as "no base", so strip the
// trailing '/' and a leading '/' that's the only character. Reading from
// import.meta.env.BASE_URL means the two stay in sync automatically — no
// hand-coded constant to drift.
const routerBase = import.meta.env.BASE_URL.replace(/\/$/, '');

export default function App() {
  return (
    <Router base={routerBase}>
      <Route path="/create" component={WorldCreation} />
      <Route path="/data" component={DataBrowser} />
      {/* Feedback form — basic_auth gated at the edge; no per-world token
          required so testers can report inability to enter a session. See
          docs/ALPHA_FEEDBACK.md for the operational triage flow. */}
      <Route path="/feedback" component={Feedback} />
      {/* System-messages admin (RFC 0002) — tailnet-only. The Caddyfile
          404s `/api/admin/*` on the public edge, so the page itself loads
          on the public bundle but every API call from it fails unless you
          reach the backend over tailnet. Topology IS the credential. */}
      <Route path="/admin/messages" component={AdminMessages} />
      {/* The game lives at a world's own URL (ADR 0002 Slice 4) so it's
          shareable and survives a refresh — AppShell hydrates from the
          worldId param. */}
      <Route path="/w/:worldId" component={AppShell} />
      {/* The root is the "my worlds" picker (ADR 0002 Slice 5): worlds are
          resumable, so / lists them (resume → /w/<id>) or offers a new one. */}
      <Route path="/" component={WorldList} />
    </Router>
  );
}

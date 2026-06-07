import { Router, Route } from 'wouter';
import { AppShell } from './components/shell/AppShell';
import WorldCreation from './pages/WorldCreation';
import WorldList from './pages/WorldList';
import DataBrowser from './pages/DataBrowser';
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

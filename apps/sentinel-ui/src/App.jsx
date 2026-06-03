import { Router, Route } from 'wouter';
import { AppShell } from './components/shell/AppShell';
import WorldCreation from './pages/WorldCreation';
import WorldList from './pages/WorldList';
import DataBrowser from './pages/DataBrowser';
import './index.css';

export default function App() {
  return (
    <Router>
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

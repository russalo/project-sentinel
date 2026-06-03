import { Router, Route, Redirect } from 'wouter';
import { AppShell } from './components/shell/AppShell';
import WorldCreation from './pages/WorldCreation';
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
      {/* No "currentless" game state to render at the root — every game has
          a world URL, so / sends the player to world creation. */}
      <Route path="/">
        <Redirect to="/create" />
      </Route>
    </Router>
  );
}

import { Router, Route } from 'wouter';
import { AppShell } from './components/shell/AppShell';
import WorldCreation from './pages/WorldCreation';
import DataBrowser from './pages/DataBrowser';
import './index.css';

export default function App() {
  return (
    <Router>
      <Route path="/create" component={WorldCreation} />
      <Route path="/data" component={DataBrowser} />
      <Route path="/" component={AppShell} />
    </Router>
  );
}

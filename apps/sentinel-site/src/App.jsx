import { Route, Switch } from 'wouter'
import Landing from './pages/Landing.jsx'
import Guide from './pages/Guide.jsx'

export default function App() {
  return (
    <Switch>
      <Route path="/" component={Landing} />
      <Route path="/guide" component={Guide} />
      {/* Unknown paths fall back to the landing page rather than a dead end. */}
      <Route component={Landing} />
    </Switch>
  )
}

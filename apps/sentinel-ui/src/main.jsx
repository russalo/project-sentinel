import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Polyfill crypto.randomUUID for insecure contexts (HTTP over LAN/tailnet).
// The Web Crypto API only exposes randomUUID on secure origins (HTTPS or
// localhost); serving the dev build over a tailnet IP puts us in an
// insecure context, so the function is undefined and any caller crashes.
// This polyfill is NOT cryptographically strong — it just produces a
// UUID-v4-shaped string for UI-level IDs (chat message keys, etc.).
if (typeof globalThis.crypto === 'undefined') {
  globalThis.crypto = {}
}
if (typeof globalThis.crypto.randomUUID !== 'function') {
  globalThis.crypto.randomUUID = () =>
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

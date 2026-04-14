import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Note: ID generation is handled via src/utils/id.js (newId()), not
// by patching globalThis.crypto. See that file for the reasoning.

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

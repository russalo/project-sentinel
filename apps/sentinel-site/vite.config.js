import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Public marketing/landing SPA — separate from the gated game app
// (apps/sentinel-ui). Served at the apex of sentinelrpg.com, so base '/'.
//
// `server.fs.allow` is widened to the repo root so the /guide page can
// `?raw`-import the single source of truth for the tutorial,
// `docs/alpha/TESTER_GUIDE.md` — the same doc the gated app renders, edited
// once and bundled into both SPAs at build time (no copy step).
// https://vite.dev/config/
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    fs: {
      allow: ['..', '../..'],
    },
  },
})

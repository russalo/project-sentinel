/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Vitest piggybacks on this config — the `test` block below is read
// by `vitest run` / `vitest` and applies on top of the Vite plugins
// already configured for dev/build, so component tests share the
// same React + JSX transform the production app uses.
//
// Mode-aware base path:
//   - default `production` (`pnpm build`) → base '/' → tailnet dev site at
//     sentinel.dev.russalo.com/
//   - `alpha` mode (`pnpm build:alpha` → `pnpm build --mode alpha`) → base
//     '/alpha/' → public closed alpha at sentinel.russalo.com/alpha/
//
// In alpha mode, Vite emits asset URLs prefixed `/alpha/`; Caddy strips the
// `/alpha` prefix at the edge (handle_path) before reverse_proxy, so the
// backend stays mounted at /api/ unchanged and the file_server sees
// /assets/... unchanged. Wouter Router uses base="/alpha" in App.jsx when
// import.meta.env.BASE_URL is '/alpha/'; the two must stay in sync, which
// the App.jsx-side wiring (reading import.meta.env.BASE_URL) guarantees.
// `pnpm dev` is unaffected — Vite serves at / locally.
export default defineConfig(({ mode }) => ({
  base: mode === 'alpha' ? '/alpha/' : '/',
  plugins: [react()],
  // Explicit JSX automatic runtime. Production source files don't
  // import React (the @vitejs/plugin-react auto-runtime injects the
  // JSX factory), and we want test files to behave the same. Without
  // this, vitest's esbuild loader defaults to `runtime: 'classic'`
  // and every .jsx file we render in a test fails with
  // "ReferenceError: React is not defined".
  esbuild: {
    jsx: 'automatic',
    jsxImportSource: 'react',
  },
  test: {
    // Component tests need a DOM. jsdom is fine for everything we
    // ship today.
    environment: 'jsdom',
    // Globals on so tests can `describe`/`it`/`expect` without an
    // import in every file. Matches the convention vitest's docs
    // and most React testing examples follow.
    globals: true,
    // setupFiles runs before each test file. Registers the
    // jest-dom matchers (toBeInTheDocument, toHaveTextContent,
    // etc.) globally.
    setupFiles: ['./vitest.setup.js'],
    // Test file patterns under src/. Defaults already include
    // *.test.* and *.spec.*; listing them here makes the
    // convention visible without having to know vitest's defaults.
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    exclude: ['node_modules', 'dist', 'build'],
  },
}))

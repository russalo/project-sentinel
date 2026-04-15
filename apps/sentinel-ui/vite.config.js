import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// The config is a function because we only want the `esbuild` block
// during vitest runs. Vite 8's production build uses oxc and warns
// (harmlessly) if both are set, so we keep esbuild scoped to test mode.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  ...(mode === 'test' && {
    // vitest uses esbuild for transforming .test.jsx files. The test
    // files don't import React explicitly — they rely on the automatic
    // JSX runtime, which esbuild needs to be told about here.
    esbuild: { jsx: 'automatic' },
  }),
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
}))

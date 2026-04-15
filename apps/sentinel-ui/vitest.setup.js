// Vitest setup file — runs before each test file.
//
// `@testing-library/jest-dom` extends Vitest's `expect` with
// DOM-specific matchers like `toBeInTheDocument()`,
// `toHaveTextContent()`, `toHaveClass()`, etc. Without this import,
// component tests have to fall back to verbose attribute / text
// checks that hide intent.
//
// Wired up via `test.setupFiles` in vite.config.js.
import '@testing-library/jest-dom'

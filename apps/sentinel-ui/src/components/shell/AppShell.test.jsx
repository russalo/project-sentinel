/**
 * Tests for AppShell's welcome-message seeding.
 *
 * AppShell seeds a single "Welcome, traveler…" message into the chat
 * store on mount. Two regressions are guarded here:
 *
 *   1. Author must come from the active persona (personaStore), not a
 *      hardcoded "Oracle".
 *   2. Exactly one welcome message must be seeded — including under
 *      React StrictMode, whose dev-mode double-invocation of effects
 *      previously produced two identical welcomes.
 *
 * The shell's heavy children (TopBar, panels, narrative scroll) are
 * stubbed — this test only exercises the seeding effect, so it asserts
 * against the chat store state rather than the rendered subtree.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { StrictMode } from 'react'
import { render, act } from '@testing-library/react'
import { AppShell } from './AppShell'
import { useChatStore } from '../../stores/chatStore'
import { usePersonaStore } from '../../stores/personaStore'

vi.mock('./TopBar', () => ({ TopBar: () => null }))
vi.mock('./CommandBar', () => ({ CommandBar: () => null }))
vi.mock('../world-state/WorldStateDashboard', () => ({ WorldStateDashboard: () => null }))
vi.mock('../narrative/NarrativeScroll', () => ({ NarrativeScroll: () => null }))
vi.mock('../panels/PanelRouter', () => ({ PanelRouter: () => null }))

function welcomeMessages() {
  return useChatStore
    .getState()
    .messages.filter((m) => typeof m.content === 'string' && m.content.startsWith('Welcome, traveler'))
}

beforeEach(() => {
  // Reset both stores to a clean pre-session baseline.
  useChatStore.getState().clearMessages()
  usePersonaStore.setState({ personaId: null, personaName: 'Oracle' })
})

describe('AppShell welcome message', () => {
  it('seeds exactly one welcome message on mount', () => {
    render(<AppShell />)
    expect(welcomeMessages()).toHaveLength(1)
  })

  it('does not duplicate the welcome under StrictMode double-invocation', () => {
    render(
      <StrictMode>
        <AppShell />
      </StrictMode>,
    )
    expect(welcomeMessages()).toHaveLength(1)
  })

  it('attributes the welcome to the selected persona, not a hardcoded Oracle', () => {
    usePersonaStore.getState().setPersona('cowboy-bob', 'Cowboy Bob')
    render(<AppShell />)
    expect(welcomeMessages()[0].author).toBe('Cowboy Bob')
  })

  it('falls back to the store default author when no persona is set', () => {
    render(<AppShell />)
    expect(welcomeMessages()[0].author).toBe('Oracle')
  })

  it('re-seeds the welcome after the chat is cleared while mounted', () => {
    render(<AppShell />)
    expect(welcomeMessages()).toHaveLength(1)

    // A real turn arrives, then the chat is cleared — the welcome
    // should come back, matching the "empty chat always shows the
    // welcome" behavior the StrictMode latch must not break.
    act(() => useChatStore.getState().addMessage({ type: 'player', content: 'I look around.' }))
    act(() => useChatStore.getState().clearMessages())

    expect(welcomeMessages()).toHaveLength(1)
  })
})

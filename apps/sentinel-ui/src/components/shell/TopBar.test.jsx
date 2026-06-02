/**
 * Tests for TopBar's world-name wiring.
 *
 * The game-screen TopBar used to hardcode the world name; it now reads
 * the active world from playerStore (worldCreationStore is reset on
 * submit, so the name is persisted there). Heavy children are stubbed —
 * this test only covers the world-name source + fallback.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TopBar } from './TopBar'
import { usePlayerStore } from '../../stores/playerStore'

vi.mock('../persona/PersonaSheet', () => ({ PersonaSheet: () => null }))
vi.mock('../seed/SeedShareModal', () => ({ SeedShareModal: () => null }))
vi.mock('./StatusIndicator', () => ({ StatusIndicator: () => null }))

beforeEach(() => {
  usePlayerStore.setState({ worldName: '' })
})

describe('TopBar world name', () => {
  it('renders the active world name from playerStore', () => {
    usePlayerStore.setState({ worldName: 'The Hushmarket Reaches' })
    render(<TopBar />)
    expect(screen.getByText('The Hushmarket Reaches')).toBeInTheDocument()
  })

  it('falls back to a default when no world name is set', () => {
    render(<TopBar />)
    expect(screen.getByText('The Shattered Expanse')).toBeInTheDocument()
  })
})

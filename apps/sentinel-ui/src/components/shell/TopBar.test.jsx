/**
 * Tests for TopBar's world-name wiring.
 *
 * The game-screen TopBar used to hardcode the world name; it now reads
 * the active world from playerStore (worldCreationStore is reset on
 * submit, so the name is persisted there). Heavy children are stubbed —
 * this test only covers the world-name source + fallback.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { TopBar } from './TopBar'
import { usePlayerStore } from '../../stores/playerStore'
import { usePersonaStore } from '../../stores/personaStore'
import { useUIStore } from '../../stores/uiStore'

vi.mock('../persona/PersonaSheet', () => ({ PersonaSheet: () => null }))
vi.mock('../seed/SeedShareModal', () => ({ SeedShareModal: () => null }))
vi.mock('./StatusIndicator', () => ({ StatusIndicator: () => null }))
vi.mock('../../api/systemMessages', () => ({
  listMessages: vi.fn(),
}))
import { listMessages } from '../../api/systemMessages'

beforeEach(() => {
  // Reset the stores TopBar reads, so tests don't leak state into each other.
  usePlayerStore.setState({ worldName: '' })
  usePersonaStore.setState({ personaName: 'Oracle', mood: 'neutral', isLocked: true })
  useUIStore.setState({ focusMode: false, messagesLastSeenAt: null })
  listMessages.mockReset()
  listMessages.mockResolvedValue([])
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

describe('TopBar — system-messages unread indicator (RFC 0002)', () => {
  it('hides the gear dot when the feed is empty', async () => {
    listMessages.mockResolvedValue([])
    render(<TopBar />)
    await waitFor(() => expect(listMessages).toHaveBeenCalled())
    expect(screen.queryByTestId('settings-unread-dot')).toBeNull()
  })

  it('shows the gear dot when there are messages and the tester has never opened settings', async () => {
    listMessages.mockResolvedValue([
      { id: 'a', title: 't', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
    ])
    useUIStore.setState({ messagesLastSeenAt: null })
    render(<TopBar />)
    await waitFor(() =>
      expect(screen.getByTestId('settings-unread-dot')).toBeInTheDocument(),
    )
  })

  it('hides the gear dot when last-seen is after every published_at', async () => {
    listMessages.mockResolvedValue([
      { id: 'a', title: 't', body: 'b', category: 'info', pinned: false, published_at: '2026-06-10T00:00:00Z' },
    ])
    useUIStore.setState({ messagesLastSeenAt: '2026-06-14T00:00:00Z' })
    render(<TopBar />)
    await waitFor(() => expect(listMessages).toHaveBeenCalled())
    expect(screen.queryByTestId('settings-unread-dot')).toBeNull()
  })

  it('shows the gear dot when a message is newer than last-seen', async () => {
    listMessages.mockResolvedValue([
      { id: 'a', title: 't', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
    ])
    useUIStore.setState({ messagesLastSeenAt: '2026-06-13T00:00:00Z' })
    render(<TopBar />)
    await waitFor(() =>
      expect(screen.getByTestId('settings-unread-dot')).toBeInTheDocument(),
    )
  })

  it('fails closed on fetch error (no dot)', async () => {
    listMessages.mockRejectedValue(new Error('network'))
    render(<TopBar />)
    await waitFor(() => expect(listMessages).toHaveBeenCalled())
    expect(screen.queryByTestId('settings-unread-dot')).toBeNull()
  })
})

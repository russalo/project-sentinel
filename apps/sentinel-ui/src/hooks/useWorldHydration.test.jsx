/**
 * Tests for useWorldHydration — the /w/<worldId> resume hook (ADR 0002 Slice 4).
 *
 * On a fresh load it fetches GET /api/world/<worldId> and rebuilds the chat
 * scroll from the turn log + sets the session/world ids. When the store already
 * holds this world (arrived from WorldCreation), it must NOT re-fetch.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn() } }))

import { apiClient } from '../api/client'
import { useWorldHydration } from './useWorldHydration'
import { usePlayerStore } from '../stores/playerStore'
import { useChatStore } from '../stores/chatStore'

const WORLD_ID = '9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f'

const WORLD_PAYLOAD = {
  worldId: WORLD_ID,
  sessionId: '11111111-2222-3333-4444-555555555555',
  worldName: 'Saltmarsh',
  persona: 'Oracle',
  character: 'Russalo',
  startedAt: '2026-06-03T00:00:00+00:00',
  turns: [
    { turn_number: 0, player_action: '[Session Start] x', narrative: 'You arrive. <world_update>{}</world_update>' },
    { turn_number: 1, player_action: 'look around', narrative: 'Fog rolls in.' },
  ],
}

beforeEach(() => {
  apiClient.get.mockReset()
  useChatStore.getState().clearMessages()
  usePlayerStore.setState({ sessionId: null, worldId: null, worldName: '', characterName: '', characterClass: '' })
})

describe('useWorldHydration', () => {
  it('fetches the world and rebuilds the scroll + ids on a fresh load', async () => {
    apiClient.get.mockResolvedValue(WORLD_PAYLOAD)
    renderHook(() => useWorldHydration(WORLD_ID))

    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBe(WORLD_PAYLOAD.sessionId))
    expect(apiClient.get).toHaveBeenCalledWith(`/world/${WORLD_ID}`)
    expect(usePlayerStore.getState().worldId).toBe(WORLD_ID)
    expect(usePlayerStore.getState().worldName).toBe('Saltmarsh')

    const msgs = useChatStore.getState().messages
    // turn 0: synthetic [Session Start] player action skipped; DM narrative
    // kept (with the <world_update> block stripped). turn 1: player + DM.
    expect(msgs.map((m) => [m.type, m.content])).toEqual([
      ['dm', 'You arrive.'],
      ['player', 'look around'],
      ['dm', 'Fog rolls in.'],
    ])
  })

  it('does not re-fetch when the store already holds this world', async () => {
    usePlayerStore.setState({ worldId: WORLD_ID })
    renderHook(() => useWorldHydration(WORLD_ID))
    // Give any (incorrect) async effect a chance to fire.
    await new Promise((r) => setTimeout(r, 0))
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('is a no-op without a worldId', async () => {
    renderHook(() => useWorldHydration(undefined))
    await new Promise((r) => setTimeout(r, 0))
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('surfaces a load failure as a system message', async () => {
    apiClient.get.mockRejectedValue(new Error('404'))
    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some((m) => m.type === 'system' && /Could not load world/.test(m.content)),
      ).toBe(true),
    )
  })
})

/**
 * Tests for useWorldHydration — the /w/<worldId> resume hook (ADR 0002 Slice 4).
 *
 * On a fresh load it fetches GET /api/world/<worldId>, restores session / world
 * / character / persona, and rebuilds the chat scroll from the turn log. When
 * the store already holds this world (arrived from WorldCreation) it must NOT
 * re-fetch. It clears the scroll synchronously so a world-switch or a failed
 * load never leaves the previous world's chat visible.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn() } }))

import { apiClient } from '../api/client'
import { useWorldHydration } from './useWorldHydration'
import { usePlayerStore } from '../stores/playerStore'
import { usePersonaStore } from '../stores/personaStore'
import { useWorldStore } from '../stores/worldStore'
import { useChatStore } from '../stores/chatStore'

const WORLD_ID = '9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f'

const WORLD_PAYLOAD = {
  worldId: WORLD_ID,
  sessionId: '11111111-2222-3333-4444-555555555555',
  worldName: 'Saltmarsh',
  persona: 'Cowboy Bob',
  character: 'Russalo',
  characterClass: 'Warden',
  startedAt: '2026-06-03T00:00:00+00:00',
  turns: [
    { turn_number: 0, player_action: '[Session Start] x', narrative: 'You arrive. <world_update>{}</world_update>' },
    { turn_number: 1, player_action: 'look around', narrative: 'Fog rolls in.' },
  ],
}

beforeEach(() => {
  apiClient.get.mockReset()
  useChatStore.getState().clearMessages()
  useWorldStore.getState().reset()
  usePlayerStore.setState({
    sessionId: null,
    worldId: null,
    worldName: '',
    characterName: '',
    characterClass: '',
    hydrating: false,
  })
  usePersonaStore.setState({ personaId: null, personaName: 'Oracle' })
})

describe('useWorldHydration', () => {
  it('restores session/world/character/persona and rebuilds the scroll', async () => {
    apiClient.get.mockResolvedValue(WORLD_PAYLOAD)
    renderHook(() => useWorldHydration(WORLD_ID))

    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBe(WORLD_PAYLOAD.sessionId))
    expect(apiClient.get).toHaveBeenCalledWith(`/world/${WORLD_ID}`)
    expect(usePlayerStore.getState().worldId).toBe(WORLD_ID)
    expect(usePlayerStore.getState().worldName).toBe('Saltmarsh')
    expect(usePlayerStore.getState().characterClass).toBe('Warden')
    // Persona display name restored (would otherwise revert to 'Oracle').
    expect(usePersonaStore.getState().personaName).toBe('Cowboy Bob')
    // hydrating flag cleared when done.
    expect(usePlayerStore.getState().hydrating).toBe(false)

    const msgs = useChatStore.getState().messages
    // turn 0: synthetic [Session Start] player action skipped; DM narrative
    // kept (with the <world_update> block stripped). turn 1: player + DM.
    expect(msgs.map((m) => [m.type, m.content])).toEqual([
      ['dm', 'You arrive.'],
      ['player', 'look around'],
      ['dm', 'Fog rolls in.'],
    ])
  })

  it('keeps a later turn that legitimately starts with [Session Start]', async () => {
    apiClient.get.mockResolvedValue({
      ...WORLD_PAYLOAD,
      turns: [
        { turn_number: 0, player_action: '[Session Start] x', narrative: 'Intro.' },
        { turn_number: 1, player_action: '[Session Start] is a weird thing to say', narrative: 'Indeed.' },
      ],
    })
    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBeTruthy())
    const players = useChatStore.getState().messages.filter((m) => m.type === 'player')
    expect(players).toHaveLength(1)
    expect(players[0].content).toBe('[Session Start] is a weird thing to say')
  })

  it('resets worldStore so a previous world does not bleed into the panels', async () => {
    // Previous world's entities are in the panels.
    useWorldStore.getState().addCharacter({ id: 'c1', name: 'OldWorldNPC' })
    apiClient.get.mockResolvedValue(WORLD_PAYLOAD)

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBeTruthy())

    expect(useWorldStore.getState().characters).toEqual([])
  })

  it('does not re-fetch when the store already holds this world', async () => {
    usePlayerStore.setState({ worldId: WORLD_ID })
    renderHook(() => useWorldHydration(WORLD_ID))
    await new Promise((r) => setTimeout(r, 0))
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('is a no-op without a worldId', async () => {
    renderHook(() => useWorldHydration(undefined))
    await new Promise((r) => setTimeout(r, 0))
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('clears the previous world chat on a failed load and shows only the error', async () => {
    // Simulate a previous world's chat already on screen.
    useChatStore.getState().addMessage({ type: 'dm', content: 'OLD WORLD A', author: 'DM' })
    apiClient.get.mockRejectedValue(new Error('404'))

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some((m) => m.type === 'system' && /Could not load world/.test(m.content)),
      ).toBe(true),
    )
    // The old world's chat must be gone (cleared synchronously before fetch).
    const contents = useChatStore.getState().messages.map((m) => m.content)
    expect(contents).not.toContain('OLD WORLD A')
    expect(usePlayerStore.getState().hydrating).toBe(false)
  })
})

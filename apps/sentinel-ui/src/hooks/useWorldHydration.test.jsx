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

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}))

import { apiClient } from '../api/client'
import { useWorldHydration } from './useWorldHydration'
import { usePlayerStore } from '../stores/playerStore'
import { usePersonaStore } from '../stores/personaStore'
import { useWorldStore } from '../stores/worldStore'
import { useChatStore } from '../stores/chatStore'
import { clearWorldToken, getWorldToken } from '../api/worldToken'

const WORLD_ID = '9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f'

const WORLD_PAYLOAD = {
  worldId: WORLD_ID,
  sessionId: '11111111-2222-3333-4444-555555555555',
  worldName: 'Saltmarsh',
  persona: 'Cowboy Bob',
  personaId: 'cowboy-bob',
  mood: 'ominous',
  character: 'Russalo',
  characterClass: 'Warden',
  startedAt: '2026-06-03T00:00:00+00:00',
  turns: [
    { turn_number: 0, player_action: '[Session Start] x', narrative: 'You arrive. <world_update>{}</world_update>' },
    { turn_number: 1, player_action: 'look around', narrative: 'Fog rolls in.' },
  ],
  worldState: {
    worldName: 'Saltmarsh',
    currentLocation: 'The Docks',
    timeOfDay: 'Dusk',
    weather: 'Fog',
    tension: 3,
    characters: [{ name: 'Kael', status: 'alive' }],
    locations: [{ name: 'The Docks' }],
    factions: [],
    items: [],
  },
}

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.post.mockReset()
  clearWorldToken(WORLD_ID)
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
  usePersonaStore.setState({ personaId: null, personaName: 'Oracle', mood: 'neutral' })
})

// Helper: shape a fake apiClient error the way client.js does (Error with
// .status set). Used by the 401-recovery tests below.
function apiError(status) {
  const e = new Error(`API error: ${status}`)
  e.status = status
  return e
}

describe('useWorldHydration', () => {
  it('restores session/world/character/persona and rebuilds the scroll', async () => {
    apiClient.get.mockResolvedValue(WORLD_PAYLOAD)
    renderHook(() => useWorldHydration(WORLD_ID))

    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBe(WORLD_PAYLOAD.sessionId))
    // Called with the per-world token header (ADR 0003); empty in tests since
    // no token is stored in localStorage.
    expect(apiClient.get).toHaveBeenCalledWith(`/world/${WORLD_ID}`, { headers: {} })
    expect(usePlayerStore.getState().worldId).toBe(WORLD_ID)
    expect(usePlayerStore.getState().worldName).toBe('Saltmarsh')
    expect(usePlayerStore.getState().characterClass).toBe('Warden')
    // Persona restored (id + name + selected mood) — would otherwise revert to
    // the hardcoded 'Oracle'/'neutral' defaults.
    expect(usePersonaStore.getState().personaId).toBe('cowboy-bob')
    expect(usePersonaStore.getState().personaName).toBe('Cowboy Bob')
    expect(usePersonaStore.getState().mood).toBe('ominous')
    // World-state panels rehydrated.
    expect(useWorldStore.getState().characters).toEqual([{ name: 'Kael', status: 'alive' }])
    expect(useWorldStore.getState().currentLocation).toBe('The Docks')
    // Tension is stored as the raw 0-10 int the backend emits; WorldMetrics
    // derives the colour band at render time (see WorldMetrics.tensionTone).
    expect(useWorldStore.getState().tension).toBe(3)
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

    // The old world's entity is gone (reset), replaced by the new world's.
    const names = useWorldStore.getState().characters.map((c) => c.name)
    expect(names).not.toContain('OldWorldNPC')
    expect(names).toEqual(['Kael'])
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

  // ── Per-tester reauth recovery (2026-06-08) ─────────────────────────

  it('recovers from a 401 by reauthing and retrying — tester sees no error', async () => {
    // First GET 401s (stale/missing token). reauth() returns a fresh token.
    // Retry GET succeeds with the payload.
    apiClient.get
      .mockRejectedValueOnce(apiError(401))
      .mockResolvedValueOnce(WORLD_PAYLOAD)
    apiClient.post.mockResolvedValueOnce({ worldId: WORLD_ID, token: 'fresh-token-abc' })

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() => expect(usePlayerStore.getState().sessionId).toBe(WORLD_PAYLOAD.sessionId))

    // Recovery sequence: GET → POST /reauth → GET (retry).
    expect(apiClient.post).toHaveBeenCalledWith(`/world/${WORLD_ID}/reauth`, {})
    expect(apiClient.get).toHaveBeenCalledTimes(2)
    // The retry uses the freshly-stored token in the header (worldTokenHeader
    // reads from localStorage, which reauth wrote to).
    expect(getWorldToken(WORLD_ID)).toBe('fresh-token-abc')
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `/world/${WORLD_ID}`, {
      headers: { 'X-Sentinel-World-Token': 'fresh-token-abc' },
    })
    // No "Could not load world" system message — recovery was transparent.
    const sysMsgs = useChatStore.getState().messages.filter((m) => m.type === 'system')
    expect(sysMsgs).toHaveLength(0)
  })

  it('surfaces "Not your world" when reauth 403s — third-party browsing a stranger\'s URL', async () => {
    // GET 401, reauth 403 (basic_auth user is not this world's creator).
    apiClient.get.mockRejectedValue(apiError(401))
    apiClient.post.mockRejectedValueOnce(apiError(403))

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some((m) => m.type === 'system' && /Could not load world/.test(m.content)),
      ).toBe(true),
    )
    const sysMsgs = useChatStore.getState().messages.filter((m) => m.type === 'system')
    // The 403 surfaces with the specific "Not your world" reason so the player
    // knows to stop retrying — not a transient error.
    expect(sysMsgs[0].content).toMatch(/Not your world/i)
    // GET retry must NOT have happened — only the initial GET + the reauth POST.
    expect(apiClient.get).toHaveBeenCalledTimes(1)
  })

  it('does not loop on a persistent 401 — reauth runs at most once', async () => {
    // GET 401, reauth 401 (no basic_auth header reached the backend — likely
    // a dev/unenforced setup or the gate didn't proxy auth). We must not
    // loop; the original 401 bubbles up as the "Could not load world" path.
    apiClient.get.mockRejectedValue(apiError(401))
    apiClient.post.mockRejectedValueOnce(apiError(401))

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some((m) => m.type === 'system' && /Could not load world/.test(m.content)),
      ).toBe(true),
    )
    // Exactly one reauth attempt — never more.
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    // Exactly one GET — no retry after reauth failed.
    expect(apiClient.get).toHaveBeenCalledTimes(1)
  })

  it('does not reauth on a 404 — the error bubbles up cleanly', async () => {
    // World genuinely doesn't exist; reauth is the wrong recovery — skip it.
    apiClient.get.mockRejectedValue(apiError(404))

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some((m) => m.type === 'system' && /Could not load world/.test(m.content)),
      ).toBe(true),
    )
    // reauth was NOT attempted — 404 is not in the 401-recovery class.
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('handles a malformed reauth response without TypeError-ing', async () => {
    // reauth() defensively validates `data` is a non-null object before
    // accessing `.token` (gemini-medium on PR #125). A proxy returning HTML
    // parsed as null, or a backend regression dropping the body, should
    // surface as a recoverable "Could not load world" — never a crash.
    apiClient.get.mockRejectedValue(apiError(401))
    apiClient.post.mockResolvedValueOnce(null)

    renderHook(() => useWorldHydration(WORLD_ID))
    await waitFor(() =>
      expect(
        useChatStore.getState().messages.some(
          (m) => m.type === 'system' && /Could not load world/.test(m.content),
        ),
      ).toBe(true),
    )
    // No retry happened — the recovery dance bailed before re-issuing the GET.
    expect(apiClient.get).toHaveBeenCalledTimes(1)
  })
})

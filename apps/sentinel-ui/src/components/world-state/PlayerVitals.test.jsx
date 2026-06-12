/**
 * Tests for PlayerVitals — the inked humanoid silhouette + HP readout that
 * sits at the top of the world-state panel. Mirrors the band/NaN-guard
 * pattern from WorldMetrics (PR #124), with extra coverage for the
 * find-the-player logic + the no-player-yet fallback.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PlayerVitals } from './PlayerVitals'
import { useWorldStore } from '../../stores/worldStore'
import { usePlayerStore } from '../../stores/playerStore'

beforeEach(() => {
  useWorldStore.getState().reset()
  usePlayerStore.setState({
    sessionId: null,
    worldId: null,
    worldName: '',
    characterName: '',
    characterClass: '',
    hydrating: false,
  })
})

function seedPlayer(overrides = {}) {
  useWorldStore.setState({
    characters: [
      {
        name: 'Russalo',
        role: 'player',
        health: 100,
        status: 'alive',
        ...overrides,
      },
    ],
  })
}

describe('PlayerVitals — finding the player', () => {
  it('reads the player by role=player', () => {
    useWorldStore.setState({
      characters: [
        { name: 'Kael', role: 'npc', health: 100 },
        { name: 'Russalo', role: 'player', health: 80 },
        { name: 'Drogath', role: 'enemy', health: 50 },
      ],
    })
    render(<PlayerVitals />)
    // The 80/100 band is "Bruised" — proves it picked the right character.
    expect(screen.getByText(/Bruised/)).toBeInTheDocument()
    expect(screen.getByText(/80\/100/)).toBeInTheDocument()
    expect(screen.getByText('Russalo')).toBeInTheDocument()
  })

  it('falls back to name match when role is missing on the player record', () => {
    usePlayerStore.setState({ characterName: 'Russalo' })
    useWorldStore.setState({
      characters: [{ name: 'Russalo', health: 60 }], // no role
    })
    render(<PlayerVitals />)
    expect(screen.getByText(/Wounded/)).toBeInTheDocument()
    expect(screen.getByText(/60\/100/)).toBeInTheDocument()
  })

  it('renders an Unknown placeholder when no player exists yet', () => {
    // worldStore has only an NPC; playerStore has no characterName either.
    useWorldStore.setState({
      characters: [{ name: 'Kael', role: 'npc', health: 100 }],
    })
    render(<PlayerVitals />)
    // Component still renders (panel hierarchy is stable) — just shows the
    // Unknown state so screen readers know data isn't available yet.
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', 'Unknown')
  })
})

describe('PlayerVitals — bands', () => {
  it('renders Whole at 100 HP', () => {
    seedPlayer({ health: 100 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Whole/)).toBeInTheDocument()
    expect(screen.getByText(/100\/100/)).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', 'Whole — 100/100')
  })

  it('renders Bruised at 70-99 HP', () => {
    seedPlayer({ health: 85 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Bruised/)).toBeInTheDocument()
    expect(screen.getByText(/85\/100/)).toBeInTheDocument()
  })

  it('renders Wounded at 40-69 HP', () => {
    seedPlayer({ health: 50 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Wounded/)).toBeInTheDocument()
  })

  it('renders Bleeding at 10-39 HP', () => {
    seedPlayer({ health: 25 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Bleeding/)).toBeInTheDocument()
  })

  it('renders Near death at 1-9 HP', () => {
    seedPlayer({ health: 5 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Near death/)).toBeInTheDocument()
  })

  it('renders Fallen at 0 HP', () => {
    seedPlayer({ health: 0 })
    render(<PlayerVitals />)
    expect(screen.getByText(/Fallen/)).toBeInTheDocument()
    expect(screen.getByText(/0\/100/)).toBeInTheDocument()
  })

  it('renders Fallen when status=dead, regardless of HP value', () => {
    // An explicit death is more authoritative than the number. A live HP
    // value with status:dead should still surface as Fallen so the silhouette
    // can't read "Wounded — 20/100" on a corpse.
    seedPlayer({ health: 20, status: 'dead' })
    render(<PlayerVitals />)
    expect(screen.getByText(/Fallen/)).toBeInTheDocument()
  })
})

describe('PlayerVitals — edge cases', () => {
  it('treats missing health as 100 — DM-prompt "no invented history" rule', () => {
    // First-appearance characters whose health field wasn't emitted by the
    // DM should default to 100, NOT 0 (or a NaN/undefined-driven band).
    seedPlayer({ health: undefined })
    render(<PlayerVitals />)
    expect(screen.getByText(/Whole/)).toBeInTheDocument()
    expect(screen.getByText(/100\/100/)).toBeInTheDocument()
  })

  it('clamps out-of-range HP into [0, 100]', () => {
    seedPlayer({ health: 142 })
    render(<PlayerVitals />)
    expect(screen.getByText(/100\/100/)).toBeInTheDocument()
    expect(screen.getByText(/Whole/)).toBeInTheDocument()
  })

  it('treats NaN as 100 (gemini-medium guard — typeof NaN === number)', () => {
    seedPlayer({ health: NaN })
    render(<PlayerVitals />)
    // If NaN propagated through Math.max/min unchecked, aria-valuenow would
    // be the string "NaN" and the band lookup would land in the default
    // (Whole) by coincidence. Number.isFinite gates this explicitly.
    expect(screen.getByText(/100\/100/)).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '100')
  })

  it('handles negative HP by clamping to 0 + rendering Fallen', () => {
    seedPlayer({ health: -10 })
    render(<PlayerVitals />)
    expect(screen.getByText(/0\/100/)).toBeInTheDocument()
    expect(screen.getByText(/Fallen/)).toBeInTheDocument()
  })

  it('exposes ARIA meter attributes for screen readers', () => {
    seedPlayer({ health: 45 })
    render(<PlayerVitals />)
    const meter = screen.getByRole('meter')
    expect(meter).toHaveAttribute('aria-valuenow', '45')
    expect(meter).toHaveAttribute('aria-valuemin', '0')
    expect(meter).toHaveAttribute('aria-valuemax', '100')
    expect(meter).toHaveAttribute('aria-valuetext', 'Wounded — 45/100')
  })
})

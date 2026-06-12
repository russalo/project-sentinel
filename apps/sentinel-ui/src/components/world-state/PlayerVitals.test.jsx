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
    const meter = screen.getByRole('meter')
    expect(meter).toHaveAttribute('aria-valuetext', 'Unknown')
    // Per WAI-ARIA: when value is unknown, aria-valuenow must be OMITTED,
    // not set to 0 (which would announce as "Fallen / 0 HP"). gemini-medium
    // on PR #127. React drops the attr when we pass undefined.
    expect(meter).not.toHaveAttribute('aria-valuenow')
  })

  it('prefers the active session player when multiple role=player records exist', () => {
    // The codex-P2 case from PR #127: legacy/shared state can leak multiple
    // historical role=player entities into worldStore. A plain
    // find(role=player) would surface whichever comes first, potentially the
    // wrong character for the active session. With playerName set, the
    // disambiguator picks the one whose name matches the session.
    usePlayerStore.setState({ characterName: 'Russalo' })
    useWorldStore.setState({
      characters: [
        { name: 'OldCharacter', role: 'player', health: 15 }, // first in list
        { name: 'Russalo', role: 'player', health: 80 }, // active session
        { name: 'AnotherOldOne', role: 'player', health: 100 },
      ],
    })
    render(<PlayerVitals />)
    // 80/100 = Bruised; if the picker took the first record we'd see
    // Bleeding (15) and the name 'OldCharacter'.
    expect(screen.getByText(/Bruised/)).toBeInTheDocument()
    expect(screen.getByText(/80\/100/)).toBeInTheDocument()
    expect(screen.getByText('Russalo')).toBeInTheDocument()
    expect(screen.queryByText('OldCharacter')).not.toBeInTheDocument()
  })

  it('falls back to first role=player when playerName is not set', () => {
    // Early-hydration / no-session-context case: pick something rather than
    // nothing so the panel isn't blank during a brief race.
    useWorldStore.setState({
      characters: [
        { name: 'SomePlayer', role: 'player', health: 50 },
        { name: 'Kael', role: 'npc', health: 100 },
      ],
    })
    render(<PlayerVitals />)
    expect(screen.getByText(/Wounded/)).toBeInTheDocument()
    expect(screen.getByText('SomePlayer')).toBeInTheDocument()
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

describe('PlayerVitals — race-keyed body geometry (stub)', () => {
  // Stub status: every known race resolves to the same human silhouette
  // today; real per-race art is BACKLOG. These tests lock the dispatch so
  // that (a) known races never crash, (b) unknown races fall back to the
  // human default, (c) the lookup is case-insensitive + trim-tolerant
  // against whatever spelling the DM emits.
  function svgPaths() {
    // The component renders BOTH a clipPath <path> and an outline <path>
    // with the same d attribute. Either one is fine for the assertion;
    // querySelectorAll lets us pick out both for sanity.
    return Array.from(document.querySelectorAll('svg path')).map(
      (p) => p.getAttribute('d') || '',
    )
  }

  it('renders without crashing for each registered Fantasy race', () => {
    const fantasyRaces = [
      'human', 'elf', 'half-elf', 'dwarf', 'halfling',
      'gnome', 'orc', 'half-orc', 'tiefling', 'dragonborn',
    ]
    for (const race of fantasyRaces) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 100, race }],
      })
      const view = render(<PlayerVitals />)
      expect(screen.getByRole('meter')).toBeInTheDocument()
      view.unmount()
    }
  })

  it('renders identical geometry across all stubbed races (proves they all resolve to HUMAN_BODY_PATH today)', () => {
    seedPlayer({ race: 'human' })
    const view1 = render(<PlayerVitals />)
    const humanPaths = svgPaths()
    view1.unmount()

    // Pick a non-human race; should produce the same path strings until
    // per-race art lands.
    useWorldStore.setState({
      characters: [{ name: 'Russalo', role: 'player', health: 100, race: 'dwarf' }],
    })
    const view2 = render(<PlayerVitals />)
    expect(svgPaths()).toEqual(humanPaths)
    view2.unmount()
  })

  it('falls back to human geometry for an unknown race (no crash)', () => {
    seedPlayer({ race: 'android' })
    render(<PlayerVitals />)
    // Component still mounts; the silhouette is the human default.
    expect(screen.getByRole('meter')).toBeInTheDocument()
    // And the rendered geometry matches the human path (no empty d= because
    // bodyPathFor's || fallback fired).
    expect(svgPaths()[0]).toMatch(/M 36 36/)
  })

  it('falls back to human geometry when race is undefined', () => {
    seedPlayer({}) // health defaults to 100, no race field
    render(<PlayerVitals />)
    expect(screen.getByRole('meter')).toBeInTheDocument()
    expect(svgPaths()[0]).toMatch(/M 36 36/)
  })

  it('lookup is case-insensitive (Elf / ELF / elf all resolve)', () => {
    for (const race of ['Elf', 'ELF', 'elf', 'eLf']) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 100, race }],
      })
      const view = render(<PlayerVitals />)
      expect(svgPaths()[0]).toMatch(/M 36 36/)
      view.unmount()
    }
  })

  it('lookup trims surrounding whitespace from race', () => {
    seedPlayer({ race: '  dwarf  ' })
    render(<PlayerVitals />)
    expect(svgPaths()[0]).toMatch(/M 36 36/)
  })

  it('non-string race (number, object, null) falls back to human without crashing', () => {
    for (const race of [42, {}, null, true, []]) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 100, race }],
      })
      const view = render(<PlayerVitals />)
      expect(svgPaths()[0]).toMatch(/M 36 36/)
      view.unmount()
    }
  })

  it('Object.prototype keys ("constructor" / "toString" / etc.) fall back to human', () => {
    // Without the hasOwnProperty guard, RACE_BODIES['constructor'] would
    // return the prototype function — landing as a non-string `d` attribute
    // on <path>, crashing the render. (gemini-medium on PR #129.) DM emits
    // free-form race strings, so this isn't theoretical.
    for (const race of ['constructor', 'toString', 'valueOf', 'hasOwnProperty', '__proto__']) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 100, race }],
      })
      const view = render(<PlayerVitals />)
      expect(svgPaths()[0]).toMatch(/M 36 36/)
      view.unmount()
    }
  })
})

describe('PlayerVitals — wash visibility per band (Russell 2026-06-12 fix)', () => {
  // The dark codex background eats subtle opacity, so the wash uses a stepped
  // per-band floor (not a smooth (100-hp)/100 curve which produced ~9% opacity
  // at HP=90 — effectively invisible). These tests lock the floor so a
  // regression silently dimming the wash would fail CI.
  function washOpacity() {
    const wash = screen.getByTestId('vitals-damage-wash')
    return Number(wash.getAttribute('opacity'))
  }

  it('Whole (HP 100) → no wash', () => {
    seedPlayer({ health: 100 })
    render(<PlayerVitals />)
    expect(washOpacity()).toBe(0)
  })

  it('Bruised (HP 70-99) → visible wash, opacity ≥ 0.25', () => {
    seedPlayer({ health: 90 })
    render(<PlayerVitals />)
    // The exact value the pre-fix code produced at HP=90 was ~0.095;
    // anything ≥ 0.25 is the new visible-on-dark floor.
    expect(washOpacity()).toBeGreaterThanOrEqual(0.25)
  })

  it('Wounded (HP 40-69) → opacity ≥ 0.50', () => {
    seedPlayer({ health: 50 })
    render(<PlayerVitals />)
    expect(washOpacity()).toBeGreaterThanOrEqual(0.50)
  })

  it('Bleeding (HP 10-39) → opacity ≥ 0.70', () => {
    seedPlayer({ health: 20 })
    render(<PlayerVitals />)
    expect(washOpacity()).toBeGreaterThanOrEqual(0.70)
  })

  it('Near death (HP 1-9) → opacity ≥ 0.85', () => {
    seedPlayer({ health: 5 })
    render(<PlayerVitals />)
    expect(washOpacity()).toBeGreaterThanOrEqual(0.85)
  })

  it('Fallen (HP 0 or status=dead) → dim red wash, opacity ~0.40', () => {
    // Death wash is intentionally dimmer than "Near death" — the player is
    // gone, the silhouette itself drops to 30% opacity so the visual is
    // "spent" rather than "bleeding out."
    seedPlayer({ health: 0 })
    render(<PlayerVitals />)
    expect(washOpacity()).toBeGreaterThan(0)
    expect(washOpacity()).toBeLessThanOrEqual(0.50)
  })

  it('placeholder (no player) → no wash', () => {
    useWorldStore.setState({
      characters: [{ name: 'Kael', role: 'npc', health: 100 }],
    })
    render(<PlayerVitals />)
    expect(washOpacity()).toBe(0)
  })
})

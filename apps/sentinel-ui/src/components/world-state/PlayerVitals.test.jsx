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

  it('renders Dead (with skull pictogram) when status=dead, regardless of HP value', () => {
    // An explicit death is more authoritative than the number. A live HP
    // value with status:dead surfaces as Dead with the skull-and-crossbones
    // pose (RFC-0001 decision 3), not as Wounded.
    seedPlayer({ health: 20, status: 'dead' })
    render(<PlayerVitals />)
    expect(screen.getByText(/^Dead/)).toBeInTheDocument()
    expect(screen.getByTestId('vitals-skull-crossbones')).toBeInTheDocument()
  })

  it('renders Dead for capitalized "Dead" / "DEAD" / " dead " — status compare is case-insensitive', () => {
    for (const status of ['Dead', 'DEAD', ' dead ', 'dEaD']) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 20, status }],
      })
      const view = render(<PlayerVitals />)
      expect(screen.getByText(/^Dead/)).toBeInTheDocument()
      expect(screen.getByTestId('vitals-skull-crossbones')).toBeInTheDocument()
      view.unmount()
    }
  })

  it('renders Fallen at HP=0 when status is still alive (transient state)', () => {
    // HP hit zero but the DM hasn't emitted a terminal status yet — render
    // Fallen with an empty silhouette (vitality height = 0). The DM is
    // expected to follow up with status='unconscious' or 'dead' next turn.
    seedPlayer({ health: 0, status: 'alive' })
    render(<PlayerVitals />)
    expect(screen.getByText(/^Fallen/)).toBeInTheDocument()
    // Body silhouette is still there (not the skull) — this is the
    // pre-status-flip transient.
    expect(screen.queryByTestId('vitals-skull-crossbones')).not.toBeInTheDocument()
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
    // status='alive' explicit so this hits the HP=0 Fallen branch rather
    // than the dead-pose or unconscious-pose branches.
    seedPlayer({ health: -10, status: 'alive' })
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

describe('PlayerVitals — vitality fill (RFC-0001, top-down drain, bottom-anchored)', () => {
  // The fill is solid blood, height proportional to HP remaining, anchored
  // at the bottom of the SVG. As HP drops the rect's y rises and its
  // height shrinks — the "Diablo orb" idiom. Both y and height are set via
  // inline style (not XML attrs) so CSS transitions fire on Safari iOS.
  function vitalityHeight() {
    const rect = screen.getByTestId('vitals-vitality-fill')
    return parseFloat(rect.style.height || '0')
  }
  function vitalityY() {
    const rect = screen.getByTestId('vitals-vitality-fill')
    return parseFloat(rect.style.y || '0')
  }
  const SVG_HEIGHT = 180
  const MIN_VITALITY = 12

  it('HP=100 → vitality fills the entire body (height 180, y 0)', () => {
    seedPlayer({ health: 100 })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBe(SVG_HEIGHT)
    expect(vitalityY()).toBe(0)
  })

  it('HP=55 → vitality covers the bottom 55%, top 45% is empty outline', () => {
    seedPlayer({ health: 55 })
    render(<PlayerVitals />)
    // 55% of 180 = 99; y = 180 - 99 = 81
    expect(vitalityHeight()).toBeCloseTo(99, 0)
    expect(vitalityY()).toBeCloseTo(81, 0)
  })

  it('HP=50 → exactly half', () => {
    seedPlayer({ health: 50 })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBe(90)
    expect(vitalityY()).toBe(90)
  })

  it('HP=5 → tiny vitality at the feet (proportional ~9, but floor ~12)', () => {
    seedPlayer({ health: 5 })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBeGreaterThanOrEqual(MIN_VITALITY)
    expect(vitalityY()).toBeCloseTo(SVG_HEIGHT - vitalityHeight(), 1)
  })

  it('HP=1 → minimum visible vitality floor (~12 SVG units, NOT zero)', () => {
    // The floor guarantees "even at HP=1 the player can see they have
    // SOMETHING left." A strict proportional value would be 1.8 units —
    // visually zero — and lie about a still-conscious character.
    seedPlayer({ health: 1 })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBe(MIN_VITALITY)
  })

  it('HP=0 (status alive) → vitality fully empty (height 0, y at SVG floor)', () => {
    seedPlayer({ health: 0, status: 'alive' })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBe(0)
    expect(vitalityY()).toBe(SVG_HEIGHT)
  })

  it('status=unconscious → vitality empty regardless of HP (silhouette + Zzz instead)', () => {
    seedPlayer({ health: 50, status: 'unconscious' })
    render(<PlayerVitals />)
    expect(vitalityHeight()).toBe(0)
  })

  it('placeholder (no player) → vitality empty', () => {
    useWorldStore.setState({
      characters: [{ name: 'Kael', role: 'npc', health: 100 }],
    })
    render(<PlayerVitals />)
    // The skull-and-crossbones case has no vitality-fill rect at all; the
    // placeholder case still renders the rect with height 0.
    expect(vitalityHeight()).toBe(0)
  })

  it('HP=80 vs HP=20 produce visibly different vitality heights', () => {
    seedPlayer({ health: 80 })
    const v1 = render(<PlayerVitals />)
    const at80 = vitalityHeight()
    v1.unmount()
    useWorldStore.setState({
      characters: [{ name: 'Russalo', role: 'player', health: 20 }],
    })
    const v2 = render(<PlayerVitals />)
    const at20 = vitalityHeight()
    v2.unmount()
    expect(at80).toBeGreaterThan(at20)
    expect(at80 - at20).toBeGreaterThanOrEqual(60)
  })

  it('uses solid blood fill (no gradient defs in the rendered SVG)', () => {
    // RFC-0001 decision 2: drop the radial gradient entirely; the AREA of
    // the fill is now doing the work the per-band opacity stepping was
    // trying to do.
    seedPlayer({ health: 50 })
    render(<PlayerVitals />)
    const rect = screen.getByTestId('vitals-vitality-fill')
    expect(rect.getAttribute('fill')).toBe('#8c3a3a')
    // No <radialGradient> in the SVG — was previously id="vitals-damage"
    expect(document.querySelector('#vitals-damage')).toBeNull()
  })
})

describe('PlayerVitals — pose dispatch by status (RFC-0001 decision 3)', () => {
  it('status=alive → renders the humanoid silhouette, no skull, no Zzz', () => {
    seedPlayer({ health: 60, status: 'alive' })
    render(<PlayerVitals />)
    expect(screen.queryByTestId('vitals-skull-crossbones')).not.toBeInTheDocument()
    expect(screen.queryByTestId('vitals-zzz-caption')).not.toBeInTheDocument()
    expect(screen.getByTestId('vitals-vitality-fill')).toBeInTheDocument()
  })

  it('status=unconscious → silhouette + Zzz caption; no skull; vitality empty', () => {
    seedPlayer({ health: 0, status: 'unconscious' })
    render(<PlayerVitals />)
    expect(screen.getByTestId('vitals-zzz-caption')).toBeInTheDocument()
    expect(screen.queryByTestId('vitals-skull-crossbones')).not.toBeInTheDocument()
    expect(screen.getByText(/Unconscious/)).toBeInTheDocument()
  })

  it('status=unconscious is case-insensitive (Unconscious / UNCONSCIOUS / " unconscious ")', () => {
    for (const status of ['Unconscious', 'UNCONSCIOUS', ' unconscious ', 'uNcOnScIoUs']) {
      useWorldStore.setState({
        characters: [{ name: 'Russalo', role: 'player', health: 0, status }],
      })
      const view = render(<PlayerVitals />)
      expect(screen.getByTestId('vitals-zzz-caption')).toBeInTheDocument()
      expect(screen.getByText(/Unconscious/)).toBeInTheDocument()
      view.unmount()
    }
  })

  it('status=dead → skull-and-crossbones replaces the body entirely', () => {
    seedPlayer({ health: 0, status: 'dead' })
    render(<PlayerVitals />)
    expect(screen.getByTestId('vitals-skull-crossbones')).toBeInTheDocument()
    // No vitality fill, no Zzz caption, no body silhouette path — the
    // skull pictogram is the whole visual.
    expect(screen.queryByTestId('vitals-vitality-fill')).not.toBeInTheDocument()
    expect(screen.queryByTestId('vitals-zzz-caption')).not.toBeInTheDocument()
    expect(screen.getByText(/^Dead/)).toBeInTheDocument()
  })

  it('unconscious WINS over a positive HP — explicit status > the number', () => {
    // If the DM emits unconscious with a non-zero HP (mid-fight, the
    // narration explicitly knocked them out), the pose follows the status,
    // not the residual HP.
    seedPlayer({ health: 30, status: 'unconscious' })
    render(<PlayerVitals />)
    expect(screen.getByTestId('vitals-zzz-caption')).toBeInTheDocument()
    expect(screen.getByText(/Unconscious/)).toBeInTheDocument()
  })
})

describe('PlayerVitals — layout invariants', () => {
  it('SVG height class is responsive (h-20 on mobile, sm:h-24 on desktop)', () => {
    seedPlayer({ health: 100 })
    render(<PlayerVitals />)
    const svg = screen.getByRole('meter')
    const cls = svg.getAttribute('class') || ''
    expect(cls).toMatch(/\bh-20\b/)
    expect(cls).toMatch(/\bsm:h-24\b/)
  })

  it('band label and HP readout have whitespace-nowrap (never wrap on narrow widths)', () => {
    seedPlayer({ health: 5 })
    render(<PlayerVitals />)
    const band = screen.getByText(/Near death/)
    const hp = screen.getByText(/5\/100/)
    expect(band.className).toMatch(/\bwhitespace-nowrap\b/)
    expect(hp.className).toMatch(/\bwhitespace-nowrap\b/)
  })
})

/**
 * Tests for DeltaMessage — the world-state delta renderer.
 *
 * Two modes:
 *   - inline: rendered as a callout in the narrative scroll between
 *     DM turns. No turn header.
 *   - log:    rendered in the system-log tab. Includes a "Turn N"
 *     header and a timestamp.
 *
 * Pure component, takes a `delta` prop matching the shape returned
 * by computeDelta() in utils/delta.js. Tests use synthetic deltas
 * to keep coverage focused on rendering behavior, not on the diff
 * helper that's already covered in delta.test.js.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DeltaMessage } from './DeltaMessage'

// Reusable empty delta — every test starts from this and overrides
// the relevant collection.
function emptyDelta(overrides = {}) {
  return {
    world: [],
    characters: [],
    locations: [],
    factions: [],
    items: [],
    ...overrides,
  }
}

describe('DeltaMessage — inline mode (default)', () => {
  it('renders a world metric change with the from→to format', () => {
    const delta = emptyDelta({
      world: [{ field: 'weather', from: 'clear', to: 'storm' }],
    })
    render(<DeltaMessage delta={delta} />)

    // The friendly label "weather" is in the FIELD_LABEL map and
    // matches the raw field name; the value uses the → arrow the
    // component formats with.
    expect(screen.getByText('weather')).toBeInTheDocument()
    expect(screen.getByText('clear→storm')).toBeInTheDocument()
  })

  it('renders an added entity with its display name', () => {
    const delta = emptyDelta({
      characters: [
        { action: 'added', name: 'Kael', entity: { name: 'Kael', role: 'fighter' } },
      ],
    })
    render(<DeltaMessage delta={delta} />)

    // Entity name shows as the row label
    expect(screen.getByText('Kael')).toBeInTheDocument()
    // Type label is "character" (singular, from TYPE_LABEL map),
    // appended after the entity's role with " · " as separator.
    expect(screen.getByText('character · fighter')).toBeInTheDocument()
  })

  it('renders a changed entity with field deltas', () => {
    const delta = emptyDelta({
      characters: [
        {
          action: 'changed',
          name: 'Kael',
          changes: [
            { field: 'health', from: 100, to: 60 },
            { field: 'status', from: 'alive', to: 'wounded' },
          ],
        },
      ],
    })
    render(<DeltaMessage delta={delta} />)

    expect(screen.getByText('Kael')).toBeInTheDocument()
    // Multiple changes render as " · "-separated `label from→to` parts.
    // FIELD_LABEL maps health → 'hp'.
    expect(
      screen.getByText('hp 100→60 · status alive→wounded'),
    ).toBeInTheDocument()
  })

  it('renders a removed entity', () => {
    const delta = emptyDelta({
      items: [{ action: 'removed', name: 'Old Sword' }],
    })
    render(<DeltaMessage delta={delta} />)

    expect(screen.getByText('Old Sword')).toBeInTheDocument()
    // Removed rows show the type label as the detail
    expect(screen.getByText('item')).toBeInTheDocument()
  })

  it('renders nothing visible when the delta is empty', () => {
    const { container } = render(<DeltaMessage delta={emptyDelta()} />)
    // Container has the wrapper div, but no entity or world rows
    // because each collection is empty.
    expect(container.querySelectorAll('[class*="text-ether"]')).toHaveLength(0)
  })

  it('does NOT render a turn header in inline mode', () => {
    const delta = emptyDelta({
      world: [{ field: 'weather', from: 'clear', to: 'storm' }],
    })
    render(<DeltaMessage delta={delta} mode="inline" turnIdx={3} />)
    // turnIdx is ignored in inline mode
    expect(screen.queryByText(/Turn 3/)).not.toBeInTheDocument()
  })
})

describe('DeltaMessage — log mode', () => {
  it('renders the turn header with index and timestamp', () => {
    const delta = emptyDelta({
      world: [{ field: 'weather', from: 'clear', to: 'storm' }],
    })
    // Use a fixed time so the test is deterministic across timezones.
    // toLocaleTimeString with hour: '2-digit' + minute: '2-digit'
    // produces something like "14:35" — match on the prefix only
    // because the exact format depends on the test runner's locale.
    const ts = new Date('2026-04-15T14:35:00Z')
    render(
      <DeltaMessage delta={delta} mode="log" turnIdx={7} timestamp={ts} />,
    )

    // The header contains "Turn 7 · <time>". The time portion is
    // locale-dependent so we check for the parts we know about.
    const header = screen.getByText(/Turn 7/)
    expect(header).toBeInTheDocument()
    expect(header.textContent).toContain('·')
  })

  it('renders the body content the same way as inline mode', () => {
    const delta = emptyDelta({
      characters: [
        { action: 'added', name: 'Thalia', entity: { name: 'Thalia', role: 'archer' } },
      ],
    })
    render(
      <DeltaMessage
        delta={delta}
        mode="log"
        turnIdx={1}
        timestamp={new Date('2026-04-15T12:00:00Z')}
      />,
    )

    expect(screen.getByText('Thalia')).toBeInTheDocument()
    expect(screen.getByText('character · archer')).toBeInTheDocument()
  })

  it('omits the timestamp when not provided', () => {
    const delta = emptyDelta({
      world: [{ field: 'tension', from: 2, to: 7 }],
    })
    render(<DeltaMessage delta={delta} mode="log" turnIdx={4} />)

    // Header still shows turn index, but no time separator
    const header = screen.getByText(/Turn 4/)
    expect(header).toBeInTheDocument()
    expect(header.textContent).not.toContain('·')
  })
})

describe('DeltaMessage — type label mapping', () => {
  it('renders entity type labels in singular form, not 3-letter slices', () => {
    // Regression test for the issue Gemini flagged on PR #34: the
    // original implementation used `type.slice(0, 3)` which produced
    // cryptic labels like "cha" / "loc" / "fac" / "ite". The PR #34
    // merge fixed this with a TYPE_LABEL mapping; this test makes
    // sure the mapping doesn't silently regress.
    const delta = emptyDelta({
      characters: [
        { action: 'added', name: 'C', entity: { role: 'fighter' } },
      ],
      locations: [
        { action: 'added', name: 'L', entity: { type: 'tavern' } },
      ],
      factions: [
        { action: 'added', name: 'F', entity: { alignment: 'neutral' } },
      ],
      items: [{ action: 'added', name: 'I', entity: { type: 'weapon' } }],
    })
    render(<DeltaMessage delta={delta} />)

    // Singular labels — not "cha"/"loc"/"fac"/"ite"
    expect(screen.getByText('character · fighter')).toBeInTheDocument()
    expect(screen.getByText('location · tavern')).toBeInTheDocument()
    expect(screen.getByText('faction · neutral')).toBeInTheDocument()
    expect(screen.getByText('item · weapon')).toBeInTheDocument()
  })
})

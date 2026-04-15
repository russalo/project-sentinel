/**
 * Tests for EntityCard — the shared entity-detail primitive.
 *
 * EntityCard is pure: takes (entity, type, onClose) props, renders
 * a header + body, no store dependencies. The first React-component
 * test target because the rendering surface is small and the
 * fixture data shape is well-defined per worldStore.
 *
 * Each test renders with a typed fixture and asserts the visible
 * behavior — text content, conditional rows, the close button when
 * it's wired. Implementation details (CSS classes, DOM structure)
 * are deliberately not tested.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EntityCard } from './EntityCard'

describe('EntityCard — header', () => {
  it('renders the entity name and type label', () => {
    render(
      <EntityCard
        entity={{ name: 'Kael', role: 'fighter' }}
        type="character"
      />,
    )
    expect(screen.getByText('Kael')).toBeInTheDocument()
    // Type label is the lowercase string passed in; CSS uppercases it
    // visually via `capitalize`, so the DOM still reads "character".
    expect(screen.getByText('character')).toBeInTheDocument()
  })

  it('renders nothing when given an unknown type', () => {
    const { container } = render(
      <EntityCard entity={{ name: 'X' }} type="dragon-rider" />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when entity is null', () => {
    const { container } = render(<EntityCard entity={null} type="character" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('EntityCard — close button', () => {
  it('omits the close button when onClose is not provided', () => {
    render(<EntityCard entity={{ name: 'Kael' }} type="character" />)
    expect(screen.queryByLabelText('Close')).not.toBeInTheDocument()
  })

  it('renders the close button and calls onClose when clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <EntityCard
        entity={{ name: 'Kael' }}
        type="character"
        onClose={onClose}
      />,
    )
    const closeBtn = screen.getByLabelText('Close')
    await user.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('EntityCard — character body', () => {
  it('renders all populated character fields', () => {
    render(
      <EntityCard
        entity={{
          name: 'Kael',
          role: 'fighter',
          class: 'paladin',
          race: 'human',
          level: 5,
          health: 80,
          maxHealth: 100,
          status: 'alive',
          currentLocation: 'Trog Tavern',
          traits: ['brave', 'reckless'],
          description: 'A weathered warrior.',
        }}
        type="character"
      />,
    )

    expect(screen.getByText('fighter')).toBeInTheDocument()
    expect(screen.getByText('paladin')).toBeInTheDocument()
    expect(screen.getByText('human')).toBeInTheDocument()
    // Health renders as "current / max"
    expect(screen.getByText('80 / 100')).toBeInTheDocument()
    expect(screen.getByText('alive')).toBeInTheDocument()
    expect(screen.getByText('Trog Tavern')).toBeInTheDocument()
    // Array fields are joined with ", "
    expect(screen.getByText('brave, reckless')).toBeInTheDocument()
    expect(screen.getByText('A weathered warrior.')).toBeInTheDocument()
  })

  it('hides empty rows', () => {
    // Only `name` is set. Header is rendered (name + type), body
    // rows for empty fields are all hidden by the Row helper's
    // null/undefined/empty check. The result is a card with just
    // the header and no field rows underneath.
    render(<EntityCard entity={{ name: 'Kael' }} type="character" />)

    // No "Role" label visible — Row returns null for missing values
    expect(screen.queryByText('Role')).not.toBeInTheDocument()
    expect(screen.queryByText('Class')).not.toBeInTheDocument()
    expect(screen.queryByText('Health')).not.toBeInTheDocument()
  })

  it('reads snake_case fallback fields when camelCase is absent', () => {
    // Backend payloads occasionally use snake_case
    // (current_location, max_health, class_name). The character
    // card's `??` fallback pattern should render them anyway.
    render(
      <EntityCard
        entity={{
          name: 'Kael',
          class_name: 'paladin',
          health: 80,
          max_health: 100,
          current_location: 'Trog Tavern',
        }}
        type="character"
      />,
    )

    expect(screen.getByText('paladin')).toBeInTheDocument()
    expect(screen.getByText('80 / 100')).toBeInTheDocument()
    expect(screen.getByText('Trog Tavern')).toBeInTheDocument()
  })
})

describe('EntityCard — item body', () => {
  it('reads ownedBy and owned_by interchangeably', () => {
    // Two renders, one for each casing — both should produce the
    // same visible "Owned by" row. Mirrors the diff-layer
    // normalization landed in PR #36.
    const { rerender } = render(
      <EntityCard
        entity={{ name: 'Iron Sword', type: 'weapon', ownedBy: 'Kael' }}
        type="item"
      />,
    )
    expect(screen.getByText('Kael')).toBeInTheDocument()

    rerender(
      <EntityCard
        entity={{ name: 'Iron Sword', type: 'weapon', owned_by: 'Kael' }}
        type="item"
      />,
    )
    expect(screen.getByText('Kael')).toBeInTheDocument()
  })

  it('renders item-specific fields (rarity, magical, type)', () => {
    render(
      <EntityCard
        entity={{
          name: 'Shadow Blade',
          type: 'weapon',
          rarity: 'rare',
          magical: true,
          location: 'Hollowed Temple',
        }}
        type="item"
      />,
    )

    expect(screen.getByText('weapon')).toBeInTheDocument()
    expect(screen.getByText('rare')).toBeInTheDocument()
    expect(screen.getByText('Yes')).toBeInTheDocument() // magical: true → "Yes"
    expect(screen.getByText('Hollowed Temple')).toBeInTheDocument()
  })
})

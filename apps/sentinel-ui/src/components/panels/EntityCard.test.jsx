import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EntityCard } from './EntityCard';

// ── header + close button ───────────────────────────────────────────

describe('EntityCard — header and close button', () => {
  it('renders the entity name and type label', () => {
    const entity = { name: 'Thalia', role: 'ranger' };
    render(<EntityCard entity={entity} type="character" />);
    expect(screen.getByText('Thalia')).toBeInTheDocument();
    expect(screen.getByText('character')).toBeInTheDocument();
  });

  it('renders a close button when onClose is provided', () => {
    const onClose = vi.fn();
    render(<EntityCard entity={{ name: 'Thalia' }} type="character" onClose={onClose} />);
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<EntityCard entity={{ name: 'Thalia' }} type="character" onClose={onClose} />);
    await user.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not render a close button when onClose is absent', () => {
    render(<EntityCard entity={{ name: 'Thalia' }} type="character" />);
    expect(screen.queryByLabelText('Close')).not.toBeInTheDocument();
  });

  it('returns null when entity is missing', () => {
    const { container } = render(<EntityCard entity={null} type="character" />);
    expect(container.firstChild).toBeNull();
  });

  it('returns null for an unknown type', () => {
    const { container } = render(<EntityCard entity={{ name: 'X' }} type="unknown" />);
    expect(container.firstChild).toBeNull();
  });
});

// ── CharacterCard ───────────────────────────────────────────────────

describe('EntityCard — CharacterCard', () => {
  it('renders role, status, and formatted health', () => {
    const entity = {
      name: 'Thalia',
      role: 'ranger',
      status: 'wounded',
      health: 60,
      maxHealth: 100,
    };
    render(<EntityCard entity={entity} type="character" />);
    expect(screen.getByText('ranger')).toBeInTheDocument();
    expect(screen.getByText('wounded')).toBeInTheDocument();
    expect(screen.getByText('60 / 100')).toBeInTheDocument();
  });

  it('accepts snake_case max_health as a fallback', () => {
    const entity = { name: 'Thalia', health: 60, max_health: 100 };
    render(<EntityCard entity={entity} type="character" />);
    expect(screen.getByText('60 / 100')).toBeInTheDocument();
  });

  it('skips null and undefined fields', () => {
    const entity = { name: 'Thalia', role: 'ranger' };
    render(<EntityCard entity={entity} type="character" />);
    expect(screen.queryByText('Status')).not.toBeInTheDocument();
    expect(screen.queryByText('Health')).not.toBeInTheDocument();
    expect(screen.queryByText('Level')).not.toBeInTheDocument();
  });

  it('renders traits as a comma-joined string when given an array', () => {
    const entity = { name: 'Thalia', traits: ['keen-eyed', 'patient'] };
    render(<EntityCard entity={entity} type="character" />);
    expect(screen.getByText('keen-eyed, patient')).toBeInTheDocument();
  });
});

// ── LocationCard ────────────────────────────────────────────────────

describe('EntityCard — LocationCard', () => {
  it('renders type, region, danger, and discovered', () => {
    const entity = {
      name: 'Hollowed Temple',
      type: 'ruin',
      region: 'Thornwatch',
      danger: 7,
      discovered: true,
    };
    render(<EntityCard entity={entity} type="location" />);
    expect(screen.getByText('ruin')).toBeInTheDocument();
    expect(screen.getByText('Thornwatch')).toBeInTheDocument();
    expect(screen.getByText('7/10')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('renders "No" for undiscovered locations', () => {
    const entity = { name: 'Hidden Cave', discovered: false };
    render(<EntityCard entity={entity} type="location" />);
    expect(screen.getByText('No')).toBeInTheDocument();
  });
});

// ── FactionCard ─────────────────────────────────────────────────────

describe('EntityCard — FactionCard', () => {
  it('renders alignment, power, and playerRelation', () => {
    const entity = {
      name: 'The Order',
      alignment: 'lawful',
      power: 8,
      playerRelation: 3,
    };
    render(<EntityCard entity={entity} type="faction" />);
    expect(screen.getByText('lawful')).toBeInTheDocument();
    expect(screen.getByText('8/10')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('falls back to snake_case player_relation', () => {
    const entity = { name: 'The Order', player_relation: 5 };
    render(<EntityCard entity={entity} type="faction" />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});

// ── ItemCard ────────────────────────────────────────────────────────

describe('EntityCard — ItemCard', () => {
  it('renders type, rarity, and ownedBy', () => {
    const entity = {
      name: 'Shadow Blade',
      type: 'weapon',
      rarity: 'rare',
      ownedBy: 'Thalia',
    };
    render(<EntityCard entity={entity} type="item" />);
    expect(screen.getByText('weapon')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getByText('Thalia')).toBeInTheDocument();
  });

  it('falls back to snake_case owned_by when ownedBy is absent', () => {
    const entity = { name: 'Shadow Blade', owned_by: 'Russalo' };
    render(<EntityCard entity={entity} type="item" />);
    expect(screen.getByText('Russalo')).toBeInTheDocument();
  });

  it('renders "Yes" for magical items and "No" for non-magical', () => {
    const { rerender } = render(
      <EntityCard entity={{ name: 'Shadow Blade', magical: true }} type="item" />,
    );
    expect(screen.getByText('Yes')).toBeInTheDocument();

    rerender(<EntityCard entity={{ name: 'Rusty Sword', magical: false }} type="item" />);
    expect(screen.getByText('No')).toBeInTheDocument();
  });

  it('skips the magical row entirely when the field is absent', () => {
    render(<EntityCard entity={{ name: 'Shadow Blade' }} type="item" />);
    expect(screen.queryByText('Magical')).not.toBeInTheDocument();
  });
});

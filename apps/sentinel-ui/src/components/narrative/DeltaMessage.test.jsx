import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DeltaMessage } from './DeltaMessage';

// ── fixture helpers ──────────────────────────────────────────────────

function emptyDelta() {
  return { world: [], characters: [], locations: [], factions: [], items: [] };
}

// ── world-field changes ─────────────────────────────────────────────

describe('DeltaMessage — world-field changes', () => {
  it('renders a currentLocation change with the friendly label', () => {
    const delta = {
      ...emptyDelta(),
      world: [{ field: 'currentLocation', from: 'Tavern', to: 'Forest' }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('location')).toBeInTheDocument();
    expect(screen.getByText('Tavern→Forest')).toBeInTheDocument();
  });

  it('renders a tension change with numeric from→to', () => {
    const delta = {
      ...emptyDelta(),
      world: [{ field: 'tension', from: 3, to: 7 }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('tension')).toBeInTheDocument();
    expect(screen.getByText('3→7')).toBeInTheDocument();
  });
});

// ── entity added / removed / changed ────────────────────────────────

describe('DeltaMessage — entity actions', () => {
  it('renders an added character with the full type label (not "cha")', () => {
    const delta = {
      ...emptyDelta(),
      characters: [{ action: 'added', name: 'Thalia', entity: { name: 'Thalia', role: 'ranger' } }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('Thalia')).toBeInTheDocument();
    // Regression guard: used to be 'cha', 'loc', 'fac', 'ite' from type.slice(0,3)
    expect(screen.getByText(/character · ranger/)).toBeInTheDocument();
  });

  it('renders an added location with the full type label', () => {
    const delta = {
      ...emptyDelta(),
      locations: [{ action: 'added', name: 'Hollowed Temple', entity: { name: 'Hollowed Temple', type: 'ruin' } }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('Hollowed Temple')).toBeInTheDocument();
    expect(screen.getByText(/location · ruin/)).toBeInTheDocument();
  });

  it('renders an added item with the full type label', () => {
    const delta = {
      ...emptyDelta(),
      items: [{ action: 'added', name: 'Shadow Blade', entity: { name: 'Shadow Blade' } }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('Shadow Blade')).toBeInTheDocument();
    expect(screen.getByText('item')).toBeInTheDocument();
  });

  it('renders a removed character with the full type label', () => {
    const delta = {
      ...emptyDelta(),
      characters: [{ action: 'removed', name: 'Thalia' }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('Thalia')).toBeInTheDocument();
    expect(screen.getByText('character')).toBeInTheDocument();
  });

  it('renders a changed character with a list of field changes', () => {
    const delta = {
      ...emptyDelta(),
      characters: [{
        action: 'changed',
        name: 'Thalia',
        changes: [
          { field: 'health', from: 100, to: 60 },
          { field: 'status', from: 'healthy', to: 'wounded' },
        ],
      }],
    };
    render(<DeltaMessage delta={delta} />);
    expect(screen.getByText('Thalia')).toBeInTheDocument();
    expect(screen.getByText(/hp 100→60/)).toBeInTheDocument();
    expect(screen.getByText(/status healthy→wounded/)).toBeInTheDocument();
  });
});

// ── mode: inline vs log ─────────────────────────────────────────────

describe('DeltaMessage — inline vs log mode', () => {
  const delta = {
    ...emptyDelta(),
    world: [{ field: 'tension', from: 3, to: 5 }],
  };

  it('inline mode renders no Turn header', () => {
    const { container } = render(<DeltaMessage delta={delta} mode="inline" />);
    expect(container.textContent).not.toMatch(/Turn/);
  });

  it('log mode renders a Turn header with the turn index', () => {
    render(<DeltaMessage delta={delta} mode="log" turnIdx={7} />);
    expect(screen.getByText(/Turn 7/)).toBeInTheDocument();
  });

  it('log mode renders a timestamp when provided', () => {
    // Fixed time to avoid flakiness — 14:30 local time
    const ts = new Date();
    ts.setHours(14, 30, 0, 0);
    render(<DeltaMessage delta={delta} mode="log" turnIdx={1} timestamp={ts} />);
    // Match HH:MM (locale-agnostic — just check digits-colon-digits)
    const header = screen.getByText(/Turn 1/);
    expect(header.textContent).toMatch(/\d{1,2}:\d{2}/);
  });
});

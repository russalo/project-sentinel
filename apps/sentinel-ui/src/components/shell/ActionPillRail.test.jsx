import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActionPillRail } from './ActionPillRail';
import { useChatStore } from '../../stores/chatStore';

beforeEach(() => {
  useChatStore.setState({ input: '', suggestedActions: [] });
});

describe('ActionPillRail', () => {
  it('renders always-available pills even when no DM suggestions exist', () => {
    render(<ActionPillRail />);
    expect(
      screen.getByRole('button', { name: 'Always-available action: Look around' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Always-available action: Wait' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Always-available action: Rest' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Always-available action: Inventory' }),
    ).toBeInTheDocument();
  });

  it('renders DM-suggested pills alongside always-available ones', () => {
    useChatStore.setState({
      suggestedActions: [
        { label: 'strike with shadow magic', tone: 'aggressive' },
        { label: 'parry the strike', tone: 'defensive' },
      ],
    });
    render(<ActionPillRail />);
    expect(
      screen.getByRole('button', { name: 'Suggested action: strike with shadow magic' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Suggested action: parry the strike' }),
    ).toBeInTheDocument();
    // Always-available rail still visible
    expect(
      screen.getByRole('button', { name: 'Always-available action: Look around' }),
    ).toBeInTheDocument();
  });

  it('clicking a DM pill populates chatStore.input', async () => {
    useChatStore.setState({
      suggestedActions: [{ label: 'strike', tone: 'aggressive' }],
    });
    render(<ActionPillRail />);
    await userEvent.click(screen.getByRole('button', { name: 'Suggested action: strike' }));
    expect(useChatStore.getState().input).toBe('strike');
  });

  it('clicking an always-available pill populates chatStore.input', async () => {
    render(<ActionPillRail />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Always-available action: Wait' }),
    );
    expect(useChatStore.getState().input).toBe('Wait');
  });

  it('deduplicates DM pills that overlap with always-available labels (case-insensitive)', () => {
    useChatStore.setState({
      suggestedActions: [
        { label: 'look around', tone: 'curious' },  // dup vs Always-Available "Look around"
        { label: 'flee', tone: 'cautious' },
      ],
    });
    render(<ActionPillRail />);
    // Only ONE Look-around pill should exist (the always-available one).
    expect(
      screen.queryByRole('button', { name: 'Suggested action: look around' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Always-available action: Look around' }),
    ).toBeInTheDocument();
    // Other DM pills still render.
    expect(
      screen.getByRole('button', { name: 'Suggested action: flee' }),
    ).toBeInTheDocument();
  });

  it('handles a malformed suggestedActions entry gracefully (missing label dropped)', () => {
    useChatStore.setState({
      suggestedActions: [
        { tone: 'aggressive' },                            // no label
        { label: '', tone: 'aggressive' },                 // empty label
        { label: 'real action', tone: 'aggressive' },
      ],
    });
    render(<ActionPillRail />);
    expect(screen.getByRole('button', { name: 'Suggested action: real action' })).toBeInTheDocument();
    // No buttons for the malformed entries.
    const allDmPills = screen.queryAllByRole('button').filter((b) => b.getAttribute('aria-label')?.startsWith('Suggested action'));
    expect(allDmPills).toHaveLength(1);
  });

  it('falls back to neutral styling for unknown tone (prompt drift)', () => {
    useChatStore.setState({
      suggestedActions: [{ label: 'mystery move', tone: 'unknown_tone_xyz' }],
    });
    render(<ActionPillRail />);
    const pill = screen.getByRole('button', { name: 'Suggested action: mystery move' });
    // Neutral classes (border-border) should be present rather than crashing.
    expect(pill.className).toContain('border-border');
  });
});

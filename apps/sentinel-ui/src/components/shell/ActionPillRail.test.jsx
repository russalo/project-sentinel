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

  it('all DM pills use the same amber class regardless of tone (tones not visualized in v1)', () => {
    // Per 2026-06-07 UX call: drop the tone-rainbow until we can convey color
    // meaning to the player. The `tone` field is still ingested + persisted —
    // just not visualized today. Any tone (or no tone, or a malformed tone)
    // produces the same amber pill styling, matching the inline `<action>`
    // highlights in NarrativeText.
    useChatStore.setState({
      suggestedActions: [
        { label: 'A', tone: 'aggressive' },
        { label: 'B', tone: 'cautious' },
        { label: 'C', tone: 'unknown_tone_xyz' },
        { label: 'D' },  // no tone at all
      ],
    });
    render(<ActionPillRail />);
    const a = screen.getByRole('button', { name: 'Suggested action: A' });
    const b = screen.getByRole('button', { name: 'Suggested action: B' });
    const c = screen.getByRole('button', { name: 'Suggested action: C' });
    const d = screen.getByRole('button', { name: 'Suggested action: D' });
    // All DM pills share the same amber-themed class — no tone-specific
    // coloring (rust / cobalt / moss / ether) leaks into the rendered class.
    expect(a.className).toContain('border-amber');
    expect(b.className).toContain('border-amber');
    expect(c.className).toContain('border-amber');
    expect(d.className).toContain('border-amber');
    expect(a.className).not.toContain('border-rust');
    expect(a.className).not.toContain('border-cobalt');
    expect(a.className).not.toContain('border-moss');
    expect(a.className).not.toContain('border-ether');
  });
});

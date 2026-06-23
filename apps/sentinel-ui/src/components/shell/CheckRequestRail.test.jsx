import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CheckRequestRail } from './CheckRequestRail';
import { useChatStore } from '../../stores/chatStore';
import { useWorldStore } from '../../stores/worldStore';
import { usePlayerStore } from '../../stores/playerStore';

const sendRoll = vi.fn();
vi.mock('../../hooks/useDMStream', () => ({
  useDMStream: () => ({ sendRoll, sendAction: vi.fn() }),
}));

// Deterministic d100 (first roll = 47).
function stubD100(...values) {
  let i = 0;
  vi.spyOn(Math, 'random').mockImplementation(() => (values[i++] - 1) / 100);
}

beforeEach(() => {
  sendRoll.mockReset();
  vi.restoreAllMocks();
  useChatStore.setState({ checkRequest: null, isStreaming: false, messages: [] });
  useWorldStore.setState({
    characters: [
      {
        name: 'Russalo',
        role: 'player',
        module_data: { character_sheet: { stats: { body: 6, mind: 5, heart: 4, will: 8 } } },
      },
    ],
  });
  usePlayerStore.setState({ characterName: 'Russalo', sessionId: 'sess-1' });
});

describe('CheckRequestRail', () => {
  it('renders nothing when there is no check request', () => {
    const { container } = render(<CheckRequestRail />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the request affordance with stat + target band', () => {
    useChatStore.setState({
      checkRequest: { stat: 'body', target: 80, label: 'Force it', prompt: 'The iron is fast.' },
    });
    render(<CheckRequestRail />);
    expect(screen.getByText(/Body check — Hard \(80\)/)).toBeInTheDocument();
    expect(screen.getByText('The iron is fast.')).toBeInTheDocument();
    expect(screen.getByTestId('check-roll-button')).toBeInTheDocument();
  });

  it('rolling reveals the result using the player stat ×5 and the band', async () => {
    stubD100(47); // 47 + (body 6 ×5 = 30) = 77 vs 80 → margin −3
    useChatStore.setState({
      checkRequest: { stat: 'body', target: 80, label: 'Force it' },
    });
    render(<CheckRequestRail />);
    await userEvent.click(screen.getByTestId('check-roll-button'));
    const reveal = screen.getByTestId('check-reveal');
    expect(reveal).toHaveTextContent('47');
    expect(reveal).toHaveTextContent('+30');
    expect(reveal).toHaveTextContent('77');
    expect(reveal).toHaveTextContent('margin -3');
    expect(reveal).toHaveTextContent('Near miss');
  });

  it('rolling logs a roll line to the scroll and resends with the wire payload', async () => {
    stubD100(47);
    useChatStore.setState({
      checkRequest: { stat: 'body', target: 80, label: 'Force it' },
    });
    render(<CheckRequestRail />);
    await userEvent.click(screen.getByTestId('check-roll-button'));

    // A roll line was added to the scroll (beat 3) — synchronously on click.
    const msgs = useChatStore.getState().messages;
    expect(msgs.some((m) => m.type === 'system' && /margin -3/.test(m.content))).toBe(true);

    // After the reveal pause (real 900ms timeout), the turn resends with the
    // wire payload. waitFor polls until the deferred sendRoll fires.
    await waitFor(() => expect(sendRoll).toHaveBeenCalledTimes(1), { timeout: 2000 });
    const [wire, label, sessionId] = sendRoll.mock.calls[0];
    expect(wire).toMatchObject({ stat: 'body', rolled: 47, bonus: 30, total: 77, target: 80, margin: -3 });
    expect(wire.statValue).toBeUndefined(); // wire payload only
    expect(label).toBe('Force it');
    expect(sessionId).toBe('sess-1');
  });

  it('defaults a missing stat to 5 so a roll never strands', async () => {
    stubD100(50); // 50 + (default 5 ×5 = 25) = 75 vs 60 → margin +15
    useWorldStore.setState({
      characters: [{ name: 'Russalo', role: 'player' }], // no character_sheet
    });
    useChatStore.setState({ checkRequest: { stat: 'body', target: 60, label: 'x' } });
    render(<CheckRequestRail />);
    await userEvent.click(screen.getByTestId('check-roll-button'));
    const reveal = screen.getByTestId('check-reveal');
    expect(reveal).toHaveTextContent('+25'); // 5 × 5
    expect(reveal).toHaveTextContent('Solid'); // margin +15
  });

  it('roll button is disabled while streaming', () => {
    useChatStore.setState({
      checkRequest: { stat: 'body', target: 80, label: 'x' },
      isStreaming: true,
    });
    render(<CheckRequestRail />);
    expect(screen.getByTestId('check-roll-button')).toBeDisabled();
  });
});

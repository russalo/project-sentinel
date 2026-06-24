import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LevelUpCard } from './LevelUpCard';
import { useChatStore } from '../../stores/chatStore';
import { useWorldStore } from '../../stores/worldStore';
import { usePlayerStore } from '../../stores/playerStore';

const sendLevelUp = vi.fn();
vi.mock('../../hooks/useDMStream', () => ({
  useDMStream: () => ({ sendLevelUp, sendAction: vi.fn(), sendRoll: vi.fn() }),
}));

beforeEach(() => {
  sendLevelUp.mockReset();
  vi.restoreAllMocks();
  useChatStore.setState({ levelUp: null, isStreaming: false, messages: [] });
  useWorldStore.setState({
    characters: [
      {
        name: 'Russalo',
        role: 'player',
        module_data: { character_sheet: { stats: { body: 6, mind: 5, heart: 4, will: 10 } } },
      },
    ],
  });
  usePlayerStore.setState({ characterName: 'Russalo', sessionId: 'sess-1' });
});

describe('LevelUpCard', () => {
  it('renders nothing when there is no level-up proposal', () => {
    const { container } = render(<LevelUpCard />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the proposal with the target level and a button per stat', () => {
    useChatStore.setState({ levelUp: { toLevel: 3 } });
    render(<LevelUpCard />);
    expect(screen.getByText(/reached level 3/)).toBeInTheDocument();
    for (const stat of ['body', 'mind', 'heart', 'will']) {
      expect(screen.getByTestId(`level-up-stat-${stat}`)).toBeInTheDocument();
    }
    // Shows what each pick would become (e.g. Body 6 → 7).
    expect(screen.getByTestId('level-up-stat-body')).toHaveTextContent('6 → 7');
  });

  it('a stat already at the cap is disabled and shows (max)', () => {
    useChatStore.setState({ levelUp: { toLevel: 3 } });
    render(<LevelUpCard />);
    const will = screen.getByTestId('level-up-stat-will'); // will is 10
    expect(will).toBeDisabled();
    expect(will).toHaveTextContent('max');
  });

  it('confirm is disabled until a stat is picked, then enacts the choice', async () => {
    useChatStore.setState({ levelUp: { toLevel: 2 } });
    render(<LevelUpCard />);
    expect(screen.getByTestId('level-up-confirm')).toBeDisabled();

    await userEvent.click(screen.getByTestId('level-up-stat-mind'));
    expect(screen.getByTestId('level-up-stat-mind')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('level-up-confirm')).toBeEnabled();

    await userEvent.click(screen.getByTestId('level-up-confirm'));

    // A line drops into the scroll, and the choice resends.
    const msgs = useChatStore.getState().messages;
    expect(msgs.some((m) => m.type === 'system' && /Level 2 — raised Mind/.test(m.content))).toBe(true);
    expect(sendLevelUp).toHaveBeenCalledTimes(1);
    expect(sendLevelUp).toHaveBeenCalledWith('mind', 2, 'sess-1');
  });

  it('stat buttons are disabled while streaming', () => {
    useChatStore.setState({ levelUp: { toLevel: 2 }, isStreaming: true });
    render(<LevelUpCard />);
    expect(screen.getByTestId('level-up-stat-body')).toBeDisabled();
    expect(screen.getByTestId('level-up-confirm')).toBeDisabled();
  });
});

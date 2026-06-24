import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CommandBar } from './CommandBar';
import { useChatStore } from '../../stores/chatStore';
import { usePlayerStore } from '../../stores/playerStore';

const sendAction = vi.fn();
vi.mock('../../hooks/useDMStream', () => ({
  useDMStream: () => ({ sendAction, sendRoll: vi.fn(), sendLevelUp: vi.fn() }),
}));

// ActionPillRail / CheckRequestRail / LevelUpCard pull from stores too; render
// them inert so this test focuses on the command bar's own lock behavior.
vi.mock('./ActionPillRail', () => ({ ActionPillRail: () => null }));
vi.mock('./CheckRequestRail', () => ({ CheckRequestRail: () => null }));
vi.mock('./LevelUpCard', () => ({ LevelUpCard: () => null }));

beforeEach(() => {
  sendAction.mockReset();
  useChatStore.setState({ input: '', isStreaming: false, rollPending: false, messages: [] });
  usePlayerStore.setState({ sessionId: 'sess-1' });
});

describe('CommandBar — rollPending lock (player-paced roll, PR #151 follow-up)', () => {
  it('input + send are enabled in the ordinary idle state', () => {
    render(<CommandBar />);
    expect(screen.getByTestId('command-bar-input')).toBeEnabled();
    expect(screen.getByTestId('command-bar-send')).toBeEnabled();
  });

  it('locks input + send while a rolled check awaits resolution', () => {
    useChatStore.setState({ rollPending: true });
    render(<CommandBar />);
    expect(screen.getByTestId('command-bar-input')).toBeDisabled();
    expect(screen.getByTestId('command-bar-send')).toBeDisabled();
    expect(screen.getByTestId('command-bar-input')).toHaveAttribute(
      'placeholder', 'Resolve the roll to continue...');
  });

  it('does not send an action while rollPending — the roll cannot be discarded by typing', () => {
    useChatStore.setState({ rollPending: true, input: 'run away instead' });
    render(<CommandBar />);
    // Even forcing a click on the (disabled) send does nothing.
    screen.getByTestId('command-bar-send').click();
    expect(sendAction).not.toHaveBeenCalled();
  });

  it('is also locked while streaming (unchanged behavior)', () => {
    useChatStore.setState({ isStreaming: true });
    render(<CommandBar />);
    expect(screen.getByTestId('command-bar-input')).toBeDisabled();
    expect(screen.getByTestId('command-bar-send')).toBeDisabled();
  });
});

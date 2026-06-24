import { Send } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { usePlayerStore } from '../../stores/playerStore';
import { useDMStream } from '../../hooks/useDMStream';
import { ActionPillRail } from './ActionPillRail';
import { CheckRequestRail } from './CheckRequestRail';
import { LevelUpCard } from './LevelUpCard';

// `input` is lifted to chatStore so the ActionPillRail and inline `<action>`
// highlights (NarrativeText) can populate the field via setInput(label). The
// pills NEVER auto-submit — the player still reviews / edits before sending.
// See BACKLOG-#474 + project_canon_modules_framing memory for the spec.
export function CommandBar() {
  const { input, setInput, addMessage, isStreaming, rollPending } = useChatStore();
  const { sessionId } = usePlayerStore();
  const { sendAction } = useDMStream();

  // `rollPending` locks the bar while a rolled-but-unresolved check is on
  // screen, so a revealed roll can't be silently discarded by typing past it
  // (the player resolves via CheckRequestRail's Resolve button). Lifts on
  // Resolve / next turn. See chatStore.rollPending.
  const locked = isStreaming || rollPending;

  const handleSubmit = () => {
    if (!input.trim() || locked) return;
    const action = input.trim();
    setInput('');
    addMessage({
      type: 'player',
      content: action,
      timestamp: new Date(),
    });
    sendAction(action, sessionId);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <footer
      className="bg-codex border-t border-border"
      style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
    >
      <CheckRequestRail />
      <LevelUpCard />
      <ActionPillRail />
      <div
        className="px-3 lg:px-6 pt-1 flex gap-2 lg:gap-3"
      >
        <div className="flex-1 flex gap-2">
          <input
            data-testid="command-bar-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              !sessionId
                ? 'Start a new world to begin...'
                : rollPending
                  ? 'Resolve the roll to continue...'
                  : 'What do you do?'
            }
            disabled={locked || !sessionId}
            className="flex-1 bg-void border border-border rounded px-3 py-2.5 text-base md:text-sm text-ink placeholder-dust focus:outline-none focus:border-amber transition-colors disabled:opacity-50"
          />
          <button
            data-testid="command-bar-send"
            onClick={handleSubmit}
            disabled={locked || !sessionId}
            className="px-4 py-2.5 bg-amber text-void rounded hover:bg-amber/90 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </footer>
  );
}

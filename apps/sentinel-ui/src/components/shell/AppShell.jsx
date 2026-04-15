import { useEffect } from 'react';
import { useUIStore } from '../../stores/uiStore';
import { useChatStore } from '../../stores/chatStore';
import { TopBar } from './TopBar';
import { CommandBar } from './CommandBar';
import { WorldStateDashboard } from '../world-state/WorldStateDashboard';
import { NarrativeScroll } from '../narrative/NarrativeScroll';
import { PanelRouter } from '../panels/PanelRouter';

export function AppShell() {
  const { focusMode, toggleFocusMode, leftPanelCollapsed, rightPanelCollapsed } = useUIStore();
  const { messages, addMessage } = useChatStore();

  // Focus mode keyboard shortcut (F key).
  //
  // The handler ignores keydown events whose target is a form
  // control — without that guard, typing the literal letter "f"
  // inside the command bar (e.g. "I follow Kael") fires the
  // shortcut and collapses both side panels mid-action. The user
  // has to hit f again to restore them, which feels like the panels
  // are randomly disappearing. The form-control guard makes the
  // shortcut only fire when the user explicitly intends it (i.e.
  // not while typing into an input/textarea/contenteditable).
  useEffect(() => {
    const handleKeyDown = (e) => {
      const target = e.target;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.key === 'f' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        toggleFocusMode();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleFocusMode]);

  // Add welcome message on mount
  useEffect(() => {
    if (messages.length === 0) {
      addMessage({
        type: 'dm',
        content: 'Welcome, traveler. The world awaits your next move.',
        author: 'Oracle',
        timestamp: new Date(),
      });
    }
  }, [addMessage, messages.length]);

  return (
    <div className="flex flex-col h-screen bg-void">
      <TopBar />

      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel */}
        {!focusMode && (
          <div className={`${leftPanelCollapsed ? 'w-12' : 'w-80'} bg-codex border-r border-border overflow-y-auto transition-all duration-200`}>
            {!leftPanelCollapsed && <WorldStateDashboard />}
          </div>
        )}

        {/* Center Panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <NarrativeScroll />
        </div>

        {/* Right Panel */}
        {!focusMode && (
          <div className={`${rightPanelCollapsed ? 'w-12' : 'w-80'} bg-codex border-l border-border overflow-y-auto transition-all duration-200`}>
            {!rightPanelCollapsed && <PanelRouter />}
          </div>
        )}
      </div>

      <CommandBar />
    </div>
  );
}

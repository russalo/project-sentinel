import { useEffect, useRef } from 'react';
import { useUIStore } from '../../stores/uiStore';
import { useChatStore } from '../../stores/chatStore';
import { usePersonaStore } from '../../stores/personaStore';
import { TopBar } from './TopBar';
import { CommandBar } from './CommandBar';
import { WorldStateDashboard } from '../world-state/WorldStateDashboard';
import { NarrativeScroll } from '../narrative/NarrativeScroll';
import { PanelRouter } from '../panels/PanelRouter';

export function AppShell() {
  const { focusMode, toggleFocusMode, leftPanelCollapsed, rightPanelCollapsed, mobilePanelOpen, openMobilePanel, closeMobilePanel, selectedEntity } = useUIStore();
  const { messages, addMessage } = useChatStore();
  const personaName = usePersonaStore((s) => s.personaName);

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

  // Lock body scroll and handle Escape key while mobile drawer is open
  useEffect(() => {
    if (mobilePanelOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobilePanelOpen]);

  useEffect(() => {
    if (!mobilePanelOpen) return;
    const handleKeyDown = (e) => { if (e.key === 'Escape') closeMobilePanel(); };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobilePanelOpen, closeMobilePanel]);

  // When an entity is selected from the left drawer, switch to the right drawer
  // so the detail view in PanelRouter is visible.
  useEffect(() => {
    if (selectedEntity && mobilePanelOpen === 'left') {
      openMobilePanel('right');
    }
  }, [selectedEntity, mobilePanelOpen, openMobilePanel]);

  // Add welcome message on mount.
  //
  // The ref latch makes this fire at most once per mount. React 19
  // StrictMode invokes effects twice in development, and the
  // addMessage state update between the two firings is not synchronous
  // — so a bare `messages.length === 0` guard lets both invocations
  // see an empty list and seed two identical welcome messages. The ref
  // is stable across the double-invocation, so the second pass
  // short-circuits. The length check is retained so we never clobber an
  // already-running conversation.
  //
  // Author comes from the live persona store (same source TopBar reads)
  // so the welcome is attributed to the selected persona instead of a
  // hardcoded "Oracle". The store defaults to "Oracle", so a
  // pre-session mount still renders a sensible author.
  const welcomeSeeded = useRef(false);
  useEffect(() => {
    if (welcomeSeeded.current) return;
    if (messages.length === 0) {
      welcomeSeeded.current = true;
      addMessage({
        type: 'dm',
        content: 'Welcome, traveler. The world awaits your next move.',
        author: personaName,
        timestamp: new Date(),
      });
    }
  }, [addMessage, messages.length, personaName]);

  return (
    <div className="flex flex-col h-screen bg-void">
      <TopBar />

      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel — desktop only */}
        {!focusMode && (
          <div className={`hidden lg:block ${leftPanelCollapsed ? 'w-12' : 'w-80'} bg-codex border-r border-border overflow-y-auto transition-all duration-200`}>
            {!leftPanelCollapsed && <WorldStateDashboard />}
          </div>
        )}

        {/* Center Panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <NarrativeScroll />
        </div>

        {/* Right Panel — desktop only */}
        {!focusMode && (
          <div className={`hidden lg:block ${rightPanelCollapsed ? 'w-12' : 'w-80'} bg-codex border-l border-border overflow-y-auto transition-all duration-200`}>
            {!rightPanelCollapsed && <PanelRouter />}
          </div>
        )}

        {/* Mobile drawer overlay */}
        {mobilePanelOpen && (
          <div className="lg:hidden fixed inset-0 z-50 flex">
            <div className="absolute inset-0 bg-black/60" onClick={closeMobilePanel} aria-hidden="true" />
            <div className={`relative z-10 w-80 max-w-[85vw] bg-codex overflow-y-auto flex-shrink-0 ${mobilePanelOpen === 'right' ? 'ml-auto border-l border-border' : 'border-r border-border'}`}>
              {mobilePanelOpen === 'left' ? <WorldStateDashboard /> : <PanelRouter />}
            </div>
          </div>
        )}
      </div>

      <CommandBar />
    </div>
  );
}

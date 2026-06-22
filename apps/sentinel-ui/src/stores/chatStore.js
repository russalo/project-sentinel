import { create } from 'zustand';
import { newId } from '../utils/id';

// Strip the DM's <world_update>...</world_update> block from a raw
// streamed response. The block is a machine-readable hint meant for
// the Fact-Extractor on the backend, not for the player. Was
// temporarily disabled during the 2026-04-14 smoke test as a
// debugging aid (so the user could see exactly what the DM was
// emitting without digging through backend logs); re-enabled
// 2026-04-15 once the dispatch path was confirmed working
// end-to-end and the visible block became distracting noise during
// real walkthroughs.
export function stripWorldUpdate(text) {
  return text.replace(/<world_update>[\s\S]*?<\/world_update>/g, '').trim();
}

export const useChatStore = create((set) => ({
  // Message history
  messages: [],
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, { id: newId(), ...message }],
  })),
  clearMessages: () => set({ messages: [], systemLog: [], unreadSystemLog: 0, activeView: 'narrative', streamBuffer: '', streamError: false }),

  // System log — one entry per turn, persists across the session
  systemLog: [],
  addSystemLogEntry: (entry) => set((state) => ({
    systemLog: [...state.systemLog, { id: newId(), ...entry }],
    // Only increment badge when the player is looking at the narrative tab
    unreadSystemLog: state.activeView === 'narrative' ? state.unreadSystemLog + 1 : state.unreadSystemLog,
  })),

  // Active view — 'narrative' | 'system-log'
  activeView: 'narrative',
  setActiveView: (view) => set((state) => ({
    activeView: view,
    unreadSystemLog: view === 'system-log' ? 0 : state.unreadSystemLog,
  })),

  // Unread badge count for system log tab
  unreadSystemLog: 0,
  clearUnreadSystemLog: () => set({ unreadSystemLog: 0 }),

  // Streaming state
  isStreaming: false,
  setIsStreaming: (streaming) => set({ isStreaming: streaming }),

  // Whether the last turn failed (network/stream error). Drives the
  // StatusIndicator; cleared at the start of the next turn.
  streamError: false,
  setStreamError: (v) => set({ streamError: v }),

  // Stream buffer (accumulates characters as they arrive)
  streamBuffer: '',
  appendToBuffer: (text) => set((state) => ({ streamBuffer: state.streamBuffer + text })),
  clearBuffer: () => set({ streamBuffer: '' }),

  // Commit current stream to messages
  commitStreamMessage: (dmName = 'DM') => set((state) => {
    // Strip the <world_update> block before showing the narrative
    // to the player. The block is internal state for the Fact-
    // Extractor, not story beat content.
    //
    // NOTE: inline <action>...</action> tags are NOT stripped here —
    // they stay in the narrative text and are parsed at render time
    // by NarrativeText (apps/sentinel-ui/src/components/narrative/).
    // Stripping them here would lose the action labels for inline
    // highlighting.
    const content = stripWorldUpdate(state.streamBuffer);
    if (content) {
      return {
        messages: [...state.messages, {
          id: newId(),
          type: 'dm',
          content,
          author: dmName,
          timestamp: new Date(),
        }],
        streamBuffer: '',
        isStreaming: false,
      };
    }
    return { streamBuffer: '', isStreaming: false };
  }),

  // Command-bar input — lifted from CommandBar's local useState so action
  // pills + inline `<action>` highlights can populate the input on click.
  // The clicker calls `setInput(label)`; CommandBar reads `input` as a
  // controlled component value. Pills NEVER auto-submit (per BACKLOG-#474):
  // the player reviews / edits before sending.
  input: '',
  setInput: (text) => set({ input: text }),

  // DM-emitted action suggestions for the current turn — populated by
  // useDMStream when the SSE `world_update` event arrives carrying a
  // `suggestedActions: [{label, tone}]` array. Cleared at the start of
  // each new turn so stale suggestions don't carry over to a different
  // narrative moment.
  suggestedActions: [],
  setSuggestedActions: (actions) => set({ suggestedActions: Array.isArray(actions) ? actions : [] }),
  clearSuggestedActions: () => set({ suggestedActions: [] }),
}));

// Dev-only handle so the screenshot tooling (scripts/src/screenshot-guide.mjs)
// can pre-populate the per-turn `suggestedActions` for the game-screen capture
// — the field is ephemeral (cleared every turn) and isn't reachable from
// outside without a live SSE turn. Tree-shaken out of production builds by
// Vite when `import.meta.env.DEV` is false.
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  window.__sentinelStores = window.__sentinelStores || {};
  window.__sentinelStores.chat = useChatStore;
}

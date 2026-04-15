import { create } from 'zustand';
import { newId } from '../utils/id';

// Strip the DM's <world_update>...</world_update> block from a raw
// streamed response. The block is a machine-readable hint meant for
// the Fact-Extractor on the backend, not for the player. Currently
// unused — during the 2026-04-14 smoke test the user asked to keep
// the block visible in the narrative as a debugging aid, since it
// makes it easy to see exactly what the DM is emitting without
// having to dig through backend logs. To re-enable clean narrative
// display later, change the `content` assignment inside
// commitStreamMessage from `state.streamBuffer` to
// `stripWorldUpdate(state.streamBuffer)` — it's a one-line flip.
// eslint-disable-next-line no-unused-vars
function stripWorldUpdate(text) {
  return text.replace(/<world_update>[\s\S]*?<\/world_update>/g, '').trim();
}

export const useChatStore = create((set) => ({
  // Message history
  messages: [],
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, { id: newId(), ...message }],
  })),
  clearMessages: () => set({ messages: [], systemLog: [], unreadSystemLog: 0 }),

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

  // Stream buffer (accumulates characters as they arrive)
  streamBuffer: '',
  appendToBuffer: (text) => set((state) => ({ streamBuffer: state.streamBuffer + text })),
  clearBuffer: () => set({ streamBuffer: '' }),

  // Commit current stream to messages
  commitStreamMessage: (dmName = 'DM') => set((state) => {
    const content = state.streamBuffer;
    if (content.trim()) {
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
}));

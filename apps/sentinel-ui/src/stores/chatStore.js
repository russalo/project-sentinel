import { create } from 'zustand';

// Strip the DM's <world_update>...</world_update> block from a raw
// streamed response. The block is a machine-readable hint meant for
// the Fact-Extractor on the backend, not for the player. Currently
// unused — during the 2026-04-14 smoke test the user asked to keep
// the block visible in the narrative as a debugging aid, since it
// makes it easy to see exactly what the DM is emitting without
// having to dig through backend logs. To re-enable clean narrative
// display later, replace `state.streamBuffer` with
// `stripWorldUpdate(state.streamBuffer)` inside commitStreamMessage.
// eslint-disable-next-line no-unused-vars
function stripWorldUpdate(text) {
  return text.replace(/<world_update>[\s\S]*?<\/world_update>/g, '').trim();
}

export const useChatStore = create((set) => ({
  // Message history
  messages: [],
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, { id: crypto.randomUUID(), ...message }],
  })),
  clearMessages: () => set({ messages: [] }),

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
          id: crypto.randomUUID(),
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

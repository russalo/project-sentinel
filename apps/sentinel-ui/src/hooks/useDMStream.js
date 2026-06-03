import { useCallback } from 'react';
import { API_BASE } from '../api/client';
import { useChatStore } from '../stores/chatStore';
import { useWorldStore } from '../stores/worldStore';
import { usePlayerStore } from '../stores/playerStore';
import { computeDelta, hasDelta } from '../utils/delta';

export function useDMStream() {
  const { appendToBuffer, commitStreamMessage, setIsStreaming, setStreamError, addMessage, addSystemLogEntry } = useChatStore();
  const applyUpdate = useWorldStore((s) => s.applyUpdate);

  const sendAction = useCallback(
    async (action, sessionId) => {
      setIsStreaming(true);
      setStreamError(false); // clear any prior turn's error
      let buffer = '';
      const pendingDeltas = [];
      // worldId is advisory for the backend (it routes by session_id), but the
      // ADR 0002 Slice 4 contract carries it on the turn. Read at call time.
      const worldId = usePlayerStore.getState().worldId;

      try {
        const response = await fetch(`${API_BASE}/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, sessionId, worldId }),
        });

        if (!response.ok) {
          throw new Error(`Stream request failed: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let receivedDone = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep incomplete last line

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') {
              commitStreamMessage();
              for (const pd of pendingDeltas) {
                addMessage({ type: 'delta', delta: pd.delta, timestamp: pd.timestamp });
              }
              receivedDone = true;
              break;
            }
            let event;
            try {
              event = JSON.parse(raw);
            } catch {
              continue;
            }
            if (event.type === 'token') appendToBuffer(event.content);
            if (event.type === 'world_update') {
              const before = useWorldStore.getState();
              applyUpdate(event.data);
              const after = useWorldStore.getState();
              const delta = computeDelta(before, after);
              if (hasDelta(delta)) {
                const ts = new Date();
                addSystemLogEntry({ delta, timestamp: ts });
                pendingDeltas.push({ delta, timestamp: ts });
              }
            }
            if (event.type === 'system') addMessage({ type: 'system', content: event.content, timestamp: new Date() });
            if (event.type === 'error') addMessage({ type: 'system', content: `[Error: ${event.content}]`, timestamp: new Date() });
          }
          if (receivedDone) break;
        }
        // Stream ended without [DONE] — commit what we have, then flush deltas
        if (!receivedDone) {
          commitStreamMessage();
          for (const pd of pendingDeltas) {
            addMessage({ type: 'delta', delta: pd.delta, timestamp: pd.timestamp });
          }
        }
      } catch (err) {
        commitStreamMessage(); // finalize any partial buffer before showing error
        setStreamError(true); // surface on the StatusIndicator
        addMessage({ type: 'system', content: `[Connection error: ${err.message}]`, timestamp: new Date() });
      } finally {
        setIsStreaming(false);
      }
    },
    [appendToBuffer, commitStreamMessage, setIsStreaming, setStreamError, addMessage, addSystemLogEntry, applyUpdate],
  );

  return { sendAction };
}

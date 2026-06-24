import { useCallback } from 'react';
import { API_BASE } from '../api/client';
import { worldTokenHeader } from '../api/worldToken';
import { useChatStore } from '../stores/chatStore';
import { useWorldStore } from '../stores/worldStore';
import { usePlayerStore } from '../stores/playerStore';
import { computeDelta, hasDelta } from '../utils/delta';

export function useDMStream() {
  const { appendToBuffer, commitStreamMessage, setIsStreaming, setStreamError, addMessage, addSystemLogEntry, setSuggestedActions, clearSuggestedActions, setCheckRequest, clearCheckRequest, setLevelUp, clearLevelUp } = useChatStore();
  const applyUpdate = useWorldStore((s) => s.applyUpdate);

  // Core turn runner. `roll` is the d100 wire payload on a resolve turn
  // (ADR-0005 resolution module), null on an ordinary turn. `levelUp` is
  // the level-up choice wire payload on an enact turn (ADR-0005 progression
  // module / RFC-0009), null otherwise.
  const runTurn = useCallback(
    async (action, sessionId, roll = null, levelUp = null) => {
      setIsStreaming(true);
      setStreamError(false); // clear any prior turn's error
      // Drop the previous turn's DM-emitted affordances the moment a new
      // turn starts — stale action pills / a stale check request / a stale
      // level-up proposal from N-1 turns ago shouldn't sit next to the new
      // turn's narrative. Always-available pills (rule-based, frontend-only)
      // are unaffected.
      clearSuggestedActions();
      clearCheckRequest();
      clearLevelUp();
      let buffer = '';
      const pendingDeltas = [];
      // worldId is advisory for the backend (it routes by session_id), but the
      // ADR 0002 Slice 4 contract carries it on the turn. Read at call time.
      const worldId = usePlayerStore.getState().worldId;

      try {
        const response = await fetch(`${API_BASE}/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            // Per-world token (ADR 0003); empty header object when none is held.
            ...worldTokenHeader(worldId),
          },
          // `roll` only present on a resolve turn; `levelUp` only on an
          // enact turn. The backend models ignore each when absent.
          body: JSON.stringify({ action, sessionId, worldId, ...(roll ? { roll } : {}), ...(levelUp ? { levelUp } : {}) }),
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
              // Surface this turn's DM-emitted action pills. The DM-side
              // contract (see engine/prompts/dm.py) is `suggestedActions:
              // [{label, tone}]` byte-identical to the inline `<action>` tags
              // in the narrative, so click on either surface types the same
              // string into the input. Missing/non-array field → cleared
              // (graceful fallback to always-available rail).
              setSuggestedActions(event.data?.suggestedActions);
              // Surface a DM-requested d100 check (ADR-0005 resolution
              // module): the DM emits `check_request: {stat,target,label,
              // prompt}` in the same world_update hint when it wants the
              // player to roll instead of resolving. Missing → cleared.
              setCheckRequest(event.data?.check_request);
              // Surface a DM-proposed level-up (ADR-0005 progression
              // module / RFC-0009): the DM emits `level_up: {to_level}` in
              // the same world_update hint when the player has earned an
              // advance, then STOPS. Missing → cleared.
              setLevelUp(event.data?.level_up);
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
    [appendToBuffer, commitStreamMessage, setIsStreaming, setStreamError, addMessage, addSystemLogEntry, applyUpdate, setSuggestedActions, clearSuggestedActions, setCheckRequest, clearCheckRequest, setLevelUp, clearLevelUp],
  );

  // Ordinary turn: the player's typed/clicked action, no roll.
  const sendAction = useCallback(
    (action, sessionId) => runTurn(action, sessionId, null),
    [runTurn],
  );

  // Resolve turn: the player rolled a DM-requested check. `wirePayload` is
  // the d100 RollResult (from roll.js toWirePayload); `label` re-states what
  // is being resolved so the DM has context alongside the roll.
  const sendRoll = useCallback(
    (wirePayload, label, sessionId) => runTurn(label || 'resolve the check', sessionId, wirePayload),
    [runTurn],
  );

  // Enact turn: the player took a DM-proposed level-up and chose a stat
  // (ADR-0005 progression module / RFC-0009). `stat` is the lowercase
  // attribute (body/mind/heart/will); `toLevel` is the target level. The
  // backend LevelUpChoice model reads camelCase (toLevel); the DM applies
  // exactly this — the PC-ownership wall.
  const sendLevelUp = useCallback(
    (stat, toLevel, sessionId) =>
      runTurn(
        `I advance to level ${toLevel}, raising ${stat}.`,
        sessionId,
        null,
        { stat, toLevel },
      ),
    [runTurn],
  );

  return { sendAction, sendRoll, sendLevelUp };
}

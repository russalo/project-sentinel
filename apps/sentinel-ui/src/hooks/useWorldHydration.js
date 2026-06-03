import { useEffect } from 'react';
import { apiClient } from '../api/client';
import { usePlayerStore } from '../stores/playerStore';
import { useChatStore, stripWorldUpdate } from '../stores/chatStore';

// Hydrate the game from a world's URL (ADR 0002 Slice 4).
//
// When the player opens /w/<worldId> — a shared link, a bookmark, or just a
// page refresh — nothing is in the in-memory stores, so we fetch the world's
// current session from GET /api/world/<worldId> and rebuild the narrative
// scroll from its turn log. Coming straight from WorldCreation we skip this:
// that flow already set the stores and seeded the chat, and playerStore.worldId
// will already equal the route's worldId.
export function useWorldHydration(worldId) {
  useEffect(() => {
    if (!worldId) return;
    // Already loaded (navigated here from WorldCreation) → don't re-fetch or
    // double-seed the scroll.
    if (usePlayerStore.getState().worldId === worldId) return;

    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.get(`/world/${worldId}`);
        if (cancelled) return;

        const player = usePlayerStore.getState();
        player.setSessionId(data.sessionId);
        player.setWorldId(worldId);
        player.setWorldName(data.worldName || 'Unnamed World');
        player.setCharacter(data.character || '', player.characterClass || '');

        // Rebuild the scroll from the turn log, mirroring how live play renders
        // (CommandBar adds a 'player' message, the DM narrative a 'dm' message).
        // The turn-0 player_action is the synthetic "[Session Start] …" line —
        // it isn't shown live, so skip it here too.
        const chat = useChatStore.getState();
        chat.clearMessages();
        for (const turn of data.turns || []) {
          const action = turn.player_action;
          if (action && !action.startsWith('[Session Start]')) {
            chat.addMessage({ type: 'player', content: action, timestamp: new Date() });
          }
          const narrative = stripWorldUpdate(turn.narrative ?? '');
          if (narrative) {
            chat.addMessage({ type: 'dm', content: narrative, author: 'DM', timestamp: new Date() });
          }
        }
      } catch (err) {
        if (cancelled) return;
        useChatStore.getState().addMessage({
          type: 'system',
          content: `[Could not load world: ${err.message}]`,
          timestamp: new Date(),
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [worldId]);
}

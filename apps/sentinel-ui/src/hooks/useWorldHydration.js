import { useEffect } from 'react';
import { apiClient } from '../api/client';
import { usePlayerStore } from '../stores/playerStore';
import { usePersonaStore } from '../stores/personaStore';
import { useWorldStore } from '../stores/worldStore';
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

    // Commit to (re)hydrating. Clear the previous world's scroll AND world
    // state *now*, before the await, so neither lingers across a world switch
    // or a failed load. Resetting worldStore is essential: applyUpdate upserts,
    // so without it the new world's first world_update would merge into the old
    // world's entities (cross-world bleed in the panels). Flag `hydrating` so
    // the welcome-seed effect stays quiet during the fetch.
    useChatStore.getState().clearMessages();
    useWorldStore.getState().reset();
    usePlayerStore.getState().setHydrating(true);

    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.get(`/world/${worldId}`);
        if (cancelled) return;
        if (!data || typeof data !== 'object') {
          throw new Error('empty world response');
        }

        const player = usePlayerStore.getState();
        player.setSessionId(data.sessionId);
        player.setWorldId(worldId);
        player.setWorldName(data.worldName || 'Unnamed World');
        player.setCharacter(data.character || '', data.characterClass || '');
        // Restore the persona display name (TopBar / welcome / author) — the
        // create path syncs personaStore for the same reason; otherwise it
        // reverts to the hardcoded 'Oracle' default on resume. The persona's
        // id + mood list aren't persisted on the session record yet (tracked),
        // so only the display name is restored here.
        if (data.persona) usePersonaStore.getState().setPersona(null, data.persona);

        // Rebuild the scroll from the turn log, mirroring live play (CommandBar
        // adds a 'player' message, the DM narrative a 'dm' message). Turn 0's
        // player_action is the synthetic "[Session Start] …" line — not shown
        // live — so skip it; a later turn that happens to start that way is
        // a real player message and is kept.
        const chat = useChatStore.getState();
        chat.clearMessages();
        for (const turn of data.turns || []) {
          if (!turn || typeof turn !== 'object') continue;
          const action = turn.player_action;
          const isSyntheticStart =
            turn.turn_number === 0 && action && action.startsWith('[Session Start]');
          if (action && !isSyntheticStart) {
            chat.addMessage({ type: 'player', content: action, timestamp: new Date() });
          }
          const narrative = stripWorldUpdate(turn.narrative ?? '');
          if (narrative) {
            chat.addMessage({ type: 'dm', content: narrative, author: 'DM', timestamp: new Date() });
          }
        }
      } catch (err) {
        if (cancelled) return;
        // The scroll was already cleared above, so the player sees only this
        // error — never the previous world's chat.
        useChatStore.getState().addMessage({
          type: 'system',
          content: `[Could not load world: ${err.message}]`,
          timestamp: new Date(),
        });
      } finally {
        if (!cancelled) usePlayerStore.getState().setHydrating(false);
      }
    })();

    return () => {
      cancelled = true;
      usePlayerStore.getState().setHydrating(false);
    };
  }, [worldId]);
}

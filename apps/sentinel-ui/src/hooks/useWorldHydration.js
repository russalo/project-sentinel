import { useEffect } from 'react';
import { apiClient } from '../api/client';
import { reauth, worldTokenHeader } from '../api/worldToken';
import { usePlayerStore } from '../stores/playerStore';
import { usePersonaStore } from '../stores/personaStore';
import { useWorldStore } from '../stores/worldStore';
import { useChatStore, stripWorldUpdate } from '../stores/chatStore';

// Fetch the world payload, recovering from a 401 (missing token) OR 403
// (expired / invalid token) by calling /reauth once and retrying with the
// fresh token. Factored out so the hydration body below stays readable —
// the actual recovery logic lives here:
//
//   1. Try GET /world/{id} with whatever token we have.
//   2. On 401 (no token in localStorage) OR 403 (token present but expired
//      / wrong secret / wrong-shape), call reauth(worldId). reauth carries
//      the browser's already-cached basic_auth header; the backend confirms
//      the user is the world's creator and re-mints a fresh token.
//   3. Retry GET /world/{id} with the fresh token.
//   4. If reauth itself fails: 403 from reauth means basic_auth user isn't
//      this world's creator — surface a clear "Not your world." Other
//      reauth failures (401 = no basic_auth reached the backend; 502 =
//      network or response-shape failure) bubble as-is so the user-facing
//      error reflects the actual cause, not the original GET status.
//
// Why 401 + 403, not just 401: the per-world HMAC tokens have a 7-day TTL
// by default. A returning tester whose token expired (or whose secret has
// rotated, or whose token wire-shape became invalid via a backend upgrade)
// gets 403 from `enforce_world_token`. Without 403-trigger reauth, that
// tester is stranded with a "Could not load world: API error: 403" message
// instead of auto-recovering via basic_auth re-mint. Russell reported this
// 2026-06-14 after his 6.9-day-old token aged out.
const REAUTH_TRIGGER_STATUSES = new Set([401, 403]);

async function fetchWorldWithReauth(worldId) {
  try {
    return await apiClient.get(`/world/${worldId}`, {
      headers: worldTokenHeader(worldId),
    });
  } catch (err) {
    if (!REAUTH_TRIGGER_STATUSES.has(err?.status)) throw err;
    // Stale, missing, or expired token. Try the recovery dance — at most
    // once, so a genuinely-broken auth path doesn't loop forever.
    try {
      await reauth(worldId);
    } catch (reauthErr) {
      // reauth failed — bubble the error that actually surfaced. 403 from
      // reauth specifically means the basic_auth user isn't this world's
      // creator (a genuine ownership mismatch, not recoverable) — translate
      // to a clear "Not your world." All other reauth errors (401 = no
      // basic_auth header reached the backend; 502 = network / response
      // shape failure; etc.) bubble as-is so the user-facing error message
      // reflects the actual cause, not the original GET status that
      // triggered the recovery attempt. (gemini-medium on PR #138.)
      if (reauthErr?.status === 403) {
        const e = new Error('Not your world');
        e.status = 403;
        throw e;
      }
      throw reauthErr;
    }
    return await apiClient.get(`/world/${worldId}`, {
      headers: worldTokenHeader(worldId),
    });
  }
}

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
        const data = await fetchWorldWithReauth(worldId);
        if (cancelled) return;
        if (!data || typeof data !== 'object') {
          throw new Error('empty world response');
        }

        const player = usePlayerStore.getState();
        player.setSessionId(data.sessionId);
        player.setWorldId(worldId);
        player.setWorldName(data.worldName || 'Unnamed World');
        player.setCharacter(data.character || '', data.characterClass || '');
        // Restore the persona (TopBar / welcome / author / current mood) — the
        // create path syncs personaStore for the same reason, else it reverts
        // to the hardcoded 'Oracle'/'neutral' defaults on resume. The persona's
        // available-mood *list* isn't persisted (preset metadata) so the mood
        // dropdown options stay at the store default — tracked follow-up; the
        // id, display name, and selected mood are restored.
        if (data.persona || data.personaId) {
          usePersonaStore.getState().setPersona(data.personaId || null, data.persona || data.personaId);
        }
        if (data.mood) usePersonaStore.getState().setMood(data.mood);

        // Rehydrate the world-state panels (entities/locations/factions/items +
        // metadata) so a reopened world looks as it was left, not just the
        // narrative. The store was reset() above, so this is a clean load.
        useWorldStore.getState().hydrate(data.worldState);

        // Rebuild the scroll from the turn log, mirroring live play (CommandBar
        // adds a 'player' message, the DM narrative a 'dm' message). Turn 0's
        // player_action is the synthetic "[Session Start] …" line — not shown
        // live — so skip it; a later turn that happens to start that way is
        // a real player message and is kept.
        const chat = useChatStore.getState();
        chat.clearMessages();
        chat.clearSuggestedActions();
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
        // Seed the pill rail with the latest turn's DM-emitted suggestions so
        // resume mirrors live play. Turns are ordered oldest-first; the last
        // turn's world_updates carries the suggestions still relevant.
        //
        // Filter null / non-object turn elements BEFORE picking the last one
        // (gemini medium on PR #112) — a stray null or malformed element at the
        // tail would otherwise either crash on the `?.world_updates` access
        // (`?.` saves us here but is fragile) or hide valid suggestions just
        // before it.
        const validTurns = (data.turns || []).filter(
          (t) => t && typeof t === 'object',
        );
        const lastWorldUpdate =
          validTurns.length > 0 ? validTurns[validTurns.length - 1].world_updates : null;
        if (lastWorldUpdate && Array.isArray(lastWorldUpdate.suggestedActions)) {
          chat.setSuggestedActions(lastWorldUpdate.suggestedActions);
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

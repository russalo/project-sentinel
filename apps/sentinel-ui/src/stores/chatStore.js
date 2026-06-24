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
  clearMessages: () => set({ messages: [], systemLog: [], unreadSystemLog: 0, activeView: 'narrative', streamBuffer: '', streamError: false, rollResult: null }),

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

  // DM-requested d100 check for the current turn (ADR-0005 resolution
  // module / RFC-0006). Populated by useDMStream when the `world_update`
  // event carries `check_request: {stat, target, label, prompt}` — the
  // DM is asking the player to roll instead of resolving the action. The
  // CheckRequestRail renders the Roll affordance; on roll, useDMStream
  // resends the turn carrying the result. Cleared at the start of each
  // turn (parallel to suggestedActions) so a stale request can't linger.
  checkRequest: null,
  // Validate a DM-emitted check_request before surfacing it. A malformed
  // request (non-recognized stat, non-integer target) would produce a NaN
  // margin / broken roll, so reject it outright — better the DM resolves
  // narratively than the player faces an un-rollable check. (gemini-high
  // on PR #146; the malformed-LLM-output hunt pattern.)
  setCheckRequest: (req) => {
    const VALID_STATS = ['body', 'mind', 'heart', 'will'];
    if (
      !req ||
      typeof req !== 'object' ||
      !VALID_STATS.includes(req.stat) ||
      !Number.isInteger(req.target) ||
      req.target <= 0
    ) {
      set({ checkRequest: null });
      return;
    }
    // Coerce the optional display strings; never trust their type.
    // `effect_die` (RFC-0007 combat) rides along on an attack: a "1dN"
    // spec the frontend rolls alongside the d100. Pass it only when it's
    // a string; otherwise the check is a non-combat check.
    set({
      checkRequest: {
        stat: req.stat,
        target: req.target,
        label: typeof req.label === 'string' ? req.label : '',
        prompt: typeof req.prompt === 'string' ? req.prompt : '',
        effectDie: typeof req.effect_die === 'string' ? req.effect_die : null,
      },
    });
  },
  clearCheckRequest: () => set({ checkRequest: null, rollResult: null }),

  // The d100 result the player has rolled for the current check but not yet
  // resolved — the object from utils/roll.js computeRoll(), or null (ADR-0005
  // resolution module / RFC-0006). The roll reveal is PLAYER-PACED (PR #151);
  // this lives in the store (not CheckRequestRail's local state) so a revealed
  // roll SURVIVES the rail unmounting — e.g. the player navigating to /guide
  // or /feedback before tapping Resolve — and is restored on return rather
  // than forcing a re-roll (PR #152 follow-up).
  //
  // It is ALSO the single source of truth for "a roll is pending resolution"
  // (`rollResult !== null`): set on Roll (CheckRequestRail.handleRoll), it
  // locks the command bar (CommandBar) so a revealed roll can't be silently
  // discarded by typing a different action, and drives a distinct "resolve to
  // continue" StatusIndicator state — a genuinely different state from
  // `isStreaming` (the DM isn't working yet; we're waiting on the player), so
  // it does NOT overload isStreaming (which would falsely read "Streaming…").
  // Cleared by clearCheckRequest — which runTurn calls at the top of every
  // turn — so resolving (or starting any new turn) lifts the lock + the reveal.
  rollResult: null,
  setRollResult: (r) => set({ rollResult: r }),

  // DM-proposed level-up for the current turn (ADR-0005 progression module
  // / RFC-0009). Populated by useDMStream when the `world_update` event
  // carries `level_up: {to_level}` — the DM is signalling the player has
  // earned an advance and STOPS (the PC-ownership wall: the DM never picks
  // the stat or writes the level itself). The LevelUpCard renders the
  // stat-choice affordance; on confirm, useDMStream resends the turn
  // carrying the choice. Cleared at the start of each turn (parallel to
  // checkRequest) so a stale proposal can't linger.
  levelUp: null,
  // Validate a DM-emitted level_up before surfacing it. A malformed signal
  // (non-integer / non-positive to_level) would produce a broken card, so
  // reject it outright — better the DM keeps narrating than the player
  // faces an un-actionable advance. (Mirrors setCheckRequest; the
  // malformed-LLM-output hunt pattern.)
  // The progression module is v0.1 levels 1..5; a malformed proposal above
  // the cap (e.g. {to_level: 6}) must be rejected, not surfaced — otherwise
  // LevelUpCard would let the player confirm an impossible advancement
  // (codex P2, PR #150). Mirrors the backend LevelUpChoice bound.
  setLevelUp: (req) => {
    if (
      !req ||
      typeof req !== 'object' ||
      !Number.isInteger(req.to_level) ||
      req.to_level < 1 ||
      req.to_level > 5
    ) {
      set({ levelUp: null });
      return;
    }
    set({ levelUp: { toLevel: req.to_level } });
  },
  clearLevelUp: () => set({ levelUp: null }),
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

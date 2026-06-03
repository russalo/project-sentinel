import { create } from 'zustand';

export const usePlayerStore = create((set) => ({
  // Session
  sessionId: null,
  setSessionId: (id) => set({ sessionId: id }),

  // World identity (ADR 0002 Slice 4). Drives the /w/<worldId> URL and lets the
  // hydration hook distinguish "already loaded this world" from "fresh load →
  // fetch it". Set at creation and on hydration from a /w/<id> link or refresh.
  worldId: null,
  setWorldId: (id) => set({ worldId: id }),

  // True while useWorldHydration is fetching a world (ADR 0002 Slice 4). The
  // welcome-seed effect checks it so the placeholder doesn't flash into a
  // scroll that's about to be replaced by the resumed turn log.
  hydrating: false,
  setHydrating: (v) => set({ hydrating: v }),

  // World identity — set at session creation and read by the TopBar.
  // (worldCreationStore is reset on submit, so the active world's name
  // is persisted here instead.)
  worldName: '',
  setWorldName: (name) => set({ worldName: name }),

  // Character identity
  characterName: '',
  characterClass: '',
  setCharacter: (name, charClass) =>
    set({ characterName: name, characterClass: charClass }),
}));

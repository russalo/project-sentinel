import { create } from 'zustand';

export const usePlayerStore = create((set) => ({
  // Session
  sessionId: null,
  setSessionId: (id) => set({ sessionId: id }),

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

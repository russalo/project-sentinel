import { create } from 'zustand';

export const usePersonaStore = create((set) => ({
  // Persona type
  personaId: null,
  personaName: 'Oracle',
  // The mood list that belongs to the active persona. Populated at
  // session-create time from the preset metadata so the PersonaSheet
  // only offers moods compatible with the chosen persona instead of
  // a fixed Oracle list.
  availableMoods: ['neutral', 'ominous', 'lore-heavy'],
  setPersona: (id, name, moods) => set({
    personaId: id,
    personaName: name,
    ...(Array.isArray(moods) && moods.length > 0 ? { availableMoods: moods } : {}),
  }),

  // Mood (always changeable within the active persona's list)
  mood: 'neutral',
  setMood: (mood) => set({ mood }),

  // Lock state (persona type cannot change when locked, unless unlocked by event)
  isLocked: true,
  isSandbox: false,
  unlock: () => set({ isLocked: false }),
  lock: () => set({ isLocked: true }),
  setSandbox: (sandbox) => set({ isSandbox: sandbox }),
}));

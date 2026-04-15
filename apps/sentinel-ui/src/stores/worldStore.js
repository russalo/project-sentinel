import { create } from 'zustand';

export const useWorldStore = create((set) => ({
  // World metadata
  worldName: '',
  genre: '',
  tone: '',
  currentLocation: '',
  timeOfDay: '',
  weather: '',
  setWorldMetadata: (metadata) => set(metadata),

  // Locations
  locations: [],
  addLocation: (location) => set((state) => ({ locations: [...state.locations, location] })),
  updateLocation: (id, updates) => set((state) => ({
    locations: state.locations.map(l => l.id === id ? { ...l, ...updates } : l),
  })),

  // Characters/NPCs
  characters: [],
  addCharacter: (character) => set((state) => ({ characters: [...state.characters, character] })),
  updateCharacter: (id, updates) => set((state) => ({
    characters: state.characters.map(c => c.id === id ? { ...c, ...updates } : c),
  })),

  // Factions
  factions: [],
  addFaction: (faction) => set((state) => ({ factions: [...state.factions, faction] })),
  updateFaction: (id, updates) => set((state) => ({
    factions: state.factions.map(f => f.id === id ? { ...f, ...updates } : f),
  })),

  // Items
  items: [],
  addItem: (item) => set((state) => ({ items: [...state.items, item] })),
  updateItem: (id, updates) => set((state) => ({
    items: state.items.map(i => i.id === id ? { ...i, ...updates } : i),
  })),

  // World metrics
  day: 1,
  tension: 'calm', // calm, moderate, high, critical
  setDay: (day) => set({ day }),
  setTension: (tension) => set({ tension }),

  // Apply a WorldUpdate from the SSE stream (name-based upsert/remove)
  applyUpdate: (worldUpdate) => set((state) => {
    const next = { ...state };

    if (worldUpdate.world) {
      const w = worldUpdate.world;
      if (w.currentLocation !== undefined) next.currentLocation = w.currentLocation;
      if (w.timeOfDay !== undefined) next.timeOfDay = w.timeOfDay;
      if (w.weather !== undefined) next.weather = w.weather;
      if (w.tension !== undefined) {
        // Keep numeric tension in state for display; map to label if needed elsewhere
        next.tension = w.tension;
      }
    }

    if (worldUpdate.characters?.length) {
      let chars = [...state.characters];
      for (const char of worldUpdate.characters) {
        if (char.action === 'remove') {
          chars = chars.filter(c => c.name !== char.name);
        } else {
          const idx = chars.findIndex(c => c.name === char.name);
          if (idx >= 0) {
            chars = chars.map((c, i) => i === idx ? { ...c, ...char } : c);
          } else {
            chars = [...chars, char];
          }
        }
      }
      next.characters = chars;
    }

    if (worldUpdate.locations?.length) {
      let locs = [...state.locations];
      for (const loc of worldUpdate.locations) {
        if (loc.action === 'remove') {
          locs = locs.filter(l => l.name !== loc.name);
        } else {
          const idx = locs.findIndex(l => l.name === loc.name);
          if (idx >= 0) {
            locs = locs.map((l, i) => i === idx ? { ...l, ...loc } : l);
          } else {
            locs = [...locs, loc];
          }
        }
      }
      next.locations = locs;
    }

    if (worldUpdate.factions?.length) {
      let facs = [...state.factions];
      for (const fac of worldUpdate.factions) {
        if (fac.action === 'remove') {
          facs = facs.filter(f => f.name !== fac.name);
        } else {
          const idx = facs.findIndex(f => f.name === fac.name);
          if (idx >= 0) {
            facs = facs.map((f, i) => i === idx ? { ...f, ...fac } : f);
          } else {
            facs = [...facs, fac];
          }
        }
      }
      next.factions = facs;
    }

    if (worldUpdate.items?.length) {
      let its = [...state.items];
      for (const item of worldUpdate.items) {
        if (item.action === 'remove') {
          its = its.filter(i => i.name !== item.name);
        } else {
          const idx = its.findIndex(i => i.name === item.name);
          if (idx >= 0) {
            its = its.map((i, n) => n === idx ? { ...i, ...item } : i);
          } else {
            its = [...its, item];
          }
        }
      }
      next.items = its;
    }

    return next;
  }),

  // Bulk hydration from API
  hydrate: (worldState) => set({
    worldName: worldState.name || '',
    genre: worldState.genre || '',
    tone: worldState.tone || '',
    currentLocation: worldState.currentLocation || '',
    timeOfDay: worldState.timeOfDay || '',
    weather: worldState.weather || '',
    locations: worldState.locations || [],
    characters: worldState.characters || [],
    factions: worldState.factions || [],
    items: worldState.items || [],
    day: worldState.day || 1,
    tension: worldState.tension || 'calm',
  }),
}));

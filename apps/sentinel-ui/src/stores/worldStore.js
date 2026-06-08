import { create } from 'zustand';

// worldStore's tension contract is the raw 0-10 integer the backend emits
// (via load_world_context and via every DM world_update). WorldMetrics derives
// the colour band + categorical label from the int at render time — see
// components/world-state/WorldMetrics.jsx. Keeping the int in the store means
// the meter can render its bar width directly, the delta layer compares
// raw ints (utils/delta.js), and a future surface (e.g. a tension-history
// chart) can read the actual value instead of an already-banded label.

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
  tension: 0, // 0-10 int; encounter-pressure value the DM emits each turn
  setDay: (day) => set({ day }),
  setTension: (tension) => set({ tension }),

  // Reset to the empty baseline (ADR 0002 Slice 4). Called when hydrating a
  // different world so the previous world's entities don't linger in the
  // panels — without this, the next world_update would upsert into the old
  // world's arrays (cross-world bleed). Mirrors the initial state above.
  reset: () => set({
    worldName: '',
    genre: '',
    tone: '',
    currentLocation: '',
    timeOfDay: '',
    weather: '',
    locations: [],
    characters: [],
    factions: [],
    items: [],
    day: 1,
    tension: 0,
  }),

  // Replace the store with a world's persisted state on /w/<id> resume (ADR
  // 0002 Slice 5). The backend (GET /api/world/<id> → worldState) returns the
  // canonical entity dicts, which are flat {name, …} objects keyed by name —
  // the same shape applyUpdate maintains — so they load directly. Missing
  // fields fall back to the current value, and arrays default to [].
  hydrate: (worldState) => set((state) => {
    if (!worldState || typeof worldState !== 'object') return {};
    // Fall back to the current value when a field is absent — the endpoint
    // always sends all four arrays (load_world_context returns [] for empty),
    // so a missing one means a malformed/partial payload; preserve rather than
    // wipe. (In the normal flow hydrate runs right after reset(), so current
    // is already [].)
    const arr = (v, fallback) => (Array.isArray(v) ? v : fallback);
    return {
      // worldName is session-owned (playerStore) — don't mirror it here, where
      // ctx.world_name can be the 'Unknown Realm' placeholder before any
      // world/state.json exists, creating a split-brain with the real name.
      currentLocation: worldState.currentLocation ?? state.currentLocation,
      timeOfDay: worldState.timeOfDay ?? state.timeOfDay,
      weather: worldState.weather ?? state.weather,
      // Number.isFinite (not typeof) so NaN doesn't propagate into the store
      // (gemini-medium on PR #124).
      tension: Number.isFinite(worldState.tension) ? worldState.tension : state.tension,
      characters: arr(worldState.characters, state.characters),
      locations: arr(worldState.locations, state.locations),
      factions: arr(worldState.factions, state.factions),
      items: arr(worldState.items, state.items),
    };
  }),

  // Apply a WorldUpdate from the SSE stream (name-based upsert/remove)
  applyUpdate: (worldUpdate) => set((state) => {
    const next = { ...state };

    if (worldUpdate.world) {
      const w = worldUpdate.world;
      if (w.currentLocation !== undefined) next.currentLocation = w.currentLocation;
      if (w.timeOfDay !== undefined) next.timeOfDay = w.timeOfDay;
      if (w.weather !== undefined) next.weather = w.weather;
      // Number.isFinite (not typeof) so NaN doesn't survive the upsert
      // (gemini-medium on PR #124).
      if (Number.isFinite(w.tension)) next.tension = w.tension;
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
        // Match on unique_id when present, fall back to name for payloads without it
        const match = (i) => item.unique_id
          ? i.unique_id === item.unique_id
          : i.name === item.name;
        if (item.action === 'remove') {
          its = its.filter(i => !match(i));
        } else {
          const idx = its.findIndex(match);
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
}));

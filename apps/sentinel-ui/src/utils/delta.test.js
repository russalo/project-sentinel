import { describe, it, expect } from 'vitest';
import { computeDelta, hasDelta } from './delta';

// ── fixtures ─────────────────────────────────────────────────────────

const emptyWorld = {
  currentLocation: null,
  timeOfDay: null,
  weather: null,
  tension: null,
  characters: [],
  locations: [],
  factions: [],
  items: [],
};

function w(overrides = {}) {
  return { ...emptyWorld, ...overrides };
}

// ── computeDelta: no-op cases ────────────────────────────────────────

describe('computeDelta — empty / no-change cases', () => {
  it('returns empty arrays when before and after are identical empty worlds', () => {
    const delta = computeDelta(emptyWorld, emptyWorld);
    expect(delta.world).toEqual([]);
    expect(delta.characters).toEqual([]);
    expect(delta.locations).toEqual([]);
    expect(delta.factions).toEqual([]);
    expect(delta.items).toEqual([]);
  });

  it('returns empty world delta when fields are unchanged', () => {
    const before = w({ currentLocation: 'Tavern', timeOfDay: 'dusk', weather: 'clear', tension: 3 });
    const after  = w({ currentLocation: 'Tavern', timeOfDay: 'dusk', weather: 'clear', tension: 3 });
    expect(computeDelta(before, after).world).toEqual([]);
  });

  it('hasDelta returns false for an empty delta', () => {
    expect(hasDelta(computeDelta(emptyWorld, emptyWorld))).toBe(false);
  });

  it('hasDelta returns true when any collection has entries', () => {
    const after = w({ characters: [{ name: 'Thalia', role: 'ranger' }] });
    expect(hasDelta(computeDelta(emptyWorld, after))).toBe(true);
  });
});

// ── computeDelta: world-field changes ────────────────────────────────

describe('computeDelta — world fields', () => {
  it('detects a currentLocation change', () => {
    const before = w({ currentLocation: 'Tavern' });
    const after  = w({ currentLocation: 'Forest' });
    const delta = computeDelta(before, after);
    expect(delta.world).toEqual([{ field: 'currentLocation', from: 'Tavern', to: 'Forest' }]);
  });

  it('detects a tension change', () => {
    const before = w({ tension: 3 });
    const after  = w({ tension: 7 });
    const delta = computeDelta(before, after);
    expect(delta.world).toEqual([{ field: 'tension', from: 3, to: 7 }]);
  });

  it('detects multiple world-field changes at once', () => {
    const before = w({ timeOfDay: 'day',  weather: 'clear' });
    const after  = w({ timeOfDay: 'night', weather: 'storm' });
    const delta = computeDelta(before, after);
    const fields = delta.world.map(c => c.field).sort();
    expect(fields).toEqual(['timeOfDay', 'weather']);
  });
});

// ── computeDelta: character add/remove/change ────────────────────────

describe('computeDelta — characters', () => {
  it('detects an added character', () => {
    const before = w();
    const after  = w({ characters: [{ name: 'Thalia', role: 'ranger' }] });
    const delta = computeDelta(before, after);
    expect(delta.characters).toHaveLength(1);
    expect(delta.characters[0].action).toBe('added');
    expect(delta.characters[0].name).toBe('Thalia');
    expect(delta.characters[0].entity).toEqual({ name: 'Thalia', role: 'ranger' });
  });

  it('detects a removed character', () => {
    const before = w({ characters: [{ name: 'Thalia', role: 'ranger' }] });
    const after  = w();
    const delta = computeDelta(before, after);
    expect(delta.characters).toEqual([{ action: 'removed', name: 'Thalia' }]);
  });

  it('detects tracked field changes on a character', () => {
    const before = w({ characters: [{ name: 'Thalia', health: 100, status: 'healthy' }] });
    const after  = w({ characters: [{ name: 'Thalia', health: 60,  status: 'wounded' }] });
    const delta = computeDelta(before, after);
    expect(delta.characters).toHaveLength(1);
    expect(delta.characters[0].action).toBe('changed');
    expect(delta.characters[0].name).toBe('Thalia');
    const fields = delta.characters[0].changes.map(c => c.field).sort();
    expect(fields).toEqual(['health', 'status']);
  });

  it('ignores untracked fields on a character', () => {
    // `description` is not in TRACKED_FIELDS.character
    const before = w({ characters: [{ name: 'Thalia', description: 'old' }] });
    const after  = w({ characters: [{ name: 'Thalia', description: 'new' }] });
    expect(computeDelta(before, after).characters).toEqual([]);
  });

  it('skips null→null transitions (no spurious changes)', () => {
    const before = w({ characters: [{ name: 'Thalia', health: null }] });
    const after  = w({ characters: [{ name: 'Thalia', health: null }] });
    expect(computeDelta(before, after).characters).toEqual([]);
  });
});

// ── computeDelta: item identity (the regression guard) ──────────────

describe('computeDelta — items keyed by unique_id', () => {
  it('treats two items with the same name but different unique_id as distinct', () => {
    // The bug we fixed: without unique_id keying, two "Healing Potion" items
    // would collapse to one entry and hide the real diff.
    const before = w({
      items: [
        { unique_id: 'potion-1', name: 'Healing Potion', rarity: 'common' },
      ],
    });
    const after = w({
      items: [
        { unique_id: 'potion-1', name: 'Healing Potion', rarity: 'common' },
        { unique_id: 'potion-2', name: 'Healing Potion', rarity: 'rare' },
      ],
    });
    const delta = computeDelta(before, after);
    // One added item, no changes on the existing one
    expect(delta.items).toHaveLength(1);
    expect(delta.items[0].action).toBe('added');
    expect(delta.items[0].name).toBe('Healing Potion');
    expect(delta.items[0].entity.unique_id).toBe('potion-2');
  });

  it('falls back to name-based keying when unique_id is absent', () => {
    const before = w({ items: [{ name: 'Rusty Sword', rarity: 'common' }] });
    const after  = w({ items: [{ name: 'Rusty Sword', rarity: 'uncommon' }] });
    const delta = computeDelta(before, after);
    expect(delta.items).toHaveLength(1);
    expect(delta.items[0].action).toBe('changed');
    expect(delta.items[0].name).toBe('Rusty Sword');
    expect(delta.items[0].changes).toEqual([{ field: 'rarity', from: 'common', to: 'uncommon' }]);
  });

  it('does not emit spurious changes from owned_by (regression guard)', () => {
    // Bug fix: both ownedBy and owned_by used to be in TRACKED_FIELDS.item,
    // causing a false positive when only one variant was set on each side.
    const before = w({ items: [{ name: 'Sword', ownedBy: 'Thalia' }] });
    const after  = w({ items: [{ name: 'Sword', ownedBy: 'Thalia' }] });
    expect(computeDelta(before, after).items).toEqual([]);
  });

  it('detects an ownedBy change on an item', () => {
    const before = w({ items: [{ name: 'Sword', ownedBy: 'Thalia' }] });
    const after  = w({ items: [{ name: 'Sword', ownedBy: 'Russalo' }] });
    const delta = computeDelta(before, after);
    expect(delta.items[0].changes).toEqual([
      { field: 'ownedBy', from: 'Thalia', to: 'Russalo' },
    ]);
  });
});

// ── computeDelta: locations & factions sanity check ─────────────────

describe('computeDelta — locations & factions', () => {
  it('detects a location discovery change', () => {
    const before = w({ locations: [{ name: 'Temple', discovered: false }] });
    const after  = w({ locations: [{ name: 'Temple', discovered: true  }] });
    const delta = computeDelta(before, after);
    expect(delta.locations[0].changes).toEqual([
      { field: 'discovered', from: false, to: true },
    ]);
  });

  it('detects a faction playerRelation change', () => {
    const before = w({ factions: [{ name: 'The Order', playerRelation: 0 }] });
    const after  = w({ factions: [{ name: 'The Order', playerRelation: 5 }] });
    const delta = computeDelta(before, after);
    expect(delta.factions[0].changes).toEqual([
      { field: 'playerRelation', from: 0, to: 5 },
    ]);
  });
});

// ── computeDelta: handles missing collections gracefully ────────────

describe('computeDelta — missing collections', () => {
  it('treats an undefined collection as empty', () => {
    const before = { currentLocation: 'Tavern' }; // no characters/locations/etc
    const after  = { currentLocation: 'Forest', characters: [{ name: 'Thalia' }] };
    const delta = computeDelta(before, after);
    expect(delta.characters).toHaveLength(1);
    expect(delta.characters[0].action).toBe('added');
  });
});

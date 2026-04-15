/**
 * computeDelta — diff two worldStore snapshots and return a structured
 * description of what changed. Pure function, no side effects.
 *
 * Returns:
 *   {
 *     world:      [{ field, from, to }],
 *     characters: [{ action: 'added'|'removed'|'changed', name, entity?, changes? }],
 *     locations:  [...],
 *     factions:   [...],
 *     items:      [...],
 *   }
 */

const WORLD_FIELDS = ['currentLocation', 'timeOfDay', 'weather', 'tension'];

// Fields compared when diffing an updated entity
const TRACKED_FIELDS = {
  character: ['health', 'status', 'currentLocation', 'level', 'role'],
  location:  ['discovered', 'danger', 'type'],
  faction:   ['power', 'playerRelation', 'alignment'],
  item:      ['ownedBy', 'owned_by', 'location', 'rarity'],
};

function diffEntities(before, after, type) {
  const deltas = [];
  const beforeMap = new Map(before.map(e => [e.name, e]));
  const afterMap  = new Map(after.map(e => [e.name, e]));

  for (const [name, entity] of afterMap) {
    if (!beforeMap.has(name)) {
      deltas.push({ action: 'added', name, entity });
    } else {
      const prev = beforeMap.get(name);
      const changes = [];
      for (const field of TRACKED_FIELDS[type] ?? []) {
        const from = prev[field];
        const to   = entity[field];
        if (from !== to && !(from == null && to == null)) {
          changes.push({ field, from, to });
        }
      }
      if (changes.length) deltas.push({ action: 'changed', name, changes });
    }
  }

  for (const name of beforeMap.keys()) {
    if (!afterMap.has(name)) deltas.push({ action: 'removed', name });
  }

  return deltas;
}

export function computeDelta(before, after) {
  const world = [];
  for (const field of WORLD_FIELDS) {
    if (before[field] !== after[field]) {
      world.push({ field, from: before[field], to: after[field] });
    }
  }

  return {
    world,
    characters: diffEntities(before.characters ?? [], after.characters ?? [], 'character'),
    locations:  diffEntities(before.locations  ?? [], after.locations  ?? [], 'location'),
    factions:   diffEntities(before.factions   ?? [], after.factions   ?? [], 'faction'),
    items:      diffEntities(before.items      ?? [], after.items      ?? [], 'item'),
  };
}

export function hasDelta(delta) {
  return (
    delta.world.length > 0 ||
    delta.characters.length > 0 ||
    delta.locations.length  > 0 ||
    delta.factions.length   > 0 ||
    delta.items.length      > 0
  );
}

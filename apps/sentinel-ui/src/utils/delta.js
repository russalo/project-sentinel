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
  item:      ['ownedBy', 'location', 'rarity'],
};

function diffEntities(before, after, type) {
  const deltas = [];
  const keyOf = type === 'item'
    ? (e) => e.unique_id ?? e.name
    : (e) => e.name;
  const beforeMap = new Map(before.map(e => [keyOf(e), e]));
  const afterMap  = new Map(after.map(e => [keyOf(e), e]));

  for (const [key, entity] of afterMap) {
    if (!beforeMap.has(key)) {
      deltas.push({ action: 'added', name: entity.name, entity });
    } else {
      const prev = beforeMap.get(key);
      const changes = [];
      for (const field of TRACKED_FIELDS[type] ?? []) {
        const from = prev[field];
        const to   = entity[field];
        if (from !== to && !(from == null && to == null)) {
          changes.push({ field, from, to });
        }
      }
      if (changes.length) deltas.push({ action: 'changed', name: entity.name, changes });
    }
  }

  for (const [key, entity] of beforeMap) {
    if (!afterMap.has(key)) deltas.push({ action: 'removed', name: entity.name });
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

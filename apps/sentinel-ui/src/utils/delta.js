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

// Field aliases — read via a single canonical name even if the entity
// carries the alternate spelling. Mirrors the defensive `ownedBy ??
// owned_by` pattern in InventoryPanel.jsx (PR #32) so the diff sees
// the same logical field regardless of casing. Without this, a
// payload that switches casing on the same item would either drop
// the change entirely (if the canonical key is missing) or report
// it as a removal+addition pair on different fields. The backend's
// canonical casing today is `ownedBy`, but the InventoryPanel's
// defensive code implies a non-zero risk that won't always hold —
// the diff layer matches that posture rather than diverging from it.
function fieldValue(entity, field) {
  if (field === 'ownedBy') return entity.ownedBy ?? entity.owned_by;
  return entity[field];
}

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
        const from = fieldValue(prev, field);
        const to   = fieldValue(entity, field);
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

/**
 * Tests for utils/delta.js — the world-snapshot diff helpers.
 *
 * `computeDelta` is a pure function: takes two worldStore snapshots,
 * returns a structured description of what changed. No React, no
 * stores, no DOM. The natural first vitest target — every test
 * here runs in <1ms with zero setup.
 *
 * Coverage:
 *   - empty → empty (no false-positive changes)
 *   - hasDelta() boolean correctness
 *   - world metric changes
 *   - entity added / removed / changed
 *   - items keyed by unique_id (regression for PR #34 review)
 *   - ownedBy / owned_by normalization (regression for PR #36)
 */

import { describe, it, expect } from 'vitest'
import { computeDelta, hasDelta } from './delta'

// Shared empty snapshot — every entity collection initialised so
// callers don't have to remember what the world shape looks like.
function emptySnapshot(overrides = {}) {
  return {
    currentLocation: null,
    timeOfDay: null,
    weather: null,
    tension: 0,
    characters: [],
    locations: [],
    factions: [],
    items: [],
    ...overrides,
  }
}

describe('hasDelta', () => {
  it('returns false for an empty delta', () => {
    const empty = computeDelta(emptySnapshot(), emptySnapshot())
    expect(hasDelta(empty)).toBe(false)
  })

  it('returns true when any collection has at least one entry', () => {
    const before = emptySnapshot()
    const after = emptySnapshot({
      characters: [{ name: 'Kael', status: 'alive' }],
    })
    expect(hasDelta(computeDelta(before, after))).toBe(true)
  })

  it('returns true when only a world metric changed', () => {
    const before = emptySnapshot({ weather: 'clear' })
    const after = emptySnapshot({ weather: 'storm' })
    expect(hasDelta(computeDelta(before, after))).toBe(true)
  })
})

describe('computeDelta — world metrics', () => {
  it('reports a weather change', () => {
    const before = emptySnapshot({ weather: 'clear' })
    const after = emptySnapshot({ weather: 'storm' })
    const delta = computeDelta(before, after)

    expect(delta.world).toEqual([
      { field: 'weather', from: 'clear', to: 'storm' },
    ])
    expect(delta.characters).toEqual([])
  })

  it('reports multiple metric changes in one delta', () => {
    const before = emptySnapshot({
      currentLocation: 'tavern',
      tension: 2,
      timeOfDay: 'dusk',
    })
    const after = emptySnapshot({
      currentLocation: 'forest',
      tension: 7,
      timeOfDay: 'midnight',
    })
    const delta = computeDelta(before, after)

    // Field order matches WORLD_FIELDS in delta.js — the test
    // depends on it because the user-facing log lists fields in
    // that order. If the source-of-truth order ever changes, this
    // test should fail loudly so we confirm it's intentional.
    expect(delta.world).toEqual([
      { field: 'currentLocation', from: 'tavern', to: 'forest' },
      { field: 'timeOfDay', from: 'dusk', to: 'midnight' },
      { field: 'tension', from: 2, to: 7 },
    ])
  })

  it('does not report unchanged metrics', () => {
    const before = emptySnapshot({ weather: 'clear', tension: 5 })
    const after = emptySnapshot({ weather: 'clear', tension: 5 })
    const delta = computeDelta(before, after)
    expect(delta.world).toEqual([])
  })
})

describe('computeDelta — entity collections', () => {
  it('reports an added character', () => {
    const before = emptySnapshot()
    const after = emptySnapshot({
      characters: [{ name: 'Kael', role: 'fighter', status: 'alive' }],
    })
    const delta = computeDelta(before, after)

    expect(delta.characters).toHaveLength(1)
    expect(delta.characters[0]).toMatchObject({
      action: 'added',
      name: 'Kael',
      entity: { name: 'Kael', role: 'fighter' },
    })
  })

  it('reports a removed character', () => {
    const before = emptySnapshot({
      characters: [{ name: 'Kael', status: 'alive' }],
    })
    const after = emptySnapshot()
    const delta = computeDelta(before, after)

    expect(delta.characters).toEqual([{ action: 'removed', name: 'Kael' }])
  })

  it('reports a changed character field', () => {
    const before = emptySnapshot({
      characters: [{ name: 'Kael', health: 100, status: 'alive' }],
    })
    const after = emptySnapshot({
      characters: [{ name: 'Kael', health: 60, status: 'alive' }],
    })
    const delta = computeDelta(before, after)

    expect(delta.characters).toHaveLength(1)
    expect(delta.characters[0]).toMatchObject({
      action: 'changed',
      name: 'Kael',
      changes: [{ field: 'health', from: 100, to: 60 }],
    })
  })

  it('does not report a changed field when only an untracked field moved', () => {
    // `description` is not in TRACKED_FIELDS.character, so a change
    // there should produce no delta entry. This is a deliberate
    // narrowness — the diff only surfaces the gameplay-relevant
    // fields, not every field the DM might touch.
    const before = emptySnapshot({
      characters: [{ name: 'Kael', health: 100, description: 'old' }],
    })
    const after = emptySnapshot({
      characters: [{ name: 'Kael', health: 100, description: 'new' }],
    })
    const delta = computeDelta(before, after)
    expect(delta.characters).toEqual([])
  })
})

describe('computeDelta — items keyed by unique_id (PR #34 review fix)', () => {
  it('keys items by unique_id when present, not by name', () => {
    // Two items with the same display name but different unique_id.
    // The original (pre-fix) code keyed by name and would collapse
    // them into a single Map entry, dropping one of the two.
    const before = emptySnapshot({
      items: [
        { unique_id: 'gold-1', name: 'Gold Coin', rarity: 'common' },
      ],
    })
    const after = emptySnapshot({
      items: [
        { unique_id: 'gold-1', name: 'Gold Coin', rarity: 'common' },
        { unique_id: 'gold-2', name: 'Gold Coin', rarity: 'common' },
      ],
    })
    const delta = computeDelta(before, after)

    // The new item should land as 'added', not collapsed into the
    // existing one as a no-op.
    expect(delta.items).toHaveLength(1)
    expect(delta.items[0].action).toBe('added')
    expect(delta.items[0].entity.unique_id).toBe('gold-2')
  })

  it('falls back to name-keying for items without unique_id', () => {
    // Pre-Layer-1.5 payloads that don't carry unique_id still need
    // to diff correctly. The keyOf helper falls back to name for
    // items missing unique_id — verified here so that fallback
    // doesn't silently rot.
    const before = emptySnapshot({
      items: [{ name: 'Old Sword', rarity: 'common' }],
    })
    const after = emptySnapshot({
      items: [{ name: 'Old Sword', rarity: 'rare' }],
    })
    const delta = computeDelta(before, after)

    expect(delta.items).toHaveLength(1)
    expect(delta.items[0]).toMatchObject({
      action: 'changed',
      name: 'Old Sword',
      changes: [{ field: 'rarity', from: 'common', to: 'rare' }],
    })
  })
})

describe('computeDelta — ownedBy / owned_by normalization (PR #36 fix)', () => {
  it('treats ownedBy and owned_by as the same field when reading', () => {
    // The backend's canonical casing is `ownedBy`. This test
    // simulates a payload that switches casing on the same item:
    // before has ownedBy, after has owned_by. The diff should
    // see them as equal and report no change — not as a removal
    // + addition pair on different fields.
    const before = emptySnapshot({
      items: [{ unique_id: 'sword-1', name: 'Iron Sword', ownedBy: 'Kael' }],
    })
    const after = emptySnapshot({
      items: [{ unique_id: 'sword-1', name: 'Iron Sword', owned_by: 'Kael' }],
    })
    const delta = computeDelta(before, after)

    expect(delta.items).toEqual([])
  })

  it('reports an actual ownership change regardless of which key was used', () => {
    // before has ownedBy: 'Kael', after has owned_by: 'Thalia' —
    // a real ownership change that happens to switch keys at the
    // same time. The diff should report a single change on the
    // canonical `ownedBy` field, not two phantom rows.
    const before = emptySnapshot({
      items: [{ unique_id: 'sword-1', name: 'Iron Sword', ownedBy: 'Kael' }],
    })
    const after = emptySnapshot({
      items: [{ unique_id: 'sword-1', name: 'Iron Sword', owned_by: 'Thalia' }],
    })
    const delta = computeDelta(before, after)

    expect(delta.items).toHaveLength(1)
    expect(delta.items[0]).toMatchObject({
      action: 'changed',
      name: 'Iron Sword',
      changes: [{ field: 'ownedBy', from: 'Kael', to: 'Thalia' }],
    })
  })
})

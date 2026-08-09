/**
 * Tests for worldStore.applyUpdate — the SSE world_update reducer.
 *
 * Focus: a world_update hint carries only what CHANGED, so a character's
 * `module_data` arrives partial. Before the deep-merge fix a partial hint
 * replaced the whole stored `module_data`, wiping `hp` / `magic_pool` /
 * `combat` — which made PlayerVitals fall back to `health: 100` and the HP bar
 * jump to full, sticking until reload (nothing re-hydrates per turn).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useWorldStore } from './worldStore';

const PC = {
  name: 'Kael',
  role: 'player',
  status: 'alive',
  module_data: {
    character_sheet: {
      stats: { body: 7, mind: 5, heart: 6, will: 4 },
      hp: { current: 30, max: 56 },
      magic_pool: { current: 8, max: 10 },
    },
    combat: { death_saves_failed: 1 },
  },
};

function seedPC(extra = {}) {
  useWorldStore.setState({
    characters: [JSON.parse(JSON.stringify({ ...PC, ...extra }))],
  });
}

const pc = () => useWorldStore.getState().characters[0];
const sheet = () => pc().module_data.character_sheet;

beforeEach(() => {
  useWorldStore.setState({
    characters: [],
    locations: [],
    factions: [],
    items: [],
  });
});

describe('applyUpdate — character module_data deep merge', () => {
  it('a stats-only hint (RFC-0017 level-up mirror) preserves hp/magic_pool/combat', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [
        {
          name: 'Kael',
          action: 'upsert',
          module_data: { character_sheet: { stats: { body: 8 } } },
        },
      ],
    });
    expect(sheet().stats).toEqual({ body: 8 }); // leaf object replaced wholesale
    expect(sheet().hp).toEqual({ current: 30, max: 56 }); // sibling survives
    expect(sheet().magic_pool).toEqual({ current: 8, max: 10 });
    expect(pc().module_data.combat).toEqual({ death_saves_failed: 1 });
  });

  it('a combat-only hint (RFC-0014 death mirror) preserves the character sheet', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [
        {
          name: 'Kael',
          action: 'upsert',
          status: 'unconscious',
          module_data: { combat: { death_saves_failed: 2 } },
        },
      ],
    });
    expect(pc().status).toBe('unconscious');
    expect(pc().module_data.combat).toEqual({ death_saves_failed: 2 });
    expect(sheet().hp).toEqual({ current: 30, max: 56 }); // the bug this fixes
    expect(sheet().stats.body).toBe(7);
  });

  it('an hp-only hint (ordinary damage turn) preserves stats and magic_pool', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [
        {
          name: 'Kael',
          action: 'upsert',
          module_data: { character_sheet: { hp: { current: 12, max: 56 } } },
        },
      ],
    });
    expect(sheet().hp).toEqual({ current: 12, max: 56 });
    expect(sheet().stats.body).toBe(7);
    expect(sheet().magic_pool).toEqual({ current: 8, max: 10 });
  });

  it('a hint with no module_data leaves the stored module_data intact', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [{ name: 'Kael', action: 'upsert', currentLocation: 'The Mill' }],
    });
    expect(pc().currentLocation).toBe('The Mill');
    expect(sheet().hp).toEqual({ current: 30, max: 56 });
    expect(pc().module_data.combat).toEqual({ death_saves_failed: 1 });
  });

  it('ordinary (non-module_data) fields still shallow-override', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [{ name: 'Kael', action: 'upsert', status: 'dead' }],
    });
    expect(pc().status).toBe('dead');
    expect(pc().role).toBe('player'); // untouched field survives
  });

  it('a character with no stored module_data takes the incoming one', () => {
    useWorldStore.setState({ characters: [{ name: 'Kael', role: 'player' }] });
    useWorldStore.getState().applyUpdate({
      characters: [
        {
          name: 'Kael',
          action: 'upsert',
          module_data: { character_sheet: { hp: { current: 40, max: 40 } } },
        },
      ],
    });
    expect(sheet().hp).toEqual({ current: 40, max: 40 });
  });

  it('a new character is appended as-is', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [{ name: 'Borin', action: 'upsert', role: 'npc' }],
    });
    expect(useWorldStore.getState().characters).toHaveLength(2);
    expect(useWorldStore.getState().characters[1].name).toBe('Borin');
  });

  it('remove still drops the character', () => {
    seedPC();
    useWorldStore.getState().applyUpdate({
      characters: [{ name: 'Kael', action: 'remove' }],
    });
    expect(useWorldStore.getState().characters).toHaveLength(0);
  });

  it('a malformed module_data (non-object) is ignored, not applied', () => {
    // Malformed-LLM-output tolerance: keep the good stored sheet rather than
    // letting a garbage value through and blanking the vitals panel.
    seedPC();
    expect(() =>
      useWorldStore.getState().applyUpdate({
        characters: [{ name: 'Kael', action: 'upsert', module_data: 'oops' }],
      }),
    ).not.toThrow();
    expect(sheet().hp).toEqual({ current: 30, max: 56 });
    expect(pc().module_data.combat).toEqual({ death_saves_failed: 1 });
  });
});

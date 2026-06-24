import { describe, it, expect, vi, afterEach } from 'vitest';
import { computeRoll, toWirePayload, marginBand, rollD100 } from './roll';

afterEach(() => {
  vi.restoreAllMocks();
});

// Pin the d100 by stubbing Math.random. Math.random() in [0,1) →
// 1 + floor(r*100). r=0 → 1; r=0.46 → 47; r=0.999 → 100.
function stubRolls(...values) {
  // values are the desired d100 outputs (1-100), consumed in order.
  let i = 0;
  vi.spyOn(Math, 'random').mockImplementation(() => {
    const v = values[i++];
    return (v - 1) / 100; // inverse of 1 + floor(r*100)
  });
}

describe('rollD100', () => {
  it('is within 1..100', () => {
    for (let i = 0; i < 50; i++) {
      const r = rollD100();
      expect(r).toBeGreaterThanOrEqual(1);
      expect(r).toBeLessThanOrEqual(100);
    }
  });
});

describe('computeRoll', () => {
  it('ordinary roll: total = d100 + stat*5, margin = total - target', () => {
    stubRolls(47);
    const r = computeRoll({ stat: 'body', statValue: 6, target: 80 });
    expect(r.rolled).toBe(47);
    expect(r.bonus).toBe(30); // 6 * 5
    expect(r.total).toBe(77); // 47 + 30
    expect(r.margin).toBe(-3); // 77 - 80
    expect(r.openEnded).toBeNull();
  });

  it('open-ended high: 96-100 rolls again and adds; rolled stays the first d100', () => {
    stubRolls(98, 40); // first 98 (open high), reroll 40
    const r = computeRoll({ stat: 'body', statValue: 5, target: 60 });
    expect(r.rolled).toBe(98); // wire field stays 1-100
    expect(r.openEnded).toBe('high');
    expect(r.openEndedRoll).toBe(40);
    expect(r.total).toBe(98 + 40 + 25); // first + openEnded + bonus
    expect(r.margin).toBe(163 - 60);
  });

  it('open-ended low: 1-5 rolls again and subtracts', () => {
    stubRolls(3, 67); // first 3 (open low), reroll 67 subtracted
    const r = computeRoll({ stat: 'mind', statValue: 4, target: 50 });
    expect(r.rolled).toBe(3);
    expect(r.openEnded).toBe('low');
    expect(r.openEndedRoll).toBe(-67);
    expect(r.total).toBe(3 - 67 + 20);
    expect(r.margin).toBeLessThan(0);
  });

  it('applies situational mods', () => {
    stubRolls(50);
    const r = computeRoll({ stat: 'will', statValue: 5, target: 60, mods: 10 });
    expect(r.total).toBe(50 + 25 + 10);
  });
});

describe('computeRoll — weapon die (RFC-0007 combat)', () => {
  it('rolls the weapon die when weaponDie is given', () => {
    // Raw randoms: 0.46 → d100 47; 0.5 → 1d8 = 1 + floor(0.5*8) = 5.
    // (The stubRolls d100-inverse mapping doesn't apply to a d8, so spy directly.)
    const vals = [0.46, 0.5];
    let i = 0;
    vi.spyOn(Math, 'random').mockImplementation(() => vals[i++]);
    const r = computeRoll({ stat: 'body', statValue: 6, target: 55, weaponDie: '1d8' });
    expect(r.rolled).toBe(47);
    expect(r.weaponDie).toBe('1d8');
    expect(r.weaponRoll).toBe(5);
    expect(r.weaponRoll).toBeGreaterThanOrEqual(1);
    expect(r.weaponRoll).toBeLessThanOrEqual(8);
  });

  it('weaponRoll is null for a non-combat check', () => {
    stubRolls(47);
    const r = computeRoll({ stat: 'mind', statValue: 5, target: 40 });
    expect(r.weaponRoll).toBeNull();
    expect(r.weaponDie).toBeNull();
  });

  it('an unparseable weapon spec yields null (no weapon roll)', () => {
    stubRolls(47);
    const r = computeRoll({ stat: 'body', statValue: 5, target: 55, weaponDie: 'sword' });
    expect(r.weaponRoll).toBeNull();
  });
});

describe('toWirePayload', () => {
  it('extracts exactly the seven backend fields (1-100 rolled, openEnded camel)', () => {
    stubRolls(47);
    const r = computeRoll({ stat: 'body', statValue: 6, target: 80 });
    const wire = toWirePayload(r);
    expect(Object.keys(wire).sort()).toEqual(
      ['bonus', 'margin', 'openEnded', 'rolled', 'stat', 'target', 'total'].sort(),
    );
    expect(wire.rolled).toBe(47);
    expect(wire.rolled).toBeGreaterThanOrEqual(1);
    expect(wire.rolled).toBeLessThanOrEqual(100);
    // display-only extras are NOT on the wire
    expect(wire.statValue).toBeUndefined();
    expect(wire.openEndedRoll).toBeUndefined();
  });

  it('open-ended rolled stays in 1-100 for the backend validator', () => {
    stubRolls(99, 80);
    const r = computeRoll({ stat: 'body', statValue: 5, target: 60 });
    const wire = toWirePayload(r);
    expect(wire.rolled).toBe(99); // not 179 — the surge is in `total`
    expect(wire.total).toBe(99 + 80 + 25);
  });
});

describe('marginBand', () => {
  it('maps margin + open-ended to a band + tone', () => {
    expect(marginBand(45, null).label).toBe('Decisive');
    expect(marginBand(15, null).label).toBe('Solid');
    expect(marginBand(5, null).label).toBe('Scrapes it');
    expect(marginBand(-3, null).label).toBe('Near miss');
    expect(marginBand(-25, null).label).toBe('Failure');
    expect(marginBand(0, 'high').label).toBe('Surge');
    expect(marginBand(0, 'low').label).toBe('Fumble');
  });
});

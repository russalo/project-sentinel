// d100 open-ended roll logic (ADR-0005 resolution module / RFC-0006).
//
// Rolled CLIENT-SIDE so the randomness is real, not LLM-biased — the roll
// is the trust anchor of the dice game. The result is sent to the backend
// on the resolve turn; the DM resolves the action from the margin.
//
// The mechanic (Fantasy-flagship v0.1, ratified 2026-06-23):
//   total  = d100 + (stat × 5) + situational mods
//   margin = total − target          (≥ 0 success; magnitude = degree)
//   open-ended:  a natural 96–100 rolls again and ADDS (a surge);
//                a natural 01–05 rolls again and SUBTRACTS (a fumble spiral).
//
// Wire contract (backend RollResult): { stat, rolled, bonus, total, target,
// margin, openEnded }. `rolled` is the FIRST d100 (1–100, validated server-
// side); the open-ended adjustment is folded into `total`, so `rolled` stays
// in range even on a surge. The richer breakdown (first roll, open-ended
// reroll, stat value) is kept locally for the reveal display.

export function rollD100() {
  return 1 + Math.floor(Math.random() * 100);
}

// Roll a single weapon die from a "1dN" spec (RFC-0007 combat). Returns
// 1..N, or null for an unrecognized/oversized spec. v0.1 supports the
// single-die "1dN" form only (light 1d4 … two-handed 1d10).
export function rollWeaponDie(spec) {
  const m = /^1d(\d+)$/.exec(String(spec ?? '').trim());
  if (!m) return null;
  const sides = parseInt(m[1], 10);
  if (!(sides >= 2 && sides <= 100)) return null;
  return 1 + Math.floor(Math.random() * sides);
}

// v0.1 open-ended is a SINGLE reroll (not a chain) — simpler to display and
// reason about; chaining is a deferred RM-style depth pass.
//
// `weaponDie` (RFC-0007 combat): when the check is an attack, roll the
// weapon die alongside the d100 — the DM computes damage from
// weapon_roll + floor(margin/10). Omit for non-combat checks.
export function computeRoll({ stat, statValue, target, mods = 0, weaponDie = null }) {
  const first = rollD100();
  let openEnded = null;
  let openEndedRoll = 0;
  if (first >= 96) {
    openEnded = 'high';
    openEndedRoll = rollD100();
  } else if (first <= 5) {
    openEnded = 'low';
    openEndedRoll = -rollD100();
  }
  const bonus = statValue * 5;
  const total = first + openEndedRoll + bonus + mods;
  const margin = total - target;
  const weaponRoll = weaponDie ? rollWeaponDie(weaponDie) : null;
  return {
    // ── wire fields (sent to the backend) ──
    stat,
    rolled: first, // 1–100; the open-ended adjustment lives in `total`
    bonus,
    total,
    target,
    margin,
    openEnded,
    // weapon fields only on a combat attack (null otherwise)
    weaponDie: weaponRoll !== null ? weaponDie : null,
    weaponRoll,
    // ── display-only extras (not sent; used by the reveal) ──
    statValue,
    mods,
    openEndedRoll,
  };
}

// Extract just the backend RollResult fields from a computeRoll() result.
// weaponDie/weaponRoll are included only when the check was an attack.
export function toWirePayload(r) {
  const wire = {
    stat: r.stat,
    rolled: r.rolled,
    bonus: r.bonus,
    total: r.total,
    target: r.target,
    margin: r.margin,
    openEnded: r.openEnded,
  };
  if (r.weaponRoll !== null && r.weaponRoll !== undefined) {
    wire.weaponDie = r.weaponDie;
    wire.weaponRoll = r.weaponRoll;
  }
  return wire;
}

// Categorical band for the margin, mirroring the resolution prompt's bands —
// used to color/label the reveal. (The DM narrates from the same bands.)
export function marginBand(margin, openEnded) {
  if (openEnded === 'high') return { label: 'Surge', tone: 'leyline' };
  if (openEnded === 'low') return { label: 'Fumble', tone: 'blood' };
  if (margin < 0) return margin <= -10
    ? { label: 'Failure', tone: 'blood' }
    : { label: 'Near miss', tone: 'blood' };
  if (margin <= 9) return { label: 'Scrapes it', tone: 'amber' };
  if (margin <= 29) return { label: 'Solid', tone: 'leyline' };
  return { label: 'Decisive', tone: 'leyline' };
}

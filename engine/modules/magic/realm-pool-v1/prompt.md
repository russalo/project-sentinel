MAGIC (realm pool, d100 casting):

Mages and Clerics (and caster-flavored classes) wield magic through a
pool of energy, organized into realms, drawn from a binding.

THE POOL:

A caster's magic pool lives at `module_data.character_sheet.magic_pool =
{current, max}`, where `max = Will × 2` (a Will-8 caster has 16). Set it
when the caster is established. Spells cost from `current` by tier:

- **Cantrip** 0 · **Minor** 1 · **Standard** 2 · **Major** 4 · **Devastating** 8

Check `current` before a cast: if it can't cover the cost, the spell
fizzles or the caster improvises something lesser. The cost is spent
the moment the spell is **cast** — `current -= cost` — whether or not a
contested roll lands. The energy is expended either way; a missed or
resisted spell still drains the pool. Refresh: **long rest → full**,
**short rest → half**.

BINDINGS (assign from fiction — no menu):

When a caster first casts, bind them to a source that fits their
established fiction, and write `module_data.magic = {binding, realms}`
(+ `patron_standing` for clerics). The binding gates which realms they
can draw from. Use **lowercase** values: `binding` is `"deity:<slug>"`
(e.g. `"deity:the-mender"`) or `"tradition:<slug>"` (e.g.
`"tradition:elementalist"`), and `realms` is lowercase realm slugs —
`healing`, `blessing`, `wrath`, `curse`, `elemental`, `conjuration`,
`illusion`, `binding`. Never capitalize them in the state JSON.

- **Clerics — a Patron deity.** Pick the deity whose domains fit the
  character. Each grants TWO domain realms:
  - **The Mender** — Healing + Blessing. Compassionate; rivers, hearth,
    quiet endings. Tenets: aid the wounded regardless of allegiance;
    refuse cruelty; honor the river.
  - **The Avenger** — Wrath + Curse. Vengeful, harsh; storm, the broken
    oath. Tenets: strike the oathbreaker; show no mercy to the cruel;
    remember every wrong.
  - **The Balance** — Healing + Curse. Keeper of life and death; sickle,
    dusk, the threshold. Tenets: neither hasten nor deny a death's due;
    take a life only to save one; keep the ledger even.
  - **The Champion** — Wrath + Blessing. Holy fury; sun, sword, the
    righteous defender. Tenets: shield the innocent; meet evil head-on;
    never abandon an ally.
  Set `patron_standing` (start ~7). When the cleric acts against their
  deity's tenets, narrate the dissonance and lower standing; honoring
  them raises it. (No spell lockout in v0.1 — standing is narrative
  pressure.)

- **Mages — an Arcane Tradition.** Each has a PRIMARY realm (listed
  cost) and a SECONDARY realm (**+1 pool cost**):
  - **Elementalist** — Elemental (primary) + Conjuration (secondary).
  - **Illusionist** — Illusion + Binding.
  - **Conjurer** — Conjuration + Binding.
  - **Binder** — Binding + Elemental.

CASTING:

- A spell must be in a realm the caster's binding grants. A secondary-
  realm spell (Mage) costs +1 pool.
- **Contested spell** (it attacks, or a target resists): request a
  **Will check** the same way as any d100 check — `stat: "will"`,
  `target`: the foe's Defense or a resist DC (Easy 40 / Moderate 60 /
  Hard 80 / Very Hard 100), and `effect_die`: the spell's die (below).
  Resolve from the margin; the spell's magnitude (damage or healing) is
  `effect_roll + ⌊margin/10⌋`, exactly like a weapon hit.
- **Uncontested spell** (self-buff, utility, healing, a ward, an
  illusion no one is actively resisting): no d100 contest. Spend the
  pool and narrate the effect. For an uncontested spell with a listed
  magnitude die (e.g. Mend's `heal 1d8`), apply a value within that
  die's range as the effect — treat the die's average as a sensible
  default — rather than running the contested d100 + `effect_die`
  machinery, which is for contested casts only.

SPELL REFERENCE (~3 per realm; tier · cost · effect):

Mage realms —
- **Elemental**: Firebolt (Standard, contested, 1d8 fire) · Frost Lance
  (Major, contested, 1d10 cold + slow) · Stoneskin (Minor, self, +Defense).
- **Conjuration**: Summon Blade (Minor, self, a spectral weapon 1d8) ·
  Wall of Force (Standard, utility, blocks a path) · Banish (Major,
  contested, 1d10 vs summoned/extraplanar).
- **Illusion**: Blur (Minor, self, attackers' checks suffer) · Phantasm
  (Standard, contested vs Will, fear/confusion) · Veil (Cantrip, utility,
  hide a person or object).
- **Binding**: Hold (Standard, contested vs Will, target frozen) ·
  Counterspell (Standard, contested vs caster's Will, negate a spell) ·
  Ward (Minor, self/ally, resist one school).

Cleric realms —
- **Healing**: Mend (Minor, ally, heal 1d8) · Cleanse (Standard, ally,
  cure affliction/poison) · Revive (Devastating, ally, return from
  unconscious/recent death).
- **Wrath**: Smite (Standard, contested, 1d8 radiant) · Holy Fire (Major,
  contested, 1d10 radiant, more vs undead/fiend) · Condemn (Devastating,
  contested vs Will, a foe's doom).
- **Blessing**: Bless (Minor, ally, +bonus to their checks) · Sanctuary
  (Standard, self/ally, foes must resist to attack them) · Aegis (Major,
  ally, absorb a blow).
- **Curse**: Hex (Minor, contested vs Will, target's checks suffer) ·
  Wither (Standard, contested, 1d8 necrotic + weaken) · Doom (Major,
  contested vs Will, a compounding curse).

Treat this list as the core repertoire; a caster may attempt a kindred
spell within their realms at a sensible tier/cost. Keep magic bound by
the pool and the realms — a caster cannot cast outside their granted
realms, and an empty pool means no more spells until they rest.

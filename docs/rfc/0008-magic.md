# RFC 0008 — Magic module

**Status:** Implemented
**Date:** 2026-06-24
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005, fourth mechanic slice — Mage/Cleric casting,
the magic pool, the caster bindings (deity Patron / arcane Tradition),
against Fantasy-flagship v0.1 Axis 6 (ratified 2026-06-23/24).
**Supersedes:** —

---

## Where this sits

Under ADR-0005, after RFC-0007 (class + combat). One module:
`core/realm-pool-v1` (subsystem **magic**). Like combat, casting reuses
the RFC-0006 d100 loop — a targeted spell is a Will check vs a DC — so
the engineering is the module prompt + `module_data.magic` + spell/patron/
tradition **content**, not new roll infrastructure.

## Ratified decisions

From the earlier design pass + 2026-06-24:

- **Pool:** `magic_pool.max = Will × 2` (already in the four-stat schema);
  spell costs Cantrip 0 / Minor 1 / Standard 2 / Major 4 / Devastating 8;
  refresh full on long rest, half on short rest.
- **Realms:** Mage — Elemental, Conjuration, Illusion, Binding;
  Cleric — Healing, Wrath, Blessing, Curse.
- **Cleric Patron (deity-bound):** picks one of 4 deities; the deity's
  `domain_realms` (2) gate the cleric's accessible realms; 2–3 tenets
  (prompt-shaping); `patron_standing` 0–10 (DM-writable). Fall mechanic
  deferred.
- **Mage Tradition:** picks one of 4; primary realm at listed cost,
  secondary realm at **+1 pool**.
- **Casting resolution:** contested/targeted spells roll **Will vs a DC**
  (reuse the d100 loop); effect is **margin-scaled** (`effect_die +
  ⌊margin/10⌋`, the combat hybrid). Self/buff/utility spells just spend
  pool — no roll.
- **Spell content:** ~3 per realm (~24 total) so every binding is playable.
- **Binding selection:** the DM assigns the patron/tradition from the
  character's established fiction (no creation selector — consistent with
  free-text `class`).

## Proposal

### 1. Generalize `weapon_die` → `effect_die` (cross-stack rename)

Combat's `weapon_die`/`weapon_roll` (RFC-0007) and a spell's effect die
are the same concept: a magnitude die rolled client-side alongside the
d100, feeding `effect = die + ⌊margin/10⌋`. Rename to `effect_die`/
`effect_roll` so one field serves both weapons and spells:

- `check_request.weapon_die` → `effect_die`
- `RollResult.weapon_die`/`weapon_roll` → `effect_die`/`effect_roll`
  (still bounded 1..100)
- `_roll_block` field names; `roll.js` (`rollWeaponDie` →
  `rollEffectDie`, `weaponDie`→`effectDie`); `CheckRequestRail` reveal
  label ("weapon"→"effect", shown as the weapon or spell die);
  `chatStore.setCheckRequest` field; the combat module prompt.
- Tests updated for the new field names.

Mechanical rename; no behavior change for combat (a weapon's die now
rides `effect_die`).

### 2. `core/realm-pool-v1` (subsystem: magic)

Prompt-fragment module + a `schema_fragment` for `module_data.magic`.

**`module_data.magic`** (caster characters):
```json
"magic": {
  "binding": "deity:the-mender",   // or "tradition:elementalist"
  "patron_standing": 7,            // clerics only; DM-writable
  "realms": ["healing", "blessing"]  // derived from the binding
}
```
(`magic_pool` already lives in `module_data.character_sheet` per RFC-0006.)

**Prompt teaches:**
- **Binding from fiction:** when a Mage/Cleric (or caster-flavored class)
  first casts, bind them — a deity Patron (Cleric) or arcane Tradition
  (Mage) that fits their established fiction — and set
  `module_data.magic`. Clerics get the deity's 2 domain realms; Mages get
  the tradition's primary + secondary (secondary costs +1 pool).
- **Casting:** a spell the caster knows in an accessible realm. Check the
  pool (`magic_pool.current ≥ cost`); if short, the spell fizzles or they
  improvise something lesser. Spend the cost on cast.
- **Contested cast** (attack/save spell): request a **Will check vs the
  target's DC** (the resolution loop), with `effect_die` = the spell's
  effect die. Resolve from the margin; effect = `effect_roll +
  ⌊margin/10⌋`. Uncontested (self/buff/utility): no roll, just spend pool
  + narrate.
- **Tenets (Cleric):** narrate dissonance / shifting `patron_standing`
  when the cleric acts against the deity's tenets. No mechanical spell-
  lockout v0.1 (fall deferred).
- **Refresh:** long rest → pool to max; short rest → half.

### 3. Content (authored TOML presets)

- **Patrons** — `data/lore/core/presets/patrons/fantasy/<slug>.toml` (4):
  the-mender (Healing+Blessing), the-avenger (Wrath+Curse), the-balance
  (Healing+Curse), the-champion (Wrath+Blessing). Each: name, short,
  domain_realms, tenets[], presence_notes.
- **Traditions** — `data/lore/core/presets/traditions/fantasy/<slug>.toml`
  (4): elementalist (Elemental+Conjuration), illusionist
  (Illusion+Binding), conjurer (Conjuration+Binding), binder
  (Binding+Elemental). Each: name, short, primary, secondary, flavor.
- **Spells** — `data/lore/core/presets/spells/<realm>/<slug>.toml`
  (~3 × 8 realms ≈ 24). Each: name, realm, tier (cantrip…devastating),
  cost, contested (bool), effect_die (for contested damage spells),
  description.

The DM reads these as content (loaded by `backend/presets.py`-style
loading + composed into the prompt or surfaced on demand). v0.1 may
inline a compact realm/spell summary into the magic prompt fragment
rather than per-spell dynamic loading — see Open Q2.

### 4. DEFAULT_MODULES + re-baseline

`DEFAULT_MODULES` grows to the six-module set (… + `magic`). Assembly
test re-baselines (derived from fragments). Base-fragment integrity
intact.

## Resolved (2026-06-24)

1. **Patron as a tracked codex entity → DEFERRED.** Binding + standing
   live on `module_data.magic`; the patron-as-codex-card is a later
   polish slice.
2. **Spell content delivery → INLINE.** The realms, ~24 spells, 4
   patrons, and 4 traditions are inlined in the magic prompt fragment —
   the whole repertoire fits the prompt budget (assembled default ~22k
   chars) and avoids a per-spell loader. The *module* is the swap point
   for community magic; per-spell preset loading is a later optimization.
   (This collapsed the planned two slices into one PR — there are no
   separate content files to author.)
3. **Effect-die rename → YES.** `weapon_die`/`weapon_roll` generalized to
   `effect_die`/`effect_roll` across engine/backend/frontend + tests; no
   combat behavior change. Combat and spells share the one magnitude-die
   field.
4. **Slice or one PR → ONE PR.** With content inline, the work is the
   rename + the magic module + `module_data.magic` + DEFAULT + tests —
   shipped together.

## Acceptance Criteria

- [ ] `weapon_die`→`effect_die` generalized across engine/backend/
      frontend + tests (no combat behavior change).
- [ ] `core/realm-pool-v1` module: manifest + prompt + schema_fragment
      for `module_data.magic`.
- [ ] 4 patron + 4 tradition + ~24 spell TOMLs authored.
- [ ] Casting reuses the d100 loop (contested = Will check, margin-scaled
      via effect_die); uncontested = pool-only.
- [ ] Pool spend/refresh + binding-from-fiction in the prompt.
- [ ] `DEFAULT_MODULES` += magic; assembly re-baselined; base integrity
      intact.
- [ ] RFC 0008 lands Implemented; README index + Blueprint KB manifest
      updated.

## Out of Scope

- **Patron-as-codex-entity** (OQ1) — deferred.
- **Fall mechanic** (standing < threshold → spell lockout) — `patron_standing`
  ships DM-writable; the hard cutoff is deferred.
- **Counterspell / dispel / concentration** — later.
- **Per-spell dynamic preset loading** if OQ2 = inline.
- **Multiclass casters / spell learning/progression** — RFC-0009+.
- **Creation selectors** for patron/tradition — DM-from-fiction in v0.1.

## Cross-links

- ADR-0005; RFC-0006 (the d100 loop casting reuses); RFC-0007 (combat —
  the effect-die hybrid + the `effect_die` field magic generalizes);
  Fantasy-flagship v0.1 Axis 6.
- Downstream: RFC-0009 (progression) grows spells known + pool.

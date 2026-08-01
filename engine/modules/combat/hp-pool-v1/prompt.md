COMBAT (HP pool, round-per-roll):

HIT POINTS:

Every combat-capable character has hit points under
`module_data.character_sheet.hp = {"current": N, "max": N}`, where
`max = Body × class_HP_factor` (Warrior ×8, Rogue ×6, Mage ×4, Cleric ×6).
A Body-6 Warrior has 48 HP; a Body-3 Mage has 12.

Set a character's hp the first time they enter combat (or when first
established), grounded in their Body and class. For the PLAYER character,
`hp.max` is engine-maintained once play begins: **establish it at creation,
then do NOT change it** — the engine keeps it in sync with Body and grows it
on a level-up. Just drive the player's `current` (damage/healing). An NPC's
hp is yours throughout. `current` falls with damage and rises with healing.

ATTACKING (one roll per combat turn — round-per-roll):

When the player attacks in combat, do NOT narrate the outcome — request a
check the same way as any d100 check, but as an ATTACK:
- `stat`: `body` (melee/thrown) or the fiction's governing stat.
- `target`: the defender's **Defense** = `40 + (Body × 3) + armor_bonus`
  (unarmored ≈ 40 + Body×3; armor adds to it). Judge the defender's Body +
  armor from the fiction.
- include `effect_die` in the `check_request`: the size of the attacker's
  weapon — `"1d4"` (light: dagger, club), `"1d6"` (medium: sword, axe),
  `"1d8"` (heavy: greatsword, warhammer), `"1d10"` (two-handed: polearm,
  greataxe). The frontend rolls this die alongside the d100.

ROLL RESULT will carry the d100 fields PLUS `effect_roll` (the rolled
weapon die). Resolve the round from the **margin** (`total − Defense`):
- `margin < 0` — the attack misses or is turned aside; narrate the
  defender capitalizing the more negative it is.
- `margin ≥ 0` — a hit. Compute damage and apply it (below).
- open-ended high → a devastating, dramatic blow; open-ended low → the
  attacker is dangerously exposed.

DAMAGE (hybrid — weapon die + margin nudge):

`damage = effect_roll + ⌊margin / 10⌋`

The rolled weapon die is the base; a decisive hit adds +1 per full 10 of
margin (margin +22 → +2; a barely-made hit at margin +3 → +0). Apply it:
`current -= damage` (clamp at 0). Emit the defender's updated
`module_data.character_sheet.hp.current`.

DOWN AND OUT (death saves are engine-resolved — RFC-0014):

- `current` reaches 0 → set `status` to `unconscious`. The character is
  down but not gone — healing, an ally, or a death save can recover them.
- While the PLAYER character is unconscious at 0 HP, do NOT narrate their
  fate — **request a death save**: emit a `check_request` with
  `"kind": "death_save"`, `"stat": "will"`, `"target": 60`, and a `label`
  like "Cling to life". Do not resolve it, and do not set `status` or a
  death clock — the system rolls the save, computes the outcome, and writes
  both authoritatively.
- On the resolve turn you receive a **DEATH-SAVE RESULT** block stating the
  committed outcome (stabilized / still clinging on / died). NARRATE that
  outcome; never contradict it, never emit a different `status` for the
  player, and never touch the death clock — the system owns them.
- Healing an unconscious character (a normal `world_update`: raise
  `hp.current`, set `status` back to `alive`) is still yours to narrate and
  reverses the clock.
- For NPCs, resolve death yourself as the fiction demands — the death-save
  machinery is the player's. `dead` is correct on unambiguous terminal
  narration of an NPC (decapitation, a killing blow with no recovery).
- **Permadeath:** if the world is in permadeath and the player character is
  already `dead`, they cannot be revived — the system refuses any revival.
  Narrate death as final.

NPCs get hp + a Defense the same way (you set sensible numbers by their
threat level); they need not carry a full four-stat sheet. The player's
dice are the player's — resolve NPC attacks yourself as the fiction
demands, applying damage to the player's hp.

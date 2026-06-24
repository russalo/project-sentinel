PROGRESSION (milestone, player-enacted):

Characters grow through earned experience, not a point counter. There is
no XP to track — instead you PROPOSE a level-up at a genuine milestone,
and the player ENACTS it. Levels run 1 → 5 in v0.1.

PROPOSING A LEVEL-UP:

- Offer a level-up only at an earned beat: surviving a deadly encounter,
  resolving a major arc, a hard-won victory or discovery — the kind of
  experience that genuinely changes a person. Never for a trivial or
  cosmetic action. Pace it: a few significant beats per level, not every
  turn.
- When it's earned and the player is below level 5, propose it by
  emitting a `level_up` object in your `world_update` block instead of
  resolving a stat change yourself:

  ```
  "level_up": { "to_level": 2 }
  ```

  Frame it in the narrative ("the trial has tempered you — you may
  advance") and STOP there. Do NOT change the character's level or stats
  this turn. The advance is the player's to take.

THE PLAYER'S CHOICE IS SOVEREIGN:

The player's level and attributes are theirs. You may PROPOSE growth; you
may NOT decide it. Never write a character's `level` or raise a `stats`
value on your own initiative — only when the player has explicitly chosen
to, via the level-up they enact. Narrate consequences of actions freely;
do not narrate stat increases into existence.

APPLYING A LEVEL-UP (when a LEVEL-UP CHOICE is provided in the turn input):

You will receive `LEVEL-UP CHOICE: raise <stat> to level <N>`. Apply the
package in your `world_update`, exactly as chosen:

- `level` → N.
- the chosen attribute (`body`/`mind`/`heart`/`will`) +1 (cap 10) in
  `module_data.character_sheet.stats`.
- **max HP grows every level**: `module_data.character_sheet.hp.max +=
  class_HP_factor` (Warrior 8 / Rogue 6 / Cleric 6 / Mage 4 — the
  character's class factor, matching RFC-0007 combat), and bring
  `current` up by the same so the new vitality is immediately available.
- derived values follow the raised stat: if the player chose Will, the
  caster's `magic_pool.max` rises with it (`Will × 2`); if Body, note
  that HP max already grew this level by the class factor (Body itself
  doesn't separately re-derive HP here — the per-level bump is the HP
  growth).

Apply ONLY the stat the player chose. Then narrate the growth as the
fiction of becoming stronger. Do not propose another level-up the same
turn you apply one.

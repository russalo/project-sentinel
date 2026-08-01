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
do NOT decide it, and you do NOT record it. **Never write a character's
`level` or a `stats` value — ever, on any turn.** The engine commits
`level` and the chosen stat itself, from the level-up the player enacts; if
you write them the engine overrides your values and tells the player. Your
job is to PROPOSE (via `level_up`) and to NARRATE. Narrate consequences of
actions freely; do not narrate stat increases into existence.

APPLYING A LEVEL-UP (when a LEVEL-UP CHOICE is provided in the turn input):

You will receive `LEVEL-UP CHOICE: raise <stat> to level <N>`. The engine
has ALREADY committed `level` → N, the chosen attribute +1 (cap 10) in
`module_data.character_sheet.stats`, AND the derived vitality that follows —
`hp.max` (= Body × the class HP factor) and, for a caster, `magic_pool.max`
(= Will × 2) — bringing `current` up so the new vitality is immediately
available. **Do not write `level`, `stats`, `hp.max`, or `magic_pool.max`**;
the engine owns them, and if you write them it overrides your values and
tells the player. HP grows only when Body is the raised attribute; a caster's
pool only when Will is.

Your part is the fiction: narrate the growth as becoming stronger. Do not
propose another level-up the same turn one is applied.

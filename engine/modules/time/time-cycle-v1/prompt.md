TIME & REST (the day cycle, recovery between encounters):

THE CYCLE:

The world runs on a bounded day cycle. `world.timeOfDay` moves through
`dawn → morning → midday → afternoon → dusk → night`, wrapping from night
back to dawn. When it wraps past night, increment `world.day` (an integer
day counter, starting at 1). Emit the updated `world.timeOfDay` (and
`world.day` on a wrap) whenever time meaningfully advances.

WHAT ADVANCES TIME — a time-consuming action, not every turn. Travel
between places, an extended task (searching a ruin, crafting, a long
negotiation), and rest move `timeOfDay` one or more blocks; a quick
exchange inside a single scene does not. Move it deliberately — the player
should feel a day pass, not watch a clock tick each sentence.

REST (the non-magical recovery path — complements healing magic):

HP and the magic pool come back through rest, on the same small scale as
the sheet (`module_data.character_sheet.hp` and `.magic_pool`). Two kinds:

- SHORT REST (catch your breath; advances ~one `timeOfDay` block): restore
  `+⌊hp.max / 4⌋` HP (clamp at `hp.max`), and bring the magic pool up to at
  least half its max. A breather between encounters — needs a moment's
  safety, not a bed.

- LONG REST (a full night's sleep; set `timeOfDay` to `morning` and
  `world.day += 1`): restore HP to full (`current = max`) and the magic
  pool to full, and clear temporary conditions (fatigue, minor afflictions).
  A long rest needs a safe-enough place — a guarded camp, an inn, a sealed
  room. Do not grant one mid-dungeon, mid-pursuit, or with a threat bearing
  down; the fiction must allow it.

BOUNDARIES:

- Rest recovers the living. It does NOT revive the dead, and it does NOT
  replace the combat module's death-save loop for a character at 0 HP /
  unconscious — that is resolved by healing or an ally, never by waiting it
  out.
- Recovery is bounded by the rules above: no resting twice in a row to
  over-heal past a short rest's share, and no full heal without the night a
  long rest costs.
- Emit the recovered `module_data.character_sheet.hp.current` /
  `module_data.character_sheet.magic_pool.current` (and the advanced
  `world.timeOfDay` / `world.day`) in the `world_update` block, the same
  way combat emits damage.

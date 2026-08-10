CLASSES (Fantasy — four archetypes):

Every player character and any combat-capable NPC has a class. Each class has a stat priority (where its high numbers go), an HP factor (how tough it is — see combat), magic access, and one or two signature moves you can lean on in narration.

- **Warrior** — priority Body. HP factor **8** (the toughest). No magic. Signature: *Press the attack* (on a solid hit, hit even harder); *Guard* (raise their Defense for a round by fighting defensively). A frontline fighter — high Body, heavy weapons, soaks and deals damage.

- **Rogue** — priority Body then Mind. HP factor **6**. No magic. Signature: *Strike from shadow* (a large bonus when attacking unseen or with surprise); *Slip away* (favored on checks to escape, hide, or disengage). A precise, evasive skirmisher.

- **Mage** — priority Will then Mind. HP factor **4** (the frailest). Arcane magic (the spell system handles casting). Signature: high-impact spells over staying power — a Mage wins by ending things quickly, not by trading blows.

- **Cleric** — priority Will then Heart. HP factor **6**. Divine magic (the spell system handles casting and healing). Signature: support and restoration — buffs, wards, and mending alongside divine force.

Use the class to shape how a character fights and acts: a Warrior wades in, a Rogue flanks and vanishes, a Mage holds back and unleashes, a Cleric steadies the line. The HP factor is the number used to set a character's hit points (`max HP = Body × factor`); for a player character of a known class the engine maintains `hp.max` from it, so you establish it once and then leave it to the engine. Magic access (arcane / divine) names which casters can use spells; the casting mechanics live in the magic system.

ARCHETYPE (the mechanical handle — set once):

A character's `class` is free text and may be any flavor the player chose — "Proctor", "chaingang boss", "Swashbuckler", "Fighter". So each player character also carries a top-level `archetype`: the ONE of the four above that fits them best, lowercase — `warrior`, `rogue`, `mage`, or `cleric`. It is what the system reads to set their hit points and magic; the `class` stays exactly as written, for flavor.

- When you establish the player character — or on any turn where they have no `archetype` yet — pick the nearest fit from their class and fiction and emit it: `"archetype": "rogue"`. A Fighter is a warrior; a Swashbuckler or a thief is a rogue; a Sorcerer or Warlock is a mage; a Priest or Paladin-like healer is a cleric. Judge from how they actually fight and what they can do.
- Once set, it is FIXED. Never change a character's `archetype` afterward — the system will override the change and tell the player. If their story turns them into something new, narrate that; the archetype stays.
- Only ever one of the four lowercase slugs. Anything else is discarded.

Weapons and armor are read from the fiction, not a separate inventory system: a dagger is a light weapon, a longsword a heavy one, plate armor raises Defense. Judge a character's gear from what they're described carrying and wearing.

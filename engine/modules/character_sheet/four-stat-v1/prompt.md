CHARACTER SHEET (four-stat model):

Every significant character — the player and any named NPC who might act, fight, or be tested — has four attributes, each scored 1–10:

- **Body** — physical action, combat, athletics, endurance.
- **Mind** — reasoning, recall, perception, knowledge.
- **Heart** — social grace, empathy, persuasion, reading others.
- **Will** — willpower, magic, resisting fear and coercion.

A higher score means a more capable character along that axis (1 = feeble, 5 = ordinary, 8 = exceptional, 10 = peak). These four cover the whole spread of what a character attempts; map any test to the closest one (forcing a door → Body; recalling a lore-fact → Mind; swaying a guard → Heart; resisting a curse → Will).

GROUNDING STATS (establish them from the fiction, once):

- When a significant character first appears and has no stats yet, set all four in the same `world_update` that introduces them — grounded in who they are, not flat defaults. A veteran mercenary leads with Body; a court scholar with Mind; a silver-tongued envoy with Heart; a hedge-witch with Will. Ordinary folk sit around 4–5; give a stat 7+ only when the fiction earns it, and reserve 9–10 for the genuinely remarkable.
- Emit stats under the character's `module_data.character_sheet.stats` object: `{"body": N, "mind": N, "heart": N, "will": N}`.
- Once set, a character's stats are part of who they are. Do not drift them turn to turn. They change only through earned, narrated growth (a future progression system) — never as a casual edit.

Example of introducing a character with stats in the world_update:

```
"characters": [
  {
    "name": "Warden Meral Hult",
    "action": "upsert",
    "role": "npc",
    "description": "An aging survivor who keeps the watchhouse at the crater's rim.",
    "module_data": { "character_sheet": { "stats": { "body": 4, "mind": 7, "heart": 6, "will": 8 } } }
  }
]
```

Stats are the foundation other systems build on, so keep them honest and stable. (HP, defense, and magic capacity derive from these stats and come into play with the combat and magic systems — for now, just establish the four numbers.)

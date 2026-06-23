RESOLUTION (d100 open-ended):

When the outcome of a player's action is both **uncertain** and
**consequential**, do NOT simply narrate success or failure — call for a
check and let the dice decide. Trivial or safe actions (walking across a
room, recalling common knowledge, talking with no stakes) need no roll;
just narrate them.

REQUESTING A CHECK (when a roll is needed):

- Instead of resolving the action this turn, end your narrative by
  setting up the check, and emit a `check_request` object in your
  `world_update` block:

  ```
  "check_request": {
    "stat": "body",
    "target": 80,
    "label": "Force the seized portcullis",
    "prompt": "The iron is rusted fast. Forcing it will take real strength."
  }
  ```

  - `stat` — the governing attribute: `body` (physical), `mind`
    (mental), `heart` (social), or `will` (magic / resolve). Pick the one
    the action truly tests.
  - `target` — the difficulty: **Easy 40**, **Moderate 60**, **Hard 80**,
    or **Very Hard 100**. Judge by the fiction.
  - `label` — a short imperative naming the attempt (shown on the roll
    button).
  - `prompt` — one or two sentences of narrative setting up the stakes.

- Emit a `check_request` for the **player character** only. For NPC
  actions, resolve them yourself as the fiction demands — the dice are
  the player's.
- When you emit a `check_request`, do NOT also resolve the action's
  outcome this turn. The roll comes next turn; you resolve then.
- The governing character needs stats. If the player character has no
  stats yet, establish them (per the character-sheet rules) in this same
  turn so the roll has something to add.

RESOLVING A CHECK (when a ROLL RESULT is provided in the turn input):

You will receive a structured ROLL RESULT: `{stat, rolled, bonus, total,
target, margin, open_ended}`. The roll already happened — resolve the
narrative from the **margin** (`total − target`):

- **margin < 0** — failure. The more negative, the worse: −1 to −9 is a
  near miss (so close); −10 or worse is a clear, costly failure.
- **margin 0–9** — success, but barely. It works, but it's ugly, slow,
  or leaves a mark (a snapped tool, a strained muscle, lost time).
- **margin 10–29** — solid success. It works as intended.
- **margin 30+** — decisive success. It works beautifully, maybe with a
  bonus the player didn't expect.
- **`open_ended: "high"`** — a surge beyond intent: the roll exploded
  upward. Narrate an exceptional, lucky, or dramatic over-success.
- **`open_ended: "low"`** — a fumble spiral: the roll collapsed downward.
  Narrate a dramatic, compounding failure or complication.

Scale your prose to the margin — a +3 squeak reads "you just barely
manage it"; a +45 reads "you do it with contemptuous ease." Then emit the
actual state changes the outcome produces (health, location, items,
etc.) in the `world_update` block as usual. Do NOT emit another
`check_request` in the same turn you resolve one.

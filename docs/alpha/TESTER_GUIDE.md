# Sentinel Tester Guide

Welcome to the Sentinel closed alpha. This guide walks you through the
three things you'll actually do: create a world, read the screen during
play, and take a turn. It also flags the handful of surfaces that are
**cosmetic so far** — visible but not wired up yet — so you don't waste
time chasing them.

---

## Creating your world

Everything in the world-creation form shapes the playthrough that
follows. Pick what sounds interesting; you can always start another
world later from the home screen.

- **World name** — what you'll call this playthrough. Shows in the top
  bar during play and in your worlds list.
- **Character name** — who you'll play as. The DM will address you by
  this name.
- **Class** — your character's role (Warrior, Mage, Shadowmancer,
  whatever you want). Free-text; the DM will run with it.
- **Genre** — overall flavor: fantasy, sci-fi, western, horror,
  cyberpunk. Sets the world's foundation and the DM's voice.
- **Tone** — secondary modifier on the genre (gritty, humorous, dark,
  etc.). The DM will lean into it.
- **Starting region** — where you open. Each genre has four authored
  regions to choose from, each with its own established setting.
- **DM persona** — the voice running the game. Oracle is prophetic and
  detached, Chronicler is historian-precise, Cowboy Bob is laconic.
  Each fits some genres better than others.
- **DM mood** — current emotional register of the persona (neutral,
  ominous, gritty, humorous, fast-paced, lore-heavy). Adjustable
  mid-game from the persona menu in the top bar.
- **Sandbox mode** — tells the DM you prefer an open, non-linear world
  with fewer railroaded story beats.
- **World seed** — a free-text string the DM will use as additional
  inspiration for the opening. Optional.

> **Cosmetic so far on this screen:**
> - **Permadeath mode** is in the form but doesn't change gameplay
>   yet — there's no underlying death/respawn mechanism for it to make
>   permanent.
> - The seed string that appears below the form as you fill it out is a
>   randomized preview, not the seed your world actually uses. Ignore it.

When you submit, the DM generates your opening narrative and the world
loads. First load takes a few seconds.

---

## The screen during play

### Top bar (left to right)

- **Sentinel logo + world name** — confirms which world you're in.
- **Status dot** — green when the connection's healthy, red when a turn
  hit an error.
- **Feedback** (message-bubble icon) — opens the feedback form. Use
  liberally; that's the whole point of the alpha.
- **Settings** (gear icon) — opens a drawer with font size and any
  operator messages. An amber dot on the gear means there's an unread
  message.
- **Data** (database icon) — read-only browser for past sessions
  (yours and any others on this instance).
- **Seed string + share** — see "cosmetic so far" below.
- **Persona + mood** (your name + current mood) — click to change the
  DM's mood or persona mid-playthrough.
- **Mobile only:** the people icon (left) opens the world-state panel;
  the book icon (right) opens the codex.

### Left panel — World State

- **Vitals silhouette** — your character, filling with blood from the
  feet up as HP rises. The text band underneath labels your state
  (Whole / Bruised / Wounded / Bleeding / Near death / Fallen /
  Unconscious / Dead). Status overrides HP — Unconscious or Dead shows
  the pose regardless of your HP number.
  - Empty silhouette + "Zzz" above the head = unconscious.
  - Skull-and-crossbones = dead.
- **Current location, weather, time of day** — text values the DM
  updates each turn.
- **Tension meter** — 0 to 10, set by the DM as encounter pressure
  builds or releases. Calm / Off-balance / Overdue / Critical bands.
  Higher tension = more likely something significant is about to
  happen.
- **Character / Faction / Location lists** — everything the DM has
  introduced so far. Click any entry to see its full card on the right.

### Right panel — Codex and Inventory

- **Codex tab** — every character, location, and faction the DM has
  named. Cards update each turn as more is revealed.
- **Inventory tab** — items you've acquired. Same upsert model — the
  DM emits an item, it appears.

### Center — Narrative scroll

- **DM narrative** — streams in as the DM writes.
- **Delta messages** — short summaries that appear after each turn,
  noting what changed (e.g., "Russalo's location changed from X to Y;
  took 8 damage"). System chrome, not DM voice.
- **Inline action highlights** — phrases the DM marks as clickable.
  Click one to drop that text into the command bar; you can edit
  before sending.

### Bottom — Pill rails + command bar

- **DM-suggested actions** (top row, amber) — three or four
  contextual suggestions from the DM this turn. Click to drop into the
  command bar. New ones each turn; absent when the DM doesn't suggest
  any.
- **Always-available actions** (bottom row, neutral) — Look around,
  Wait, Rest, Inventory. Same four every turn, your fallback when
  you're stuck.
- **Command bar** — type anything; press Enter or click send.

### Keyboard

- **`F`** — Focus mode (hides the side panels for narrative-only
  reading). Press `F` again to exit.

> **Cosmetic so far on this screen:**
> - **Seed string in the top bar** — always displays `ABC-DEF-GHI-JKL`,
>   not the seed you actually used. The share button copies that
>   literal placeholder.
> - **"Day X of 365"** in the world panel — frozen at Day 1. The
>   day counter isn't wired to gameplay yet.
> - **DM pill colors** — all amber, regardless of the action's
>   character. The DM does mark pills with a tone (aggressive,
>   defensive, etc.), but tone-colors are deferred until we can give
>   you a clear legend.
> - **Race in the silhouette** — every fantasy race currently draws
>   the same human shape. Per-race art is on the way.

---

## Taking a turn

1. **Decide what to do.** Type into the command bar, or click any
   highlighted phrase / amber pill / always-available pill to drop
   suggested text into the bar. You can edit it before sending.
2. **Send.** Press Enter or click the send button.
3. **Watch the narrative stream.** DM text appears word-by-word.
4. **World panels update at end of turn.** Location, weather, tension,
   your vitals, codex entries — anything the DM changed lands in one
   batch when the turn's text finishes.
5. **New pills appear.** The DM suggests four-ish actions for next
   turn; always-available pills stay constant.

A few things to know:

- **Same input doesn't always produce the same outcome.** The DM is an
  LLM; identical phrasings can branch differently.
- **The DM remembers within a session.** It does not (yet) remember
  across worlds, and its memory inside a session is bounded — long
  playthroughs may lose detail from many turns ago.
- **Errors aren't fatal.** A failed turn shows `[Connection error: ...]`
  in the scroll, the status dot goes red, and you can just send again.
  Nothing is lost.
- **Refreshing is safe.** Your world loads back where it was. Sharing
  the URL (the one with `/w/<id>`) lets someone else view the same
  world if they have access to this instance.

---

## Sending feedback

Hit the message-bubble icon in the top bar any time something feels
wrong, surprising, or worth knowing about. The form auto-captures
which world, session, browser, and bundle you were in — you don't have
to remember any of that. Severity, repro steps, and your handle are
all optional. The shorter your report the more likely it'll be
triaged quickly.

This guide will be updated as more lands. If anything here doesn't
match what you're seeing, that itself is feedback worth filing.

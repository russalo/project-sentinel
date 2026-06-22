# Sentinel Tester Guide

Welcome to the Sentinel closed alpha. This guide walks you through the four
screens you'll spend time on: world creation, your worlds list, the game
screen, and the settings drawer. Each section is keyed to a screenshot —
the lettered circles in the image match the bullet list beneath it.

Some surfaces are **cosmetic so far** — visible but not wired up yet. Each
section flags them so you don't waste time chasing them or report them as
bugs.

{{toc}}

## Creating your world

![World creation form with lettered markers](guide/creation.png)

Pick what sounds interesting — you can always start another world later
from your worlds list.

- **A — World name** — what you'll call this playthrough. Shows in the top
  bar during play and in your worlds list.
- **B — Character name** — who you'll play as. The DM will address you by
  this name.
- **C — Class** — your character's role (Warrior, Mage, Shadowmancer,
  whatever you want). Free-text; the DM will run with it.
- **D — Genre** — overall flavor: fantasy, sci-fi, western, horror,
  cyberpunk. Each is fully authored with a starting setting and the DM's
  voice anchored to that world.
- **E — Tone** — secondary modifier on the genre (gritty, humorous, dark,
  etc.). The DM will lean into it.
- **F — Starting region** — where you open. Each genre has four authored
  regions to choose from, each with its own established setting.
- **G — DM persona** — the voice running the game. Oracle is prophetic and
  detached, Chronicler is historian-precise, Cowboy Bob is laconic. Each
  fits some genres better than others.
- **H — DM mood** — current emotional register of the persona (neutral,
  ominous, gritty, humorous, fast-paced, lore-heavy). Adjustable mid-game
  from the persona menu in the top bar.
- **I — Modifiers** — sandbox mode tells the DM you prefer an open,
  non-linear world with fewer railroaded story beats. (See below for
  permadeath.)
- **J — Begin journey** — submit. The DM generates your opening narrative
  and the world loads. First load takes a few seconds.
- **K — Live seed preview** — see the cosmetic-so-far note below.

> **Cosmetic so far on this screen:**
>
> - **Permadeath mode** (under modifiers) is in the form but doesn't change
>   gameplay yet — there's no underlying death/respawn mechanism for it to
>   make permanent.
> - **The seed string (K)** under the form is a randomized preview, not
>   the seed your world actually uses. Ignore it.

## Your worlds list

![Worlds list landing page with lettered markers](guide/worlds-list.png)

This is the landing page at `/` — every world you've started, plus a
button to begin a new one.

- **A — Refresh** — re-fetch the list from the server.
- **B — Training data browser** — read-only viewer for past sessions
  (yours and any others on this instance).
- **C — Begin a new world** — opens the world-creation form.
- **D — Your existing worlds** — each row is a world you've played. Click
  to resume; the trash icon (per-row) deletes that world.

## The screen during play

![Game screen in progress with lettered markers](guide/game.png)

This is what you see at `/w/<world-id>` — the full game shell with the
top bar, your character + world state on the left, codex + inventory on
the right, and the narrative scroll + pill rails + command bar in the
middle/bottom.

### Top bar (left to right)

- **A — World name** — confirms which world you're in.
- **B — Status indicator** — Ready (green dot), Streaming (amber, while
  the DM is writing), or Connection error (red, after a failed turn).
- **C — Feedback** — opens the feedback form. Use liberally; that's the
  whole point of the alpha.
- **D — Tester guide** — this doc. One tap to re-read any time.
- **E — Settings** — opens a drawer with font size and any operator
  messages. An amber dot on the gear means there's an unread message.
- **F — Training data browser** — read-only viewer for past sessions.
- **G — Persona + mood** — click to change the DM's mood or swap the
  persona mid-playthrough.

### Left panel — your character & world state

- **H — Vitality silhouette + band** — your character, filling with
  blood from the feet up as HP rises. The text band underneath labels
  your state (Whole / Bruised / Wounded / Bleeding / Near death / Fallen
  / Unconscious / Dead). Status overrides HP — Unconscious or Dead shows
  the pose regardless of the HP number. Empty silhouette with "Zzz"
  above the head = unconscious. Skull-and-crossbones = dead.
- **I — Day counter** — see the cosmetic-so-far note below.
- **J — Tension meter** — 0 to 10, set by the DM as encounter pressure
  builds or releases. Calm / Off-balance / Overdue / Critical bands.
  Higher tension = more likely something significant is about to happen.

The current location, weather, and time of day also appear in this
panel — the DM updates them each turn alongside the other world state.

### Right panel — codex & inventory

- **K — Codex tab** — every character, location, and faction the DM has
  named. Cards update each turn as more is revealed.
- **L — Inventory tab** — items you've acquired. Same upsert model: the
  DM emits an item, it appears.

### Action pills + command bar

- **M — DM-suggested action pills** (amber, top row) — three or four
  contextual suggestions from the DM this turn. Click to drop into the
  command bar. New ones each turn; absent when the DM doesn't suggest
  any. Phrases highlighted *inline* inside the narrative are the same
  thing — click either surface to type that label.
- **N — Always-available action pills** (neutral, bottom row) — Look
  around, Wait, Rest, Inventory. Same four every turn, your fallback
  when you're stuck.
- **O — Command bar** — type anything; press Enter to send.
- **P — Send** — submit your action.

Press **`F`** to toggle Focus mode (hides the side panels for
narrative-only reading).

> **Cosmetic so far on this screen:**
>
> - **Day counter (I)** is frozen at Day 1 — the counter isn't wired to
>   gameplay yet.
> - **The seed string under the top bar** (not lettered above) always
>   displays `ABC-DEF-GHI-JKL`, not the seed you actually used. The
>   share button copies that literal placeholder.
> - **DM pill colors** are all amber, regardless of the action's
>   character. The DM does mark pills with a tone (aggressive,
>   defensive, etc.), but tone-colors are deferred until we can give
>   you a clear legend.
> - **Race in the silhouette** — every fantasy race currently draws
>   the same human shape. Per-race art is on the way.

## The settings drawer

![Settings drawer open with lettered markers](guide/settings.png)

Opened by tapping the gear icon in the top bar.

- **A — Close** — close the drawer (or press Escape).
- **B — Decrease narrative font size** — affects the DM narrative text
  only; chrome stays at default size.
- **C — Increase narrative font size**.
- **D — Operator messages** — broadcast announcements from the alpha
  team. The amber dot on the gear in the top bar lights when there's
  an unread message; it clears the moment the drawer opens.

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
- **Errors aren't fatal.** A failed turn shows `[Connection error: …]`
  in the scroll, the status dot goes red, and you can just send again.
  Nothing is lost.
- **Refreshing is safe.** Your world loads back where it was. Sharing
  the URL (the one with `/w/<id>`) lets someone else view the same
  world if they have access to this instance.

## Sending feedback

Hit the message-bubble icon in the top bar any time something feels
wrong, surprising, or worth knowing about. The form auto-captures
which world, session, browser, and bundle you were in — you don't have
to remember any of that. Severity, repro steps, and your handle are
all optional. The shorter your report the more likely it'll be
triaged quickly.

This guide is updated as more lands. If anything here doesn't match
what you're seeing, that itself is feedback worth filing.

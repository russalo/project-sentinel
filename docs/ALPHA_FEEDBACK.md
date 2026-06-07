# Project Sentinel — Alpha Feedback Log

All feedback from the closed-alpha cohort, organized by category and dated.
This is the **capture surface** — items land here first, then graduate into
`docs/BACKLOG.md` when they're ripe for a triaged work entry. Daily patch
windows and roadmap decisions are planned off this file.

Closed alpha went live **2026-06-07** at <https://sentinel.russalo.com/alpha/>.

## How to use

- **Adding feedback:** append a one-line item under the appropriate section with
  a `[YYYY-MM-DD, source]` prefix. `source` = tester name, "internal smoke",
  "code-review bot", "operator dashboard," or whatever surfaced it.
- **Graduation:** when an item grows substantial enough for a triaged work
  entry, write it up in [`BACKLOG.md`](./BACKLOG.md) and add `→ BACKLOG` (with
  a brief locator if needed) at the end of the line here.
- **Resolution:** when an item ships, add `→ PR #N` to its line. Leave the
  item in place as historical record (don't delete — useful for patch-note
  retrospectives and pattern-spotting).
- **Don't duplicate:** if a tester reports something already captured, just
  note them as an additional `source` (e.g., `[2026-06-07, internal smoke; 2026-06-08, tester-X]`).

## Categories

- [**Bugs**](#bugs) — defects in shipped behavior; UI broken, data wrong, error visible
- [**UI/UX Improvements**](#uiux-improvements) — works but feels rough; font, layout, animation, polish
- [**General Feedback**](#general-feedback) — subjective impressions; DM tone, narrative quality, "feel"
- [**Future Features**](#future-features) — new capabilities beyond polish; persistence, sound, etc.

Cross-link: [`BACKLOG.md`](./BACKLOG.md) for triaged work entries; [`ROADMAP.md`](./ROADMAP.md) for near-term planning; [`VISION.md`](./VISION.md) for direction-level items.

---

## Bugs

- [2026-06-07, internal smoke] DM-narrative markdown emphasis (`*x*` / `**x**` / `***x***`) renders on the live streamBuffer (visible during streaming) but disappears once the turn commits to messages[]. Bold not visible anywhere. → BACKLOG ("DM-narrative markdown emphasis renders ONLY on the live streamBuffer")
- [2026-06-07, internal smoke] iOS Chrome/Safari `:hover` background on action pills stays lit after tap until the next interaction elsewhere. Cosmetic only. → BACKLOG ("iOS stuck `:hover` on action pills after tap")
- [2026-06-07, internal smoke] SystemLog doesn't persist across browser refresh — `chatStore` is in-memory and `useWorldHydration` doesn't reconstruct system-log entries from the per-turn `world_updates` history. Refresh = empty system log until new turns happen. (Not yet a BACKLOG entry; capture for triage.)

## UI/UX Improvements

- [2026-06-07, tester feedback] Narrative font is too small for comfortable reading on iOS. Want a player-adjustable size. Settings-drawer shape decided. → BACKLOG ("Player font-size control via Settings drawer") — targeted for Monday 2026-06-08 patch window
- [2026-06-07, internal smoke] DM action-pill tone-rainbow dropped for v1 because color meaning isn't conveyed to the player. Re-enable with a legend when we have a teaching moment. → BACKLOG ("Re-enable DM action-pill tones with a player-visible legend")
- [2026-06-07, internal smoke] Long action-button text glued the trailing `?` onto its own line; coalesced trailing punctuation onto the action's display. ✅ Shipped → PR #113

## General Feedback

(none yet — gather as testers play)

## Future Features

(none yet — gather as themes emerge)

---

## Triage discipline

When working through this file before a patch window:

1. **Cluster.** Look for items that touch the same render path, store, or
   subsystem — those bundle into a single PR.
2. **Promote.** Move ripe items (clear repro, clear fix, fits the next patch
   window) to a BACKLOG entry. Keep the line here with the cross-link.
3. **Defer.** Items lacking repro or scope clarity stay here; revisit when
   more testers hit them.
4. **Drop.** Items that turn out to be expected behavior get a `→ EXPECTED`
   note rather than a delete (so future readers don't re-report).

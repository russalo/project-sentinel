# RFC 0019 — DM archetype mapping (ADR-0004 Slice 1c)

**Status:** Implemented
**Date:** 2026-08-10
**Author:** Russell Pfister; Claude Code
**Implements:** ADR-0004 (state truthfulness) Slice 1c; `docs/BACKLOG.md` → "ADR-0004 Slice 1c — DM archetype mapping for free-text classes"
**Closes:** the fail-safe gap left by [RFC-0018](0018-progression-derived-maxes.md)

---

## Context

RFC-0018 made `hp.max` (= Body × class factor) and `magic_pool.max` (= Will × 2)
engine-authoritative — but only for a PC whose class resolves to a rules-data key.
A PC's `class` is **free text from the client** (`body.player_character_class` →
`IntroInput.player_class`, rendered into the intro prompt as "a {player_class}"),
so the live worlds' PCs — `Sal` = "Proctor", `Chez` = "chaingang boss" — resolved
to nothing and kept DM-authored maxes. That fail-safe was correct (never guess a
factor) but left most characters outside engine authority.

## Design

A PC now carries a top-level **`archetype`**: a lowercase slug naming one of the
bound class module's archetypes (`warrior` / `rogue` / `mage` / `cleric`). `class`
is untouched — it stays the character's flavor; `archetype` is the mechanical
handle the engine reads.

**The DM classifies.** The class module's prompt instructs the DM to set the
nearest-fitting archetype when it establishes the PC *or on any turn where one is
missing* — so existing worlds get classified on their next turn rather than needing
a migration. This is the same pattern the magic module already uses, where the DM
maps fiction onto a bounded enum (`binding` / `realms`).

**The engine pins it — write-once.** `archetype` is *conditionally* writable (legal
once, at establishment), which per ADR-0004's key lesson rules out a write-boundary
guard: the authorized and hallucinated writes are byte-identical ops. So it takes
mechanism **(a)**, dispatch-recompute-and-inject, alongside `level`/`stats`. In
`enforce_progression`:

- a valid **stored** archetype is forced onto every PC op — a DM re-map is
  overridden with a player notice. This matters because a re-map is a **free HP
  lever**: `rogue` (×6) → `warrior` (×8) would inflate max HP by a third.
- with none stored, a DM-emitted value **establishes** it — but only if it names a
  real archetype. An invalid slug (e.g. `paladin`) is **dropped, not stored**, so
  the PC stays unclassified and the next turn can retry; the engine never persists
  a slug its rules-data can't resolve.
- a **garbage stored** slug is treated as absent, so a world holding a legacy value
  can be re-established rather than pinned to nonsense forever (self-healing).

**Resolution order.** `resolve_class_rules` now takes the PC and prefers
`archetype`, falling back to `class` — so nothing regresses (a Fantasy "Warrior"
already worked and still does), and "Proctor" + `cleric` now resolves to
`{hp_factor: 6, magic: "divine"}`.

## Implementation

- **`engine/class_rules.py`** — `resolve_class_rules(modules, character)`
  (archetype-first, class fallback, bare string still accepted for pre-RFC-0019
  callers); `archetypes(modules)` returns the bound module's valid slugs;
  `canonical_archetype(modules, value)` canonicalizes one. All fail-safe, never raise.
- **`engine/progression.py`** — `enforce_progression` gains `archetypes` (the valid
  set, so the module stays pure) and pins `archetype` per the rules above, with
  `_canonical_archetype` as the pure matcher and a new player notice.
- **`backend/routes/stream.py`** — passes the PC dict to the resolver and the
  archetype set to enforcement; the RFC-0018 vitality verdict flows unchanged.
- **`engine/modules/class/four-class-fantasy-v1/prompt.md`** — the ARCHETYPE block:
  what it is, when to set it, mapping guidance (Fighter → warrior, Swashbuckler →
  rogue, Sorcerer → mage, Priest → cleric), and that it is fixed once set.

An empty archetype set makes the pin **inert**, so a world whose class module ships
no rules-data behaves exactly as it did before this RFC.

## Testing

`tests/engine/test_archetype.py` (14) — resolution (archetype wins, invalid falls
back to class, neither → None, bare string, canonicalization, inert set) and the pin
(first valid accepted + canonicalized, invalid dropped, stored forced over a re-map
with notice, forced when the op omits it, matching re-map not flagged, garbage
re-establishable, `class` never touched). Route-level in
`tests/backend/test_progression_maxes_stream.py` — a "Proctor" pinned to `cleric`
gets `hp.max` = 36 and a caster pool through the real dispatch; a mid-session re-map
to `warrior` is overridden and surfaced to the player.

## Out of Scope

- **Entity-identity hardening.** This slice uses the existing
  `find_player_character`; if an imposter entity shadows the PC, the pin follows the
  shadowed PC. That hole is **pre-existing and unchanged here** — see the BACKLOG
  entity-identity item, whose stable-identity resolver this will inherit.
- A player-facing archetype picker (considered: more deterministic, but needs a
  create-flow/UI change and would only help *new* worlds). Kept as the fallback if
  DM classification proves unreliable in play.
- NPC archetypes; a retrofit migration script (lazy classification covers it).

## Cross-links

ADR-0004; RFC-0018 (the fail-safe this closes), RFC-0017, RFC-0007/0008 (the
factors), ADR-0005 (module rules-data). `docs/BACKLOG.md` → Slice 1c.

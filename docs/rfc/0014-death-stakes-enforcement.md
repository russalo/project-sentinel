# RFC 0014 — Death-stakes enforcement (`combat` subsystem)

**Status:** Accepted
**Date:** 2026-07-02
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005 `combat` subsystem; the death-stakes next-slice
committed in `docs/CORE_SYSTEMS.md`. Moves the death ladder
(0 HP → `unconscious` → death saves → `dead`) and the `permadeath` flag from
prompt-honored to engine-enforced.
**Supersedes:** — (extends `core/hp-pool-v1`; does not replace it)

---

## Where this sits

Under ADR-0005, in the `combat` subsystem, on top of RFC-0007 (`hp-pool-v1`,
the HP pool + the death ladder as prompt text) and RFC-0006 (`d100-open-v1`,
the `check_request` → `RollResult` roll path this reuses). It is the first
mechanical layer that gives ADR-0004 (state truthfulness) real teeth: the
engine, not the DM, commits the outcome of a specific typed check.

## Context

Today the whole death pipeline is **prompt-honored**.
`engine/modules/combat/hp-pool-v1/prompt.md` asks the DM to run a death save (a
`will` check vs Moderate 60; three failures → `dead`); `base-v1` defines the
status enum; `permadeath` is a **label-only** line in `engine/types.py` /
`engine/agents/dm.py` that gates nothing and is not even persisted on the
session. The DM can forget the clock, invent the outcome, or revive a
"permadead" character, and nothing stops it.

The deeper fact (verified): the DM interprets **every** check's margin and emits
the resulting state writes — the engine never decides a check's consequence.
RFC-0006 made the *roll* real (client-rolled, server-validated); the *outcome*
is still the DM's to narrate. So "enforce death saves" is not "roll them
server-side" — the roll is already real. It is the first case where **the
engine computes a check's outcome and commits it**, deliberately taken here
because death is the highest-stakes moment and the ambient surfaces (Vitals
silhouette, tension) already imply it.

## Proposal

Six seams, in dependency order:

1. **Typed check.** Add `kind` to the `check_request` shape (DM-authored;
   default `"skill"`, `"death_save"` for a death save) and to `RollResult`
   (`backend/schemas.py`, pattern-constrained `^(skill|death_save)$` — it is
   client-controlled and influences engine logic, so it is bounded like
   `effect_die`). The frontend echoes the request's `kind` back on the resolve
   turn. A death save is emitted for the player character while
   `status == unconscious`, surfaced on the existing `CheckRequestRail`
   (labeled "Cling to life").

2. **Server-recomputed margin (tamper-proof outcome).** `RollResult.total` /
   `margin` are client-computed; only `rolled` is server-validated (1–100). An
   ordinary check tolerates that. A death save must not: keying the outcome on
   a client margin lets a crafted client send `margin ≥ 0` forever and never
   die. For `kind == "death_save"` the engine **recomputes** the margin from
   the validated `rolled` + the server-known `will` stat + the fixed target
   (Moderate 60), ignoring the client `total`/`margin`. The roll's randomness
   (the trust anchor) is preserved; the consequence is not client-forgeable.

3. **Engine-authoritative outcome (Q1 = 2a).** On a resolve turn where
   `kind == "death_save"`, a pure engine function computes the result from the
   recomputed margin + the stored clock — `margin < 0` → increment the clock;
   third failure → `dead`; `margin ≥ 0` → stabilize (clock reset, stays
   `unconscious`) — and the backend **injects those state writes
   authoritatively**, overriding any conflicting DM-emitted status/clock. The
   DM receives a constrained ROLL RESULT block stating the committed outcome
   and is told to *narrate, not decide*.

4. **Death clock in state.** Add `death_saves_failed` (int 0–3) to
   `module_data.combat`, with a `combat` module `schema.json` (combat has none
   today) as the contract of record. The clock lives in world state, not the
   DM's context.

5. **`permadeath` persisted + load-bearing (Q2 = engine at dispatch-time).**
   Persist `permadeath` on the `Session` (it is dropped today). The revival
   gate is a **pure engine function** invoked by the backend orchestration just
   before `apply_world_update` (not inside `apply_world_update`, which is a thin
   fs-manager HTTP client with no world state, and not in fs-manager, which
   doesn't know `permadeath`): when the world's `permadeath` is set and a
   character's **stored** `status == dead`, any update that would revive it is
   dropped and fed back to the DM as a rejection — never silently honored. The
   status check is an **allowlist** (only `dead` may stand — anything else,
   including prose-y statuses like `stable`/`conscious`, is refused), the
   HP-restore drop covers flat `health` + `hp.current`/`hp.max` + a death-clock
   reset, and a **renamed/clone revival** (an entities-update claiming
   `role: "player"` under a new name) is caught too — all hardened from the PR
   review (see the review note).

6. **Prompt.** Rewrite the `hp-pool-v1` death-save section: at 0 HP the DM
   *requests* a `death_save` check and, on resolve, *narrates* the
   engine-committed outcome; it never invents the clock or the status.

## Open Questions

_All resolved at acceptance:_

- **Q1 — outcome authority:** **2a** — the engine writes the outcome; the DM
  narrates. (Approved 2026-07-02.)
- **Q2 — permadeath gate placement:** **engine at dispatch-time** — a pure
  engine function called by the backend orchestration (refined from "inside
  `apply_world_update`" once that was confirmed to be a thin HTTP client).
- **Q3 — NPC deaths:** stay DM-narrated (`check_request` is player-only by
  RFC-0006). Player death is the stake that matters for v1.
- **Q4 — rolling while down:** player-tapped "Cling to life" roll (house rule:
  reveals are player-paced), not auto-advance.

## Acceptance Criteria

- A death save is a typed `check_request`, rolled on the existing rail.
- The engine recomputes the death-save margin server-side; a crafted client
  `margin` cannot change the outcome (test).
- On resolve the engine sets `death_saves_failed` / `status` from the margin; a
  test proves the DM cannot override a rolled `dead`.
- `permadeath` is persisted on the session; `permadeath` + stored `dead`
  rejects a revival update with DM-visible feedback (test).
- `combat/schema.json` validates `death_saves_failed`.
- The `hp-pool-v1` prompt has the DM narrate — not decide — a death-save
  outcome.

## Out of Scope

- Death's **world/session consequences** (session end-state, in-world memorial,
  what a dead PC does to an in-flight world) — deferred follow-up per
  CORE_SYSTEMS.
- NPC death-save mechanization.
- Multi-PC / party death (one-player-per-world holds).
- Composing module `schema.json` fragments into apply-time validation — they
  remain declarative contracts of record today; enforcement of the clock is via
  engine authority (seam 3), not schema validation.

## Cross-links

`docs/CORE_SYSTEMS.md` (death-stakes slice) · ADR-0005 (subsystem modularity) ·
ADR-0004 (state truthfulness — this is its first enforced instance) · RFC-0006
(resolution / the roll path reused) · RFC-0007 (`hp-pool-v1`, the ladder
enforced).

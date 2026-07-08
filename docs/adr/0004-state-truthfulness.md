# ADR 0004 — State truthfulness: the engine owns mechanically-determined state

**Status:** Accepted
**Date:** 2026-07-08
**Deciders:** Russell Pfister; Claude Code

---

## Context

Sentinel's core promise is a persistent, coherent world. The structural threat
to that coherence is the DM LLM itself: it generates **both** the narrative and
the `<world_update>` payload that mutates canonical state (ADR-0001). Nothing in
the architecture, on its own, stops the DM from narrating *"you shrug off the
killing blow"* and then emitting `status: alive` on a turn where the dice already
said the character is dead. A hallucinated — or, on a crafted client, a
deliberately forged — state override is written to the source of truth and
committed to the git audit trail as if it were fact.

Three enforcement layers have emerged **organically, subsystem by subsystem**,
without a ratified principle tying them together:

- The number **0004 was reserved** for this decision when RFC-0007 (`hp-pool-v1`)
  and RFC-0009 (progression) named "state truthfulness" as a deferred lane and
  pointed the hard-enforcement work at it.
- **RFC-0014 (death-stakes, landed #172) is the first subsystem to enforce it
  mechanically.** On a death-save resolve turn the engine *recomputes* the margin
  from the trusted `rolled` value + the server-known `will` stat + a fixed target
  (ignoring the client-supplied `total`/`margin`), a **pure engine function**
  computes the outcome, and the **backend injects those state writes
  authoritatively, overriding any conflicting DM-emitted status/clock**. The DM
  receives a constrained ROLL RESULT block and is told to *narrate, not decide*.
  Its own framing: "the first mechanical layer that gives ADR-0004 real teeth."
- The **fs-manager protected-field guard** (red-team #1, PR #182) enforces a
  write-boundary slice: the identity fields (`unique_id`, `world_seed`,
  `namespace`, `created_at`, `canon`, `core_faction_id`) are immutable to any
  LLM-authored payload — a write that sets one is rejected (403) and fed back,
  never applied.
- **Everywhere else is still prompt-honored only.** RFC-0009's `level`/`stats`
  "sovereignty wall" is enforced by asking the DM nicely; most of combat, all of
  magic, weather, faction, and time are narrative-trusted. RFC-0009 explicitly
  defers its hard guard to "the ADR-0004 lane — number reserved."

The consequence of leaving this un-ratified: every new subsystem re-decides *how
much* to enforce and *where* the enforcement lives (engine? backend? fs-manager?),
and the answer gets reconstructed from RFC-0014's chat log each time. That is
exactly the kind of cross-cutting, hard-to-reverse, "why is it this way" decision
an ADR exists to fix in place.

## Decision drivers

- **Player trust / the minimum-viable-structure invariant.** A rolled outcome
  (a death, a failed check) must be binding, or the dice are theater. These are
  the walls that make an autonomous world *coherent* rather than an improv toy.
- **Determinism + auditability (ADR-0001).** Canonical state is the source of
  truth and every write is a git commit. A DM override that contradicts a
  committed mechanical fact corrupts the audit trail — it records a lie as canon.
- **The engine boundary (ADR-0005 + the Inference/Infrastructure split).** The
  engine package is pure (no filesystem, no world state). Enforcement that needs
  world state or a trusted secret must live where those live — the backend
  orchestration and fs-manager — never inside the engine agents, and never inside
  `apply_world_update` (a thin fs-manager HTTP client with no world state).
- **Narrative freedom.** The DM must stay fully free to author everything that is
  *not* a committed mechanical fact. Over-enforcement turns Sentinel into a rules
  engine with a story skin and kills the emergent-worlds thesis.
- **Cost of enforcement.** Each hardened field or outcome costs engine + dispatch
  + schema + test code. Enforce where the stakes justify it; do not gold-plate
  cosmetic state.

## Options considered

**Option A — Prompt-honored only (status quo before RFC-0014).**
The DM is instructed not to lie; no structural guard on any state.
- *Pros:* zero enforcement code; maximal DM freedom.
- *Cons:* a hallucination or a crafted client silently corrupts canonical state;
  the dice are non-binding; ADR-0001's audit trail can commit a lie as fact.
- *Verdict:* rejected — RFC-0014 already walked away from it for the highest-stakes
  outcome (death), and the reasoning generalizes.

**Option B — Full engine-authoritative state machine.**
The engine owns a complete typed world model; the DM only narrates over it.
- *Pros:* total truthfulness; nothing the DM says can drift state.
- *Cons:* enormous surface — every entity attribute becomes an engine-owned typed
  field; it makes Sentinel a rules engine with a narrative skin, fights the
  "DM is the world-author" design, and forecloses emergent, DM-invented world
  content (the whole point). Wrong shape, not just heavy.
- *Verdict:* rejected.

**Option C — Layered, per-field authority (chosen).**
Classify state into **engine-owned** (mechanically determined) and
**narrative-owned** (DM-authored). Enforce engine-owned state with whichever
layer fits, incrementally, per subsystem.
- *Pros:* matches what is already shipping (RFC-0014 + the protected-field guard);
  bounds enforcement cost to where stakes justify it; preserves narrative freedom;
  gives every subsystem one contract + one placement rule.
- *Cons:* requires a per-subsystem judgment of which fields are engine-owned and
  which layer enforces them; un-hardened mechanics stay prompt-honored until
  graduated (a known, bounded, tracked gap).
- *Verdict:* **chosen.**

## Decision

Adopt **Option C**. **State truthfulness is a ratified invariant: the engine — not
the DM — is the source of truth for mechanically-determined state, and the DM
cannot override a committed mechanical outcome.**

Concretely:

1. **Ownership classification.** Each subsystem (per ADR-0005) declares which
   state it *mechanically owns* — values it determines deterministically from
   typed inputs + server-known state (a death outcome, an HP floor at 0, a `level`
   gained only through an enacted advancement, a stat set only by an enacted pick)
   — and which **protected/identity fields** are immutable to LLM payloads.
   Everything not so declared is **narrative-owned** and stays fully the DM's.

2. **Two enforcement mechanisms for engine-owned state:**
   - **(a) Dispatch-recompute-and-inject** — for typed outcomes that depend on
     server-known state plus a trust anchor (a validated roll). A **pure engine
     function** computes the outcome; the client-controlled inputs are bounded,
     and the *consequential quantity is server-recomputed from the trust anchor +
     server-known state, never a client-supplied result*; the **backend
     orchestration injects the resulting state write authoritatively at dispatch
     time**, overriding any conflicting DM-emitted value. (The RFC-0014 death-save
     pattern, generalized.)
   - **(b) Write-boundary guard** — for fields that are simply immutable to the
     DM. The schema gate + fs-manager `check_protected_fields` **reject** the write
     and feed the rejection back as control flow; the value is never applied. (The
     red-team #1 protected-field pattern, generalized to mechanically-owned fields.)

3. **"Narrate, not decide."** For any committed mechanical outcome the DM receives
   a constrained result block stating the committed value and is instructed to
   narrate it, not choose it. This is a shared prompt convention across subsystems.

4. **Layered + incremental.** Prompt instruction is the **baseline** every
   subsystem starts at. A field/outcome **graduates** to (a) or (b) when the stakes
   justify the code. *Un-hardened ≠ un-owned* — the principle holds for all
   engine-owned state; only the enforcement strength varies, and each subsystem's
   current strength is tracked.

**Placement contract (load-bearing, ratifying what RFC-0014 established):**
the **engine computes** (pure, no IO); the **backend orchestration injects**
engine-owned writes at dispatch time (before `apply_world_update`); **fs-manager
guards** the write boundary. Enforcement never lives *inside* `apply_world_update`
(no world state there) and never inside an engine agent (no IO/secret there).

## Rationale

RFC-0014 did not invent a one-off; it discovered the general shape and proved it on
the highest-stakes outcome. The recompute-from-the-trust-anchor move (trust only
the roll's randomness; recompute the consequence server-side) is what makes an
outcome both *fair* (real dice) and *unforgeable* (no client-supplied result). The
red-team #1 work independently arrived at the write-boundary half for identity
fields. Ratifying the union — plus the placement contract — means progression,
magic, and future subsystems inherit one answer instead of re-deriving it, and the
`docs/BACKLOG.md` Fantasy-flagship core-systems initiative gets a spine.

Option B is the seductive wrong turn: "just make the engine own everything" sounds
like more truth, but it deletes the reason Sentinel exists (a DM authoring an
emergent world). Option C keeps the engine's authority *scoped to what is
mechanically determined* and leaves the rest to narrative — which is the actual
invariant worth defending.

## Consequences

**Positive**
- Dice and typed mechanics become binding; a player's rolled death (or survival)
  sticks regardless of DM hallucination or a crafted client.
- The ADR-0001 audit trail cannot commit a hallucinated override of a mechanical
  fact.
- Every subsystem inherits one contract + one placement rule; new mechanics are
  cheaper and more consistent to harden.
- The emergent-worlds thesis survives — narrative-owned state stays fully the DM's.

**Negative**
- Each hardened outcome costs engine + dispatch + schema + test code (bounded by
  the "graduate only when stakes justify" rule).
- The DM's freedom is deliberately bounded on mechanical facts.
- Requires an explicit, sometimes-debatable per-subsystem judgment of which fields
  are engine-owned.

**Neutral**
- The engine stays pure; enforcement is intentionally spread across backend
  orchestration + fs-manager.
- Not-yet-hardened mechanics remain prompt-honored — a known, tracked gap per
  subsystem, not a violation of the principle.

## Implementation implications

- **The reserved lane is open.** RFC-0009's progression hard-enforcement — a
  dispatch guard so the DM cannot write `level`/`stats` outside an enacted
  advancement — **landed as RFC-0017 (Slice 1)**. Note the mechanism: this is
  **(a) recompute-and-inject**, NOT (b) — RFC-0017's code map showed a write-boundary
  guard structurally can't do it (the authorized and attack writes are byte-identical
  `world_update` ops, `stats` is nested where the top-level check can't see it, and
  the authorized delta needs `body.level_up` context fs-manager lacks). `hp`/`magic`
  authority is the deferred Slice 1b.
- **Per-subsystem "engine-owned fields" declaration** extends the ADR-0005 module
  contract (the `combat` module's `schema.json`, introduced by RFC-0014, is the
  first instance — generalize it).
- **The write-boundary guard (b) is for genuinely *immutable* fields** — the
  identity set fs-manager `check_protected_fields` already covers, and (later) the
  authored-but-unenforced entity-schema *shape* validation (RFC-0006 OQ1). Fields
  that are engine-owned but *conditionally* writable (a `level` rises on an enacted
  level-up) can't be enforced there — a payload-only check can't tell an authorized
  write from a hallucinated one — so they take mechanism (a) instead (RFC-0017).
- **Shared "narrate, not decide" prompt convention** for committed-outcome blocks,
  factored so subsystems reuse it.
- The **Fantasy-flagship core-systems** initiative (`docs/BACKLOG.md`) inherits
  this contract for magic, healing, faction, and time as those harden.

## References

- ADR-0001 (canonical `data/` state), ADR-0005 (subsystem modularity + the module
  contract this extends).
- RFC-0006 (`d100-open-v1` check loop), RFC-0007 (`hp-pool-v1` HP pool + death
  ladder), RFC-0009 (progression sovereignty wall — the deferred hard-enforcement
  lane), RFC-0013 (encounter), RFC-0014 (death-stakes enforcement — the anchor;
  the recompute-and-inject pattern this generalizes).
- PR #182 (red-team #1 — schema-gate + fs-manager `check_protected_fields`, the
  write-boundary half).
- `CLAUDE.md` hunt list: "determinism where it's asserted", "schema-gate bypass",
  "malformed-LLM-output intolerance".

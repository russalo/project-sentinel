# ADR 0006 — Retrieval substrate (vendor trellis via poggio; retire ChromaDB-RAG)

**Status:** Accepted
**Date:** 2026-07-01
**Deciders:** Russell Pfister (accepted RFC-0011; blessed the sessions-JSON corpus + the `poggio` spinoff, 2026-06-30/07-01); Claude (design + probe, 2026-06-29 → 07-01)
**Supersedes:** — (no prior ADR; redirects the ChromaDB-vector-RAG plan in the BACKLOG "Lorekeeper" item)
**Implementation:** RFC-0011 Slice 1 (the fold) lands this ADR's decision — dormant, gated, fail-open.

---

## Context

The DM improvises canon. When a player asks "what did the innkeeper tell me
about the millstones?", the DM either remembers (if it's in the recent-turns
window) or invents an answer that the next session contradicts. The world
*has* the answer on disk (`data/state` + `data/lore/.../sessions/*.json`); it
just isn't retrieved into the DM's context. Sentinel needs a **retrieval step
in the turn loop** that surfaces relevant established canon so the DM cites it.

The original plan (early BACKLOG) was **ChromaDB vector RAG**. Two Sentinel
invariants fight that choice:

1. **Determinism.** Sentinel asserts deterministic behavior where it can
   (tracer-soak tests, `rules_fingerprint`, etc.). Vector ANN retrieval is
   nondeterministic across index builds / library versions — the same query
   can return different neighbors.
2. **Citable provenance.** For the DM to *cite* canon (not just be nudged by
   it), each hit must carry a stable, auditable source. Vector RAG returns
   embeddings-nearest chunks with no first-class provenance.

A probe (2026-06-29) proved **`trellis`** — a deterministic md/JSONL → graph +
lexical(bm25)/graph query engine — fits where vector RAG fights: byte-
deterministic, provenance (`@source`) first-class on every node, per-world
scoping via corpus-as-folder. It was then built into **`poggio`** (a dedicated-
session spinoff, `russalo/poggio`, vendoring trellis) — the per-world lore-
retrieval tool: adapter (`data/` → trellis graph) + recipes + a query CLI.
Poggio v0.1.0 shipped and was verified live against a real Sentinel world
(2026-07-01). ChromaDB is currently `stopped` in the stack.

## Decision

**Adopt `trellis` (via the `poggio` tool) as Sentinel's lore-retrieval
substrate. Retire the ChromaDB-vector-RAG plan.**

- **Poggio is external** (a subprocess reading a world's `data/`). Sentinel
  owns the corpus *format* (a soft-contract — see
  `project_poggio_session_json_softcontract`); poggio owns the adapter +
  recipes + query surface.
- **The fold is Sentinel's** (RFC-0011): the backend calls poggio and injects
  ranked, provenance-carrying hits into the DM prompt before the DM call. The
  **engine stays pure** — retrieval IO lives in the backend
  (`backend/state/lorekeeper.py`); the engine only renders the hits
  (`engine/agents/lorekeeper.py`).
- **Invariants preserved:** per-world isolation (query scoped to the world's
  folder, never across worlds), determinism (trellis is deterministic;
  rebuild-on-query), read-only over lore (retrieval never mutates `data/`).
- **Safety:** the fold is opt-in (`SENTINEL_LOREKEEPER_ENABLED`, dormant by
  default) and **fail-open** (a missing/broken poggio degrades to no canon,
  never breaks a turn).

## Consequences

- **+** Deterministic, citable retrieval — the DM can quote canon with a
  source instead of improvising it. Closes the "how do I know what we
  established?" gap the recent-turns window can't.
- **+** ChromaDB leaves the critical path (already stopped) — no vector store,
  no embedding pipeline, no ANN nondeterminism to defend.
- **−** A **runtime dependency** on the `trellis` + `poggio` binaries in the
  Sentinel deploy env when armed (systemd/cutover). Mitigated: gated + fail-
  open + dormant by default; arming is a deliberate, later step.
- **−** A **soft-contract** coupling: poggio reads a named subset of the
  session JSON. Changes to that subset route through Russell (managed like the
  file-observer `CHATLOG_SPEAKER_LABEL_RE` contract).
- The `apply_world_update` schema already reserved a `lorekeeper` role; the
  **write-side** lorekeeper (promoting prose entities into canon) is the
  Entity Sweeper's lane, separate from this read-side fold.

## Rejected alternatives

- **ChromaDB vector RAG** — nondeterministic, provenance-poor; fights the
  determinism + citation invariants. (The redirected plan.)
- **Retrieval inside the engine** — breaks the engine purity boundary
  (`engine/README.md`: no runtime side effects). The backend does the IO.
- **In-process vendoring of trellis as a library** — poggio is Rust; a
  subprocess CLI (like `recall`) is the clean, decoupled seam, and keeps
  poggio independently ownable.

## Cross-links

RFC-0011 (the fold); `poggio#2` (corpus contract), the Lorekeeper handoff
brief; ADR-0001 (canonical data on disk); the BACKLOG "Lorekeeper" item this
redirects; `project_poggio_session_json_softcontract` +
`reference_recall_ecosystem_memory` memories.

# RFC 0011 — Lorekeeper fold (Slice 1: gated, fail-open plumbing)

**Status:** Implemented
**Date:** 2026-07-01
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** the **Lorekeeper fold** — wiring `poggio` (the vendored
trellis-based per-world lore-retrieval tool, `russalo/poggio` v0.1.0, verified
live 2026-07-01) into the turn loop so the DM **cites canon instead of
improvising it**. Slice 1 of N.
**Companion:** ADR-0006 ("retrieval substrate: vendor trellis via poggio,
retire ChromaDB-RAG") — landed in the same PR.
**Supersedes:** the ChromaDB-vector-RAG plan in the BACKLOG "Lorekeeper" item
(redirected 2026-06-29).

---

## Where this sits

The DM → Fact-Extractor pipeline plus the external `poggio` tool. This RFC is
the **fold** — the Sentinel-internal wiring the handoff brief reserved as
"mine." Poggio owns retrieval (adapter + recipes + query CLI over trellis);
this wires its output into the DM's context assembly, before the DM call.

**The load-bearing constraint — the engine is pure.** Per `engine/README.md`
§ "The boundary contract" (no runtime side effects), `engine/` does no
subprocess or filesystem IO. Poggio is a subprocess that reads the world's
`data/`. So the fold **splits across the node boundary**: the backend does the
IO (calls poggio), the engine only *renders* the returned hits into the
prompt — the same shape as the existing roll / level-up plumbing.

## Ratified decisions (2026-07-01)

- **Backend does IO, engine renders.** Retrieval (poggio subprocess + fs read)
  lives in `backend/state/lorekeeper.py`; the engine receives hits as data and
  renders a canon block (`engine/agents/lorekeeper.py`). `engine/` stays pure.
- **Gated + dormant by default.** `SENTINEL_LOREKEEPER_ENABLED` (default
  false). Off ⇒ the assembled prompt is byte-identical to today; zero gameplay
  change until armed.
- **Fail-OPEN.** Retrieval is an *enhancement*, never a hard dependency. A
  missing/broken poggio (not on PATH, non-zero exit, timeout, bad JSON) →
  retrieval returns `[]`, the turn proceeds without a canon block, the failure
  is logged. A missing tool must never break a turn.
- **Slice 1 recipes: `at-location` + `established`.** Scene entities (always) +
  bm25 "have we established X?" on the player action. `members` → Slice 2.
- **Lean projection consumer-side for v0.1.0.** Trim poggio's full `attrs` to
  `{id, kind, name, source, snippet}` on the Sentinel side; poggio's `#4` lean
  projection (their v0.2.0) is co-designed against this and adopted in Slice 2.
- **`world_root = data_dir.parent`.** Poggio's `--world` wants the dir
  *containing* `data/`; `find_session_data_dir` returns `data/`, so its parent
  is the world root in both shared and per-world modes.

## What landed

### 1. Config (`backend/config.py`)
`SENTINEL_LOREKEEPER_ENABLED` (bool, default false) + `SENTINEL_POGGIO_BIN`
(str, default `poggio` on PATH). Both dormant defaults on the dataclass.

### 2. Backend retrieval (`backend/state/lorekeeper.py`, new — the IO half)
`retrieve_canon(data_dir, world_context, player_action, settings)`: fast `[]`
when disabled; `world_root = data_dir.parent`; subprocesses `poggio query
--world … --recipe {at-location, established} …`; dedups by `id` (scene ahead
of established), caps at top-K ≤ 8; lean-projects each hit; **fail-open** on any
subprocess/JSON error.

### 3. Engine (pure — the render half)
`DMTurnInput.retrieved_lore: list[dict] | None`; `engine/agents/lorekeeper.py`
`render_canon_block(hits)` → a `RELEVANT CANON (established facts — cite, do
not contradict or re-invent):` block, tolerant of malformed/empty input
(→ `""`). Injected in `_build_messages` (before the player action, as context)
at both the `run_turn` and `stream_turn` sites.

### 4. Backend wiring (`backend/routes/stream.py`)
Between `load_world_context` and `DMTurnInput`, calls `retrieve_canon(...)` and
passes `retrieved_lore`. Dormant ⇒ short-circuits to `[]`, no block renders.

## Acceptance Criteria

- [x] `SENTINEL_LOREKEEPER_ENABLED` + `SENTINEL_POGGIO_BIN` in `Settings`.
- [x] `backend/state/lorekeeper.py`: `retrieve_canon` — recipe subprocess,
      dedup, lean projection, **fail-open** (poggio mocked in tests).
- [x] `DMTurnInput.retrieved_lore`; `engine/agents/lorekeeper.py`
      `render_canon_block`; injected in `_build_messages` at both sites.
- [x] Backend wiring in `stream.py`.
- [x] Tests: engine (render/omit + block injection + defaults); backend
      (dormant short-circuit, fail-open on missing binary / bad JSON / non-zero
      exit, lean-projection shape, dedup, `Nowhere` skip).
- [x] **Dormant by default** — a test pins the assembled message identical when
      `retrieved_lore` is `None`/`[]`.
- [x] RFC 0011 + ADR 0006 land Implemented in the same PR.

## Out of Scope (Slice 2+)

- **`members` recipe** (focal-NPC relationship neighborhood).
- **Poggio v0.2.0 lean projection** (`poggio#4`) — co-designed against this
  RFC's context object, adopted later.
- **Arming it** — the deploy-env work (`trellis ≥ 0.26` + the `poggio` binary
  on PATH in the Sentinel runtime; systemd/cutover). Slice 1 lands dormant.
- **A UI surface** for cited canon; **index persistence** tuning (Slice 1 uses
  rebuild-on-query); the Fact-Extractor **`lorekeeper` write role** (the Entity
  Sweeper's lane).

## Cross-links

ADR-0006 (retrieval substrate); `poggio#2` (corpus contract), `poggio#4` (lean
projection FR); `scratch/lorekeeper-handoff-brief.md`; the BACKLOG "Lorekeeper"
item; `project_poggio_session_json_softcontract` memory. Mirrors the RFC-0006
roll / RFC-0009 level-up plumbing shape.

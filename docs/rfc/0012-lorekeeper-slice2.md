# RFC 0012 — Lorekeeper fold Slice 2 (v0.2.0 lean adoption + version assert)

**Status:** Implemented
**Date:** 2026-07-01
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** two of the pieces RFC-0011 (Slice 1) deferred — makes the fold
production-ready against poggio **v0.2.0**: consume its lean output, and assert
its schema version at runtime (deploy-safety). Still **dormant**; arming stays
the operational step *after* this. **`members` is deferred to Slice 3**
(Russell, 2026-07-01 — keep Slice 2 small + low-risk).
**Depends on:** RFC-0011 (Slice 1); poggio **v0.2.0** (`b84f46c`, lean default
+ `schema-version` + string-id guarantee, co-designed & verified 2026-07-01);
ADR-0006 (retrieval substrate).

---

## Where this sits

RFC-0011 landed the fold gated + fail-open + dormant, consuming poggio v0.1.0's
**full-attrs** output and trimming it consumer-side. Poggio v0.2.0 now emits the
**lean** hit `{id, kind, name, source, snippet}` by default (co-designed to
Sentinel's spec), truncates snippets at the source, guarantees string ids, and
ships a `poggio schema-version` probe. This slice adopts the lean output + the
version probe — the two low-risk, high-value pieces that make an *armed* fold
correct and deploy-safe.

**Deploy-order fact this slice resolved:** Slice-1's `_project` read `attrs.name`,
gone from the lean default — so a Slice-1 fold against v0.2.0 would show slug ids
instead of display names (harmless only because dormant). This slice makes
"armed fold" and "v0.2.0 output" match, so **arming is gated on this slice**.

## Decisions (2026-07-01)

1. **Consume the lean form directly.** `_project` is now a validate +
   pass-through: require a dict with a non-empty **string** `id` (the defensive
   guard stays — untrusted external output; poggio guarantees string ids but
   belt + suspenders), then keep `{id, kind, name, source, snippet}` as-is.
   **Consumer-side truncation deleted** (poggio truncates at source with an
   ellipsis only when cut) — no double-cut. Dedup-by-id + top-K cap unchanged;
   budget stays Slice-1 (`at-location` ≤ 5, `established` ≤ 3, cap 8).
2. **Version assert (deploy-safety).** `poggio >= 0.2.0` pinned (deploy doc) and,
   **lazily on first retrieval when enabled**, `poggio schema-version` is probed
   once and the verdict cached process-level (keyed by binary path). Not exactly
   `_EXPECTED_SCHEMA` (`"0.2"`) — wrong/old/missing binary, non-zero exit, decode
   error → **logged once + retrieval disabled for the process** (`[]`). Fail-open
   **loud**: a bad install yields no canon rather than a mis-shaped block. The
   probe needs no trellis.

## What landed

- **`backend/state/lorekeeper.py`:** `_project` → lean pass-through + string-id
  guard, truncation + `_SNIPPET_MAX` removed; `_schema_ok(poggio_bin)` (cached
  probe) gating `retrieve_canon` right after the enabled check;
  `_EXPECTED_SCHEMA = "0.2"`. The `at-location` + `established` recipe calls and
  the fail-open/utf-8 hardening are unchanged.
- **Tests (`tests/backend/test_lorekeeper.py`):** rewritten to the **lean**
  fixtures + a mock that answers both the `schema-version` probe and recipe
  queries; a cache-clearing autouse fixture; new cases — schema match → on,
  mismatch/probe-error → disabled + `[]`, probe cached once/process, no
  double-truncation, plus the retained dormant / recipe-fail-open / dedup /
  non-scalar-id / utf-8 / Nowhere-skip cases.

## Acceptance Criteria

- [x] `_project` consumes the lean form (pass-through + string-id guard,
      truncation removed); a lean hit renders identically to today.
- [x] Cached `poggio schema-version` assert: `0.2` → retrieval on;
      mismatch/error → logged once + retrieval disabled (`[]`); probed at most
      once (cached).
- [x] Backend tests updated to the lean shape; new assert + no-double-truncation.
- [x] **Still dormant by default**; the disabled path unchanged.
- [x] RFC-0012 lands Implemented; `poggio >= 0.2.0` documented (here + BACKLOG).

## Verification

Exercised end-to-end against the **real poggio v0.2.0** binary: schema-gate
passes (`0.2`), lean output passes through to the correct `{id,kind,name,source,
snippet}` hits + a clean canon block; a wrong binary path disables retrieval with
the fail-open-loud log. Full suite green.

## Out of scope

- **`members` recipe → Slice 3** (focal-NPC neighborhood; deterministic
  faction-of-in-scene-NPCs focal-selection + a budget re-balance to 4/2/2).
- **Arming it** — the deploy-env flip (trellis ≥ 0.26 + `poggio` on PATH, then
  `SENTINEL_LOREKEEPER_ENABLED=true` in a patch window). Operational, gated on
  this slice. Flipping `serves` active (the Blueprint assertion) happens then.
- **A UI surface** for cited canon; **index persistence** (`--db` per world).

## Cross-links

RFC-0011 (Slice 1, the fold); ADR-0006 (substrate); poggio v0.2.0 RFC
(`senlab/poggio/scratch/v0.2.0_RFC_DRAFT.md`) + `poggio#4`;
`project_poggio_session_json_softcontract`.

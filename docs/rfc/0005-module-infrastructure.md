# RFC 0005 — Module infrastructure foundation

**Status:** Implemented
**Date:** 2026-06-23
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005 (subsystem modularity) — the foundational wiring slice.
**Supersedes:** —
**Superseded by:** —

---

## RFC sequence under ADR-0005

ADR-0005 commits Sentinel to a registry of swappable per-subsystem modules. It
ships across several RFCs in dependency order; this is the first:

1. **RFC-0005 (this one) — Module infrastructure foundation.** The plumbing:
   manifest format, loader, registry, `module_data` namespacing convention,
   and module-composed DM-prompt assembly. Ships ONE module — `core/base-v1` —
   that repackages the *current* DM behavior verbatim. **Zero gameplay change.**
2. **RFC-0006 — Resolution + character-sheet modules** (`core/d20-vs-dc-v1`,
   `core/four-stat-v1`).
3. **RFC-0007 — Class + combat modules** (`core/four-class-fantasy-v1`,
   `core/hp-pool-v1`).
4. **RFC-0008 — Magic module** (`core/realm-pool-v1`) including its internal
   caster bindings (deity/patron, tradition/school) + content + selectors.
5. **RFC-0009 — Progression module** (`core/milestone-v1`).

Each rides this RFC's plumbing. ADR-0004 (state truthfulness) is a sibling
track, not a blocker — the plumbing is orthogonal to the mutation-authority
rules.

## Context

Before this RFC the DM system prompt was a single hand-authored constant
(`engine.prompts.dm.DM_SYSTEM_PROMPT`), concatenated into the message array by
the DM agent. The roleplay system's mechanics were absent or implied in prose
rules inside that one string. There was no seam to swap a subsystem's behavior
without editing the monolith.

ADR-0005 commits to subsystem modularity. Before any mechanics module can ship,
the engine needs the infrastructure to declare modules (a manifest), load +
validate them, bind a set of modules to a world, namespace each module's state
additions, and assemble the DM prompt by composing module contributions instead
of hard-coding them.

This RFC builds exactly that and repackages the existing DM behavior as a single
`core/base-v1` module — so the architecture is exercised end-to-end with **no
observable gameplay change**. The big structural shift is reviewable for
correctness (the assembled prompt is byte-identical to the prior string) before
any mechanics ride on it.

## Proposal (as implemented)

### 1. Module manifest format

A module is declared by a TOML manifest. **Core modules ship with the engine
code** under `engine/modules/<subsystem>/<impl>/manifest.toml` — they are
trusted (a future module may carry Python contract logic). **Community modules**
(future) live under `data/lore/community/<pack>/modules/<slug>/` and are
DATA-ONLY (TOML + Markdown + presets, no Python — the trusted/untrusted
boundary). This is a refinement of ADR-0005's "core manifests in data/" sketch:
core modules belong with the engine code, where prompts already live.

Manifest fields: `name` (`<namespace>/<slug>-v<major>`), `version`, `subsystem`,
`interface_version`, `prompt_fragment` (path relative to the manifest dir),
`schema_fragment`, `preset_paths`, `requires`.

### 2. Loader + registry

`engine/modules/`:
- `manifest.py` — a frozen `ModuleManifest` dataclass parsed with stdlib
  `tomllib` (the engine is pydantic-free). Explicit validation: a malformed
  manifest raises `ManifestError` with a path-tagged message.
- `loader.py` — `discover_modules()` scans `engine/modules/*/*/manifest.toml`;
  `load_module(name)` resolves a module into a `LoadedModule` (manifest + the
  read prompt-fragment text, trailing newlines stripped). Duplicate module
  names fail loud.
- `registry.py` — a process-lifetime cache so a module's manifest + fragment are
  read once. Tests call `registry.clear()` for a cold read.

### 3. `module_data` namespacing — a convention, not (yet) schema-enforced

Module-added entity state lives under `module_data.<subsystem>` on the entity,
never as flat top-level fields. **This RFC ships the convention, not enforcement.**
The schema that exists today (`schemas/apply_world_update.schema.json`) validates
the *fs-manager write payload*, not the stored-entity shape — its `data` field is
freeform `["object","string","array"]`, so `module_data` already passes. There
is no stored-entity schema to tighten yet; entity-schema-level enforcement of
`module_data.<subsystem>` sub-shapes lands with the first module that defines
real fields (RFC-0006). `core/base-v1` adds no `module_data` fields, so the
convention is purely forward-looking here.

### 4. `world.modules` field — lazy-defaulted

A world's active module set lives in its `state.json` as a `modules:
{<subsystem>: <module_name>}` map. **Read with a lazy default:** a world with no
`modules` map (every world created before this RFC) resolves to the core default
set at prompt-assembly time — no migration write. RFC-0005 does not write the
field at creation (there's only one module per subsystem; an explicit write
waits for a WorldCreation module-picker, RFC-0006+). The backend
(`backend/state/world_context.py`) reads `world.modules` and threads it into the
engine's `WorldContext`.

### 5. Module-composed DM prompt assembly

`engine/modules/assembly.py::build_dm_prompt(modules)` walks the world's active
modules in `CANONICAL_SUBSYSTEM_ORDER` and concatenates each module's prompt
fragment (joined by a blank line). `None`/empty falls back to `DEFAULT_MODULES`
(`{"base": "core/base-v1"}`). Unknown subsystem keys are ignored (forward-compat
guard). The former `DM_SYSTEM_PROMPT` content moved verbatim into
`engine/modules/base/base-v1/prompt.md`; `engine.prompts.dm.DM_SYSTEM_PROMPT` is
now `build_dm_prompt()` (a back-compat constant, byte-identical).

The DM agent (`engine/agents/dm.py`) — `_build_messages` / `_build_intro_messages`
— now assemble the system prompt per-world via `build_dm_prompt(ctx.modules)` /
`build_dm_prompt(intro.modules)`. `WorldContext` and `IntroInput` gained an
optional `modules` field (default `None` → default set).

## Proof of correctness

The central safety property: **the assembled prompt for the default module set
is byte-identical to the pre-RFC-0005 prompt.** The original `DM_SYSTEM_PROMPT`
is frozen in `tests/fixtures/dm_system_prompt_pre_rfc0005.txt`;
`tests/engine/test_modules.py` asserts `build_dm_prompt() == frozen`. The full
Python suite passes with **zero existing tests modified** — no behavior changed.

## Resolved Questions

1. **Prompt-fragment storage** → `.md` files under the module dir, read as text.
2. **Canonical subsystem order** → shipped the full v0.1 list now (base,
   resolution, character_sheet, class, combat, magic, progression, time,
   tension); modules slot in as they land. (Patron/tradition fold into `magic`
   per ADR-0005, not peer subsystems.)
3. **Character-entity schema location** → there is no stored-entity schema; the
   fs-manager payload schema's freeform `data` already permits `module_data`.
   Enforcement deferred to RFC-0006.
4. **Per-module Pydantic contracts** → deferred to each subsystem's RFC.
5. **Saved-world migration** → `core/*-v1` only today; migration rules spec'd in
   a later RFC.
6. **Core-module location** → `engine/modules/` (with the code), not
   `data/lore/core/modules/`. Community modules stay under the data tree's
   namespace gate. Documented in ADR-0005 §6 + this RFC §1.

## Acceptance Criteria

- [x] `engine/modules/` package: `manifest.py`, `loader.py`, `registry.py`,
      `assembly.py`, + the `base/base-v1/` module (manifest + prompt.md).
- [x] The DM-prompt content migrated verbatim into the base module's fragment.
- [x] `build_dm_prompt()` byte-identical to the frozen pre-RFC prompt
      (snapshot test).
- [x] `world.modules` read with lazy default; threaded into `WorldContext`.
- [x] `module_data` convention documented (no schema to enforce yet).
- [x] DM agent assembles the prompt per-world via `build_dm_prompt`.
- [x] Full Python suite passes unchanged (577 passing, +15 new module tests).
- [x] ADR-0005 lands Accepted in the same PR; `docs/adr/README.md` +
      `docs/rfc/README.md` indexes updated; `engine/README.md` documents the
      architecture.

## Out of Scope

- Any roleplay mechanics (RFC-0006+).
- Community module loading (the loader's design accommodates it; only the core
  path ships here).
- Mid-game module swapping (world-bound at creation, per ADR-0005).
- Per-subsystem Pydantic contracts + entity-schema enforcement (land per
  subsystem).
- WorldCreation UI for picking modules (hard-defaults to the core set).
- Writing `world.modules` at creation (lazy-default read suffices for one
  module per subsystem).

## Cross-links

- [ADR 0005 — Subsystem modularity](../adr/0005-subsystem-modularity.md) — the
  architecture this implements
- `engine/modules/` — the package
- `engine/modules/base/base-v1/` — the base module (manifest + prompt)
- `tests/engine/test_modules.py` + `tests/fixtures/dm_system_prompt_pre_rfc0005.txt`
- Migration target: `engine/prompts/dm.py` (the former monolith → assembly shim)
- Touch points: `engine/types.py` (`WorldContext`/`IntroInput` gain `modules`),
  `engine/agents/dm.py` (per-world assembly), `backend/state/world_context.py`
  (reads `world.modules`)

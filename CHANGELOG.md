# Changelog

> **Status: not actively maintained.** This file is kept as a historical
> snapshot of the v0.1.0 release and is no longer updated turn-by-turn.
> The authoritative change log for Project Sentinel is:
>
> - **`git log`** — per-commit history with full diffs
> - **[GitHub Pull Requests](https://github.com/russalo/project-sentinel/pulls?q=is%3Apr+is%3Aclosed)** — merged PRs with descriptions and reviews
> - **`docs/adr/`** — architecture decisions that shaped the codebase
> - **`docs/BACKLOG.md`** + **`docs/ROADMAP.md`** — work in flight and next up
>
> Several items in the v0.1.0 section below (e.g. `mcp-servers/db-vector/`,
> `infrastructure/migrations/`, `artifacts/api-server/`) have since been
> removed from the codebase. They are preserved here as a record of what
> shipped on 2026-03-24, not as a description of current state.
>
> If Keep-a-Changelog discipline returns to the project, it will start
> from a fresh `[Unreleased]` section under a later release tag, not by
> back-filling the ~6 months between v0.1.0 and now.

---

## [0.1.0] — 2026-03-24

Initial working prototype. The schema gate holds. The loop runs.

### Added
- Three-node distributed architecture: Inference Node, MCP Bridge, Infrastructure Node
- `schemas/apply_world_update.schema.json` — JSON Schema Draft 2020-12 contract governing all AI-to-filesystem writes
- `schemas/community_manifest.schema.json` — Community content pack gateway schema
- `mcp-servers/fs-manager/` — Zero-touch filesystem MCP server with path validation, protected field enforcement, and schema-gated CRUD
- `mcp-servers/db-vector/` — PostgreSQL + ChromaDB query routing MCP server
- `mcp-servers/git-sync/` — Atomic Git commit MCP server for version snapshotting after each world update
- `infrastructure/docker-compose.yml` — PostgreSQL 16 + ChromaDB stack with Tailscale IP binding support
- `infrastructure/.env.example` — Environment variable template with security annotations
- `infrastructure/migrations/` — SQL migration scripts for initial world state schema
- `data/` — Hybrid storage layer: `lore/` (Markdown) + `state/` (JSON) with Core/Community namespace separation
- `ARCHITECTURE.md` — Core vs. Community framework, namespace rules, protected fields, node roles, and update pipeline
- `CONTRIBUTING.md` — Three contributor pathways: Lore-Smith, Schema-Architect, Technician
- `.github/ISSUE_TEMPLATE/lore_entry.md` — Lore-Smith issue template
- `.github/ISSUE_TEMPLATE/schema_refinement.md` — Schema-Architect issue template
- `.github/ISSUE_TEMPLATE/mcp_tool.md` — Technician issue template
- `.github/PULL_REQUEST_TEMPLATE.md` — PR template with AI-assisted disclosure requirements
- `artifacts/rpg-engine/` — React + Vite reference frontend (game console UI)
- `artifacts/api-server/` — Express 5 reference backend with DM persona and world updater
- `lib/` — Shared TypeScript libraries (api-client, api-spec, api-zod, db, integrations-openai)

### Architecture decisions
- The Inference Node is granted **zero** direct filesystem access. All writes are mediated by MCP servers.
- `session_id` must be UUID format — enforced at schema level, not application level.
- Community content is namespace-separated at both the filesystem and ChromaDB metadata level.
- Core state fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`) are immutable by any community payload.

---

[0.1.0]: https://github.com/russalo/project-sentinel/releases/tag/v0.1.0

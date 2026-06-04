---
name: "📐 Schema Refinement"
about: "Update or expand the machine-readable JSON state models (e.g., entities, items, factions, locations)."
title: "[Schema] "
labels: ["schema-architect", "json-state", "core-engine"]
assignees: ""
---

## 📐 Refinement Objective

<!-- Why are we changing the world state schema?
     What new mechanics, data points, or narrative requirements does this change unlock?
     Example: "Adding an 'alignment' field to characters so the DM agent can make
     morality-based faction reputation decisions automatically." -->


## 📁 Target Schema File(s)

<!-- Which schema file(s) are being modified?
     Example: schemas/entity.schema.json, schemas/faction.schema.json -->

- `schemas/`

## 🔄 Schema Changes (Before & After)

**This section is mandatory. Code review will not begin without it.**

**Before (Current State):**

```json
// Paste the relevant snippet of the current schema here.
// Focus on the object or property being changed — not the entire file.
```

**After (Proposed State):**

```json
// Paste the new snippet here.
// Highlight additions with a comment: // NEW
// Highlight modifications with a comment: // CHANGED
// All new properties must include: type, description, and constraints.
```

## 🛤️ Migration Plan

<!-- If this change is merged, how do we update existing world data in /data/state/?

     Choose one:
     A. Non-breaking addition (new optional field with a default) — describe the default.
     B. Breaking change — provide a Python migration script that updates existing JSON files.
     C. No existing data affected — explain why.

     If option B, paste the migration script outline here:
-->


## 🧠 Technical Context

<!-- Provide context for AI coding assistants.
     Answer these questions:
     1. Does this change require the `fs-manager` MCP server to validate the new field?
        If so, describe the validation rule.
     2. Does this change affect the `fact-extractor` agent's prompt?
        If so, describe what new information it must now extract from the DM narrative.
     3. Does this change affect the `dm.yaml` agent?
        If so, describe how the DM should use this new field in its narrative.
     4. Does this change require migrating existing on-disk JSON under `data/`?
        If so, include the Python migration script outline (see option B above).
     5. Could this change break any existing community packs?
        If so, what is the communication plan for pack authors?
-->


## ✅ Architect Checklist

- [ ] The change strictly adheres to JSON Schema Draft 2020-12 (`$schema: "https://json-schema.org/draft/2020-12/schema"`).
- [ ] All new properties include `type`, `description`, and where applicable, `enum`, `pattern`, or `minimum`/`maximum` constraints.
- [ ] `additionalProperties: false` is maintained on all modified objects.
- [ ] Protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`) are not modified or removed.
- [ ] If this is a breaking change, I have provided a migration script.
- [ ] I have tested the new schema against a local instance of the `fs-manager` MCP server.
- [ ] I have checked that no existing community packs in `data/lore/community/` would break under this change.
- [ ] I have tagged this PR with `[AI-Assisted]` if core logic was LLM-generated.

---
name: "📜 New Lore Entry"
about: "Forge new history, NPCs, factions, or locations for the World Engine."
title: "[Lore] "
labels: ["lore-smith", "rag-context", "markdown"]
assignees: ""
---

## 📜 Lore Summary

<!-- Provide a brief, atmospheric summary of the lore you are adding.
     What is it, and how does it fit into the world? Be specific — vague
     summaries slow down review. -->


## 📁 Markdown File Path

<!-- Exactly where in the repository will this file live?
     All community lore must be under data/lore/community/<your-handle>/
     Examples:
       data/lore/community/your-handle/factions/trog.md
       data/lore/community/your-handle/codex/magic_systems.md
       data/lore/community/your-handle/npcs/seriva.md
-->

**Path:** `data/lore/community/<your-handle>/`

## 🧠 Technical Context

<!-- Provide context for AI assistants and the Lorekeeper agent.

     Answer these questions:
     1. What keywords or themes should the Vector DB use to retrieve this document
        during a session? (e.g., "Trog, Sunken Citadel, undead, betrayal")
     2. Are there any existing Core entities this lore connects to?
        If so, list their entity names (from data/state/core/).
     3. Does this lore introduce any new mechanics (e.g., new magic types, currency)?
        If so, does it require a Schema-Architect issue as well?
-->


## 🔗 Core References

<!-- List any Core entity unique_ids or names this lore references but does NOT modify.
     This is required by the community.json manifest format.
     Example: entity_trog_001, location_sunken_citadel_001
-->

- References:

## ⚙️ Fact Extraction & Ingestion Checklist

- [ ] **Namespace:** The file is placed under `data/lore/community/<my-handle>/` — NOT under `data/lore/core/`.
- [ ] **Formatting:** The file uses clean Markdown (H1 title, H2 sections, bullet points) for optimal RAG chunking.
- [ ] **No Contradiction:** I have checked that this lore does not contradict any Core lore in `data/lore/core/`. If it does, I have framed it explicitly as a rumor or alternative legend.
- [ ] **community.json:** I have updated (or created) my pack's `community.json` manifest to include this file in `lore_files`.
- [ ] **State Link:** If this lore introduces a physical entity (NPC, location, item), I have also opened a Schema-Architect issue to create its JSON state entry (if applicable).
- [ ] **ChromaDB Ingestion:** _(Deferred — the RAG / Lorekeeper indexing path is not yet wired up. Leave unchecked for now; a dedicated indexing step will ship with the Lorekeeper agent.)_

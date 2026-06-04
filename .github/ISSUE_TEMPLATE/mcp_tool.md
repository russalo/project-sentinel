---
name: "⚙️ New MCP Tool"
about: "Build a new Python-based MCP Server or Tool (e.g., weather-generator, combat-roller, discord-broadcaster)."
title: "[Tool] "
labels: ["technician", "mcp-server", "python", "backend"]
assignees: ""
---

## ⚙️ Tool Description

<!-- What does this tool do? How does it extend the Infrastructure Node's capabilities?
     Be specific about the trigger: What player action or world event causes the DM
     to call this tool? What would break in the game without it? -->


## 🗂️ MCP Server Location

<!-- Which existing server does this tool belong to, or does it need a new server?
     Examples:
       Belongs to: mcp-servers/fs-manager/
       New server: mcp-servers/combat-roller/
-->

**Location:** `mcp-servers/`

## 📜 JSON Schema Contract

**This section is mandatory. The tool MUST be defined before code review begins.**

The Inference Node will call this tool by POSTing the input payload to your server.
Define the exact Draft 2020-12 JSON Schema for the input and describe the output.

**Input Schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    // Define exact input fields here
    // Include type, description, and constraints for every field
  },
  "required": [],
  "additionalProperties": false
}
```

**Expected Output (on success):**

```json
{
  // Describe the JSON structure the tool returns to the Inference Node
}
```

**Expected Output (on validation failure):**

```json
{
  "code": "VALIDATION_ERROR | PATH_VIOLATION | ...",
  "detail": "Human-readable error for the Orchestrator to relay to the DM for self-correction."
}
```

## 🛡️ Security & Infrastructure Notes

<!-- The Inference Node may hallucinate. Your server is the last line of defense.
     Answer all that apply. -->

- **Files/Directories Accessed:** (e.g., `data/state/core/entities/*.json`)
- **Ports/External APIs Used:** (e.g., ChromaDB on :8000, an external weather API)
- **Does it write to the filesystem?** Yes / No
  - If Yes: Specify the exact `target_file` pattern and confirm the path is protected by regex validation.
- **Does it execute shell commands?** Yes / No
  - If Yes: Describe the sanitization strategy.
- **Directory Traversal Prevention:** How does this tool prevent a crafted `target_file` from escaping `/data`?
- **Injection Prevention:** How does this tool prevent SQL injection, command injection, or prompt injection?

## 🧠 Technical Context

<!-- Provide context for AI coding assistants.
     Answer these questions:
     1. Which existing MCP server should this live alongside?
     2. What new Python packages does this require? (add to requirements.txt)
     3. Does this tool need new on-disk state under `data/`? If so, describe the JSON shape and which schema contract in `schemas/` gates it.
     4. Does this tool affect the Fact-Extractor's prompt? If so, describe the new <world_update> fields.
     5. Does the DM agent YAML need to be updated to document this new tool capability?
-->


## ✅ Technician Checklist

- [ ] The JSON Schema uses `additionalProperties: false`.
- [ ] All file path inputs are validated against a strict regex pattern before any `open()` call.
- [ ] The server returns a structured error JSON (not a stack trace) on schema validation failure.
- [ ] I have written automated Python tests covering: valid payload, invalid payload (schema reject), path traversal attempt.
- [ ] `requirements.txt` is updated with all new dependencies.
- [ ] If this tool writes to `/data`, I have confirmed it does not touch any protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`).
- [ ] I have tagged this PR with `[AI-Assisted]` if core logic was LLM-generated.

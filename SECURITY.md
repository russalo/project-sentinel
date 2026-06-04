# Security Policy

## Supported Versions

Project Sentinel is currently in pre-release (`v0.1`). Security fixes are applied to the `master` branch only.

| Version | Supported |
|---------|-----------|
| `master` (latest) | ✅ |
| Any tagged release | ✅ |
| Forks / community modifications | ❌ |

---

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via [GitHub Security Advisories](https://github.com/russalo/project-sentinel/security/advisories/new). You will receive an acknowledgement within 72 hours and a resolution timeline within 7 days.

Include the following in your report:
- A description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept code or curl commands welcome)
- The component affected (see Attack Surface below)
- Whether you believe it is exploitable remotely or only locally

---

## Attack Surface

Project Sentinel's attack surface is intentionally narrow by design. The Inference Node (LLM) is **never** granted raw filesystem or database access — all mutations flow through MCP servers that enforce JSON Schema validation. Nonetheless, the following areas warrant security scrutiny:

### 1. `fs-manager` MCP Server (`:8010`)

**Risk: Path Traversal**

The `fs-manager` validates `target_file` against a strict regex allowlist before any file operation. A bypass of this regex (e.g., via Unicode normalization, null bytes, or encoding tricks) could allow writes outside `/data/`.

**Mitigations in place:**
- `ALLOWED_PATH_PATTERN` regex rejects any path not matching `data/state/` or `data/lore/` prefixes
- `pathlib.Path` resolution is used for all file writes — no raw string concatenation
- Protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`) are blocked at the application layer regardless of payload content

**Additional hardening recommended:**
- Run `fs-manager` as a dedicated low-privilege OS user with write access scoped only to `/data/`
- Bind exclusively to `127.0.0.1` or a Tailscale IP — **never** `0.0.0.0`

### 2. ChromaDB & the Future Lorekeeper Path

**Risk: Prompt Injection via RAG Queries**

ChromaDB is in the stack for the future Lorekeeper agent. Once that agent lands, retrieved documents will be injected into the DM's context window. A malicious actor who can insert crafted text into the vector store (e.g., via a poisoned community pack) could use that to manipulate model behaviour.

**Mitigations designed in:**
- Community content will be ingested at lower RAG priority than Core content
- The (future) Sentinel Airlock discards all imported ChromaDB vectors and re-generates embeddings locally from source Markdown

**Additional hardening recommended:**
- Sanitize Markdown content for prompt-injection patterns (e.g., role-switching instructions) before ChromaDB ingestion
- Log all Lorekeeper context injections for audit review

### 3. `git-sync` MCP Server (`:8012`)

**Risk: Command Injection**

If user-controlled data (e.g., `session_id` or `log_entry` content) is interpolated into shell commands passed to `gitpython` or `subprocess`, an attacker could inject shell metacharacters.

**Mitigations in place:**
- `session_id` is validated as UUID format by the JSON Schema before reaching `git-sync`
- `gitpython` uses its own subprocess abstraction — avoid `shell=True` in all git operations

**Additional hardening recommended:**
- Ensure commit messages are constructed from trusted fields only (session UUID + turn number)
- Never interpolate raw `log_entry` text into git commit messages

### 4. Docker Services

**Risk: Exposed Database Ports**

`sentinel-chromadb` (`:8000`) binds to `TAILSCALE_BIND_IP` from `.env`. If this is set to `0.0.0.0` (intentionally or by mistake), the ChromaDB port becomes accessible to any host on the network.

**Hardening required:**
- Set `TAILSCALE_BIND_IP=127.0.0.1` for local-only development
- Set `TAILSCALE_BIND_IP=<your Tailscale IP>` for multi-node mesh deployments — **never** a public IP
- Enable ChromaDB token authentication (`CHROMA_AUTH_PROVIDER`) for any deployment with more than one user

### 5. The `.spak` Import Airlock

**Risk: Malicious Archive Contents**

Importing an untrusted `.spak` from the internet poses risks including directory traversal (crafted file paths), schema flooding (oversized JSON designed to exhaust memory), and Poisoned RAG (pre-computed embeddings designed to manipulate the Lorekeeper).

**Mitigations designed into the Airlock:**
- Extraction into isolated `/tmp/sentinel_airlock/` before any validation
- Full JSON Schema validation against Draft 2020-12 schemas before promotion
- Path sanitization blocking `../` traversal and symlinks outside `/data`
- ChromaDB vectors are always discarded and re-generated locally

---

## Security Best Practices for Deployers

1. **Never expose MCP server ports to the public internet.** They are designed for Tailscale mesh or localhost only.
2. **Do not store LLM API keys on the Infrastructure Node.** API keys belong on the Inference Node only (see `.env.example`).
4. **Audit `git log` regularly.** Every world update produces a Git commit — anomalous commit frequency or large diff sizes may indicate a runaway LLM loop.
5. **Review community packs before importing.** Run `porter import --dry-run <file.spak>` (coming in v0.5) to inspect contents before promoting to `/data/`.

---

## Acknowledgements

Security researchers who responsibly disclose valid vulnerabilities will be credited in the relevant release notes (with their permission).

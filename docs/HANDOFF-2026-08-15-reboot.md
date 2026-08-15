# Handoff — origin-core reboot, 2026-08-15

Point-in-time state for the session that spans PRs #187–#192. Pointers only; the
full transcript lives in the chatlog corpus
(`/srv/projects/pkplab/chatlogs/project-sentinel/`).

## Status: at equilibrium, nothing mid-flight

Master `0c0a0c9`, clean tree, nothing unpushed, **0 open PRs**, 841 Python + 359
frontend tests green, ruff clean. No work is half-done.

## THE ONE THING TO DO NEXT

**PR #192 (entity-identity hardening) is merged to master but NOT deployed.**

- Backend-only — **no SPA rebuild needed**.
- Deploy = `sudo systemctl restart sentinel-backend` (needs Russell's sudo).
- Prefer the 05:00–08:00 PT patch window. Verify after with `/alpha/healthz` and
  one real turn.

Currently live: SPA `releases/1980a3c`; backend restarted 2026-08-12 13:08 UTC,
carrying #187 / #189 / #190 / #191.

## What shipped in this session

| PR | Subject |
|---|---|
| #187 | RFC-0018 — engine-authoritative `hp.max` / `magic_pool.max` |
| #188 | CI ruff pin + `required-version` guard (Lint Python was red repo-wide) |
| #189 | Hint display truthfulness — HP bar no longer jumps to full |
| #190 | RFC-0019 — DM archetype mapping, engine-pinned write-once |
| #191 | `<action>` tag parser tolerance (+ a latent ReDoS on the stream path) |
| #192 | Entity-identity hardening — imposter PCs can't shadow or be minted |

Plus a full alpha deploy of #187/#189/#190/#191 through the RFC-0015 pipeline.

## Decisions that live ONLY in prose (now durable)

1. **Deploy order is SPA first, backend second.** The post-#189 backend emits
   `magic_pool: null` deletion markers that only the new `worldStore` deep-merge
   understands. Recorded in `project_adr0004_state_truthfulness` memory.
2. **`docs/BACKLOG.md` deliberately has no near-term/vision sections per entry.**
   CodeRabbit asked for them repeatedly; declined — BACKLOG is the triaged-item
   ledger, and none of its ~60 entries carry those fields. The split applies to
   ROADMAP/VISION-class docs. Same reasoning for RFCs: they are *implementation
   records* landing at Accepted with the code, not forward-looking plans.
3. **Codex re-posts already-fixed findings** — it repeated one item on four
   consecutive commits of #190, including the commit that fixed it. Verify against
   source (`git show <sha>:<path>`) before acting; act on reproduction, never on a
   tag.

## Blocked / needs someone else

- **#192 deploy** — needs Russell's sudo. Owner: Russell.
- **Non-ASCII player names can't persist a PC entity** (`docs/BACKLOG.md`).
  Structural: `_slugify` → None, the extractor drops the character, and the schema's
  `target_file` pattern is ASCII-only. The fix touches the slug contract **poggio**
  depends on (filename stem = entity id), so it routes through Russell as a product
  call. Owner: Russell.
- **"Opening narrative cut off"** — reported on staging 2026-08-11, never confirmed.
  No backend truncation exists and a live session returned a full 1507-char opening,
  so evidence says auto-scroll. Needs Russell to scroll to the top of a world once.
  Tracked in the memory inbox.

## Reboot-specific notes

- All six units (`sentinel-{backend,fs-manager,git-sync}` and their `-staging`
  siblings) are **enabled**, not merely active — verified, not assumed.
- No hand-started dev servers: every sentinel port (8001/8010/8012, 8101/8110/8112)
  resolves to a systemd unit.
- **The alpha's DM path depends on the `litellm-proxy` container on :4000**, which
  runs on origin-core itself (`OPENAI_BASE_URL=http://100.89.175.30:4000/v1`, and
  that is origin-core's own tailnet IP). Restart policy is `always`, so it should
  return. **Failure mode to watch:** if it doesn't, the alpha looks healthy
  (`/alpha/healthz` 200, SPA serves) but **every turn fails** — health checks won't
  catch it. LiteLLM config is tailnet's lane.
- Session scratchpad copied to `scratch/preserved-tmp-2026-08-15/` (gitignored, but
  `/srv` survives). Contents were only commit-message drafts and re-fetchable PR
  JSON — preserved wholesale rather than adjudicated.

## Next candidates after the #192 deploy

1. **PC entity provisioning at session creation.** One live world (`DongMaximus`)
   has run 5 turns with **no PC entity at all**, so ADR-0004's guarantees have
   nothing to attach to. Bigger reach problem than anything else open.
2. **RFC-0019 duplicate-op consolidation** (`docs/BACKLOG.md`) — deletes the carry
   machinery in `class_rules` that six review rounds each found an edge in.
3. The remaining ADR-0004 slices: NPC progression, `current ≤ max` clamp.

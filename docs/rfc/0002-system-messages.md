# RFC 0002 — System messages: operator-to-cohort channel

**Status:** Implemented
**Date:** 2026-06-14 (drafted in conversation); 2026-06-14 (implemented)
**Author:** Russell Pfister (design decisions); drafted by Claude
**Implements:** new feature — operator-to-cohort communication channel via the Settings drawer
**Supersedes:** —
**Superseded by:** —

---

## Context

Today there is no in-product way for the operator to communicate with the
alpha cohort. Maintenance windows, feature announcements ("the silhouette
flipped"), known-issue alerts, and feedback acknowledgements all happen
out-of-band (DM, text, or not at all). Testers see changes appear without
context; the operator has no surface to pre-announce or explain.

The Settings drawer (PR #120, gear icon in TopBar) is already the right
home — it's where player-prefs and meta-info accumulate (`fontSize` lives
there now). Adding a "Messages" section is the natural next surface.

The complementary need — the operator's compose / list / edit UI — does
not belong on the public alpha surface, because there's nothing to gain
from exposing it past the gate. Routing the admin side via tailnet
(Russell's call 2026-06-14) means the existing `test_caddy_invariant.py`
guards (which 404 `/api/admin/*` from the public edge) ARE the auth layer.
No token, no basic_auth elevation. Tailnet membership is the credential.

## Proposal

### Architecture

```
PUBLIC          sentinel.russalo.com/alpha/
                       │
                       ▼
                  Caddy (gate-fronted)
                       │  proxies non-admin paths only
                       ▼
                  ┌───────────────────────────────┐
                  │  Backend on :8001             │
                  │                               │
                  │  GET  /api/system-messages    │ ← cohort reads
                  │  POST /api/admin/system-…     │ ← public edge 404s these
                  │  PATCH /api/admin/system-…    │
                  │  DELETE /api/admin/system-…   │
                  └───────────────────────────────┘
                       ▲
                       │
TAILNET         sentinel.dev.russalo.com/admin/messages
                — tailnet-only; presence on the mesh IS the credential
```

### Backend

- **Storage:** one JSON file per message under
  `data/state/core/system_messages/<id>.json`, mirroring the
  ADR 0001 canonical-state-on-disk pattern. Helpers in
  `backend/state/system_messages.py` (`list_active()`, `read()`,
  `create()`, `update()`, `soft_delete()`).
- **Schema:**
  ```json
  {
    "id": "<uuid>",
    "published_at": "ISO-8601",
    "title": "string",
    "body": "markdown string (minimal: *italic*, **bold**, [link](url))",
    "category": "info | warning | release | maintenance",
    "pinned": false,
    "expires_at": "ISO-8601 (optional)",
    "deleted_at": "ISO-8601 (optional; soft-delete marker)"
  }
  ```
- **Endpoints (in `backend/routes/system_messages.py`):**
  - `GET /api/system-messages` — public (within the gate). Returns the
    active feed: filters out soft-deleted + expired messages, sorts
    pinned-first then by `published_at` descending.
  - `POST /api/admin/system-messages` — creates a message. Body:
    `{title, body, category?, pinned?, expires_at?}`. Returns the
    created record with server-minted `id` + `published_at`.
  - `PATCH /api/admin/system-messages/{id}` — partial update.
  - `DELETE /api/admin/system-messages/{id}` — soft-delete (sets
    `deleted_at`; the GET filters it out).
- **No auth code path.** The four endpoints rely entirely on the
  topology gate — the existing `test_caddy_invariant.py` asserts the
  public edge 404's `/api/admin/*`. A new invariant test asserts the
  same for `/api/admin/system-messages*` specifically (defense in
  depth against a future Caddyfile edit that punches a hole).

### SPA — player surface (Settings drawer)

- New "Messages" section in `SettingsDrawer.jsx`, below the existing
  font-size controls. Lists active messages, most-recent first, with
  title + minimal-markdown body + relative timestamp. Empty state:
  "No messages."
- Gear icon in `TopBar.jsx` gets a small amber dot when at least one
  message's `published_at` is newer than `localStorage.sentinel.messagesLastSeenAt`.
- Opening the drawer fires `markMessagesSeen()` which updates the
  localStorage timestamp; the dot clears.
- `messagesLastSeenAt` lives in `uiStore` alongside `fontSize`,
  persisted via the existing `zustand/middleware/persist` config.

### SPA — admin surface (tailnet only)

- New page at `/admin/messages` rendered by
  `apps/sentinel-ui/src/pages/AdminMessages.jsx`.
- Compose form (title, body, category select, pinned toggle, optional
  expires_at).
- Active-messages list with edit + delete (soft) + pin-toggle buttons.
- Includes soft-deleted messages in a separate "Deleted" section so
  the operator can see what was hidden (no undelete in v1).
- Wired into `App.jsx` router via `<Route path="/admin/messages"
  component={AdminMessages} />`.
- The route is reachable from the public SPA bundle too, but
  - the page doesn't break if the admin endpoints are unavailable
    (POST returns 404 from the public edge → renders an error state).
  - the GET feed works from the public surface, so testers visiting
    `/admin/messages` accidentally would see the public feed in
    read-only fallback (acceptable; the URL is operator-only by
    convention, not by force).

### Minimal Markdown

Reuse the existing parser from `NarrativeText.jsx` (`*italic*`,
`**bold**`, `***bold-italic***`, `[label](url)`). No headings, no
code blocks, no lists. Keeps the surface and the codex narrative UI
visually coherent.

### Read-state model

Browser-side only. `localStorage.sentinel.messagesLastSeenAt = <ISO>`
on drawer open. The dot fires when any message's `published_at >
messagesLastSeenAt`. No server-side read receipts.

Clearing localStorage = "show me everything as new again" — acceptable
for v1.

## Open Questions

All 8 questions from the draft conversation are resolved:

| # | Question | Resolution |
|---|---|---|
| 1 | Broadcast vs targeted | Broadcast (everyone sees the same feed) |
| 2 | Read-state tracking | Browser-side `messagesLastSeenAt`, gear dot for any-unread |
| 3 | Operator auth shape | Tailnet routing IS the credential; no token/basic_auth needed |
| 4 | Markdown body | Minimal (reuse `NarrativeText.jsx` parser) |
| 5 | Delete semantics | Soft delete (`deleted_at` field; filter on read) |
| 6 | Pinning | Yes — `pinned: bool`, sorted first |
| 7 | Expiry | Yes — optional `expires_at`, filter on read |
| 8 | Gear dot visual | Small amber dot top-right of gear, cleared on drawer-open |

## Acceptance Criteria

- [x] `GET /api/system-messages` returns the active feed (within gate)
- [x] `POST /api/admin/system-messages` creates a message
- [x] `PATCH /api/admin/system-messages/{id}` partial updates
- [x] `DELETE /api/admin/system-messages/{id}` soft-deletes
- [x] Storage: `data/state/core/system_messages/<id>.json` per message
- [x] Feed sort order: pinned-first, then `published_at` desc
- [x] Feed filter: hides soft-deleted + expired
- [x] Settings drawer has "Messages" section listing the feed
- [x] Gear icon shows an amber dot when there's an unread message
- [x] Opening the drawer clears the dot via localStorage update
- [x] Admin page at `/admin/messages` with compose / list / edit / delete / pin
- [x] Minimal Markdown rendering (italic / bold / links)
- [x] Caddy invariant test asserts `/api/admin/system-messages*` is
      blocked from public edge

## Out of Scope (v1)

- Per-tester targeting (broadcast only)
- Server-side per-message read receipts
- Real-time push (no SSE/WebSocket; poll-on-page-load)
- Undelete (soft-deleted stays soft-deleted; can be re-created)
- Audit log of admin actions (no who-deleted-what trail)
- Tester-to-operator messages (the existing `/alpha/feedback/` form
  covers that path)
- Translations / locale
- Reactions / replies / threading

## Cross-links

- Related ADRs: ADR 0001 (canonical-state-on-disk storage pattern);
  ADR 0003 (gate topology + the public-edge 404 rule for
  `/api/admin/*`)
- Related RFCs: RFC 0001 (the silhouette flip — the convention this
  RFC follows: draft-in-conversation, accepted-on-implementation)
- BACKLOG items: none (this surface was new)
- Memory: `project_rfc_lifecycle_convention` (the workflow this RFC
  uses); `feedback_visual_iteration_inline_svg` (the iteration
  pattern the SPA surface inherits)

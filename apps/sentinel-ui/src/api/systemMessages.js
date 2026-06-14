// System-messages API helpers — operator-to-cohort channel (RFC 0002).
//
// The public feed (`listMessages`) is callable from any tester surface — it
// reads soft-deleted/expired-filtered messages from /api/system-messages and
// is gated only by the same `basic_auth` that fronts the whole app.
//
// The admin helpers (create/update/delete + listAll) hit `/api/admin/...`,
// which the Caddyfile 404s on the public edge. They only work over tailnet —
// `tests/test_caddy_invariant.py` enforces that. No auth header is sent
// because topology IS the credential.

import { apiClient } from './client';

export async function listMessages() {
  const data = await apiClient.get('/system-messages');
  return data.messages;
}

export async function listAllMessages() {
  const data = await apiClient.get('/admin/system-messages');
  return data.messages;
}

export async function createMessage({ title, body, category = 'info', pinned = false, expires_at = null }) {
  return apiClient.post('/admin/system-messages', {
    title,
    body,
    category,
    pinned,
    expires_at,
  });
}

export async function updateMessage(id, patch) {
  return apiClient.patch(`/admin/system-messages/${id}`, patch);
}

export async function deleteMessage(id) {
  return apiClient.delete(`/admin/system-messages/${id}`);
}

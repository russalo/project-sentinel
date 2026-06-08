// Per-world session tokens (ADR 0003 Slice A + per-tester reauth).
//
// World creation returns a `sessionToken` that authorizes turns / resume /
// delete on that one world. ADR 0002 lets one browser run several concurrent
// isolated worlds, so a single shared cookie would clobber — instead we keep
// each token in localStorage keyed by world_id and send it as the
// `X-Sentinel-World-Token` header on world-scoped requests. Surviving a refresh
// is the point: reopening /w/<id> in the same browser still has the token.
//
// When the backend has no secret configured (the default, and all of local /
// tailnet), creation returns no token, nothing is stored, and the header is
// simply absent — the anonymous flow is unchanged.
//
// Recovery (per-tester reauth, 2026-06-08): when the token is missing or
// stale (cleared localStorage, fresh device, expired) a world-scoped request
// 401s. The SPA calls `reauth(worldId)` below — POST /api/world/{id}/reauth
// — which carries the browser's already-cached basic_auth header (same-origin
// requests do this automatically). The backend confirms the basic_auth user
// matches the world's creator, mints a fresh username-bound token, and
// returns it; the SPA stores it and retries the original call. No user
// intervention required; the click that opens the URL is the click that
// recovers.

import { apiClient } from './client';

const KEY_PREFIX = 'sentinel.worldToken.';

const storage = () => {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    // localStorage can throw in private-mode / sandboxed contexts. Degrade to
    // "no stored token" rather than crashing the app.
    return null;
  }
};

// Even when localStorage is *present*, the individual ops can throw —
// setItem hits QuotaExceededError, and Safari private mode throws on write —
// so guard each call. A failed token write must never crash world creation;
// it just means resume/turns won't carry the token (acceptable: enforcement is
// off in the only contexts where storage is unavailable, and the worst case is
// a re-auth, not a crash).
export function setWorldToken(worldId, token) {
  if (!worldId || !token) return;
  const s = storage();
  if (!s) return;
  try {
    s.setItem(KEY_PREFIX + worldId, token);
  } catch {
    /* quota / private-mode / locked-down — degrade to "no stored token" */
  }
}

export function getWorldToken(worldId) {
  if (!worldId) return null;
  const s = storage();
  if (!s) return null;
  try {
    return s.getItem(KEY_PREFIX + worldId);
  } catch {
    return null;
  }
}

export function clearWorldToken(worldId) {
  if (!worldId) return;
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(KEY_PREFIX + worldId);
  } catch {
    /* nothing to do — best-effort cleanup */
  }
}

// Header object for a world-scoped request — empty when no token is held, so
// spreading it is always safe: `{ ...worldTokenHeader(id) }`.
export function worldTokenHeader(worldId) {
  const token = getWorldToken(worldId);
  return token ? { 'X-Sentinel-World-Token': token } : {};
}

// Re-mint a per-world token using the browser's already-cached basic_auth
// identity. Called by useWorldHydration on a 401 from a world-scoped request.
// POST body is empty — the basic_auth header is sent automatically by the
// browser on same-origin requests. Returns the fresh token on success (also
// stores it via setWorldToken); throws on non-200, with `err.status` set so
// the caller can distinguish 401 (no basic_auth reached the backend, e.g.
// dev / unenforced) from 403 (basic_auth user isn't this world's creator)
// from a transient network failure.
export async function reauth(worldId) {
  const data = await apiClient.post(`/world/${worldId}/reauth`, {});
  // Defensively validate the response shape — apiClient only guarantees
  // res.ok + JSON parsed, not that the JSON is the shape we expect. A
  // malformed payload (e.g. a proxy injecting an HTML error page parsed as
  // text/json by mistake, or a backend regression returning `null`) should
  // surface as a recoverable error in useWorldHydration's catch, not a
  // TypeError on `data.token`. (gemini-medium on PR #125.)
  if (!data || typeof data !== 'object') {
    const err = new Error('Invalid reauth response');
    err.status = 502;
    throw err;
  }
  const token = data.token;
  if (token) setWorldToken(worldId, token);
  return token;
}

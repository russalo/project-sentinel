// Per-world session tokens (ADR 0003 Slice A).
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

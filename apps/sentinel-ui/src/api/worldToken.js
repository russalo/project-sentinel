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

export function setWorldToken(worldId, token) {
  if (!worldId || !token) return;
  const s = storage();
  if (s) s.setItem(KEY_PREFIX + worldId, token);
}

export function getWorldToken(worldId) {
  if (!worldId) return null;
  const s = storage();
  return s ? s.getItem(KEY_PREFIX + worldId) : null;
}

export function clearWorldToken(worldId) {
  if (!worldId) return;
  const s = storage();
  if (s) s.removeItem(KEY_PREFIX + worldId);
}

// Header object for a world-scoped request — empty when no token is held, so
// spreading it is always safe: `{ ...worldTokenHeader(id) }`.
export function worldTokenHeader(worldId) {
  const token = getWorldToken(worldId);
  return token ? { 'X-Sentinel-World-Token': token } : {};
}

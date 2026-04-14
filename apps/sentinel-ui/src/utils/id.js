// ID generation utility.
//
// Why a utility instead of calling `crypto.randomUUID()` directly:
// the Web Crypto API only exposes `randomUUID` in "secure contexts"
// (HTTPS or localhost). When the dev build is served over plain
// HTTP at a tailnet / LAN IP, the browser considers the origin
// insecure and `crypto.randomUUID` is undefined — any direct call
// throws TypeError.
//
// The original fix lived in main.jsx as a global polyfill that
// mutated `globalThis.crypto`, but that approach is brittle:
// `globalThis.crypto` is read-only in strict mode, native Crypto
// objects may be non-extensible on some targets, and ES module
// hoisting means any module that touches `crypto.randomUUID` at
// import-evaluation time would crash before the polyfill runs.
//
// Exporting a utility function avoids all of that: every caller
// goes through this boundary, there's no global patching, and
// import order doesn't matter.
//
// The fallback branch is NOT cryptographically strong — these IDs
// are React `key` props and chat message identifiers, never
// security tokens. When the native `crypto.randomUUID` is
// available (production HTTPS, localhost dev), we use it.

export function newId() {
  if (
    typeof globalThis.crypto !== 'undefined' &&
    typeof globalThis.crypto.randomUUID === 'function'
  ) {
    return globalThis.crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

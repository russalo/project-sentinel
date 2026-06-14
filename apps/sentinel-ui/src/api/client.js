const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

// Errors thrown from apiClient carry the HTTP status code on `.status` so
// callers can branch on 401 (per-tester reauth flow) without re-implementing
// fetch. The legacy `API error: <code>` message is preserved for any caller
// that was stringifying err.message.
function makeApiError(status) {
  const err = new Error(`API error: ${status}`);
  err.status = status;
  return err;
}

// Each method accepts an optional `{ headers }` so callers can attach the
// per-world session token (ADR 0003). Headers default to empty, so existing
// callers are unaffected.
export const apiClient = {
  async get(endpoint, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, { headers });
    if (!res.ok) throw makeApiError(res.status);
    return res.json();
  },

  async post(endpoint, body, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      // Spread caller headers first so the JSON Content-Type can't be clobbered.
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw makeApiError(res.status);
    return res.json();
  },

  async patch(endpoint, body, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'PATCH',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw makeApiError(res.status);
    return res.json();
  },

  async delete(endpoint, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE', headers });
    if (!res.ok) throw makeApiError(res.status);
    const text = await res.text();
    return text ? JSON.parse(text) : {};
  },
};

export { API_BASE };

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

// Each method accepts an optional `{ headers }` so callers can attach the
// per-world session token (ADR 0003). Headers default to empty, so existing
// callers are unaffected.
export const apiClient = {
  async get(endpoint, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, { headers });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },

  async post(endpoint, body, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },

  async delete(endpoint, { headers } = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE', headers });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    const text = await res.text();
    return text ? JSON.parse(text) : {};
  },
};

export { API_BASE };

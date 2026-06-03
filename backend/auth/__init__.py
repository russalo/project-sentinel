"""Access layer for the public/closed-beta edge (ADR 0003).

Two opt-in controls, both disabled by default so local & tailnet play stays
anonymous and unthrottled (ADR 0003: "the gate bites only at the public edge"):

- ``world_token`` — stateless per-world HMAC session tokens (no server store).
- ``access`` — the enforcement helper handlers call once they've resolved a
  world's authoritative id.

Rate limiting lives in ``backend.ratelimit`` (a separate concern); the edge
invite gate + systemd live at the Caddy/ops layer (ADR 0003 Slice C).
"""

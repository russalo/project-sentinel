"""Shared text-safety helpers for the Inference Node + backend.

The apply_world_update schema rejects control / RTL-override / zero-width bytes in
``log_entry`` and in string ``data`` (red-team #1c). Every producer of those
fields must scrub BEFORE the payload reaches ``validate_payload``, or a legit turn
whose narrative / world_name / username carried a stray byte would be rejected
(a 502 on session creation / turn write). This module is the single canonical
scrub for the engine + backend so the fact-extractor and the session-payload
builder can't drift apart.

Kept in sync with:
  - ``schemas/apply_world_update.schema.json`` → ``#/$defs/noControlChars``
  - ``mcp-servers/fs-manager/server.py`` → ``_CONTROL_BYTE_RE`` (a separate node,
    so it carries its own copy by design — the filesystem firewall).
"""

import re

# C0 control bytes except tab (\x09) and newline (\x0a); DEL; bidi RTL overrides
# (U+202A–202E) and isolates (U+2066–2069); zero-width chars (U+200B–200D); BOM.
CONTROL_BYTE_RE = re.compile(
    r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069\u200b-\u200d\ufeff]"
)


def scrub_control_bytes(text: str) -> str:
    """Strip control/RTL/zero-width bytes from operator- and corpus-facing text."""
    return CONTROL_BYTE_RE.sub("", text)

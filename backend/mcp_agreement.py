"""Cutover config-agreement check (ADR 0002 / Path A-A2).

The per-world cutover requires the backend **and both MCP servers** to agree on
``SENTINEL_WORLDS_ROOT``. A split-brain config — backend routes per-world but an
MCP server still writes the shared tree — is silently corrupting: writes land in
the wrong tree and the new session 400s on its next turn.

git-sync disagreement is already caught loudly at session creation (``init_world``
returns ``skipped`` → the route 502s). This closes the symmetric **fs-manager**
gap by checking, at backend startup, that both servers report ``worlds_root:
true`` in ``/health`` whenever the backend itself is in per-world mode. Both MCP
servers expose that flag for exactly this purpose.

No-op when ``SENTINEL_WORLDS_ROOT`` is unset (the default) — shared mode needs no
agreement, and dev/test setups without the MCP servers running aren't pinged.

Residual (deferred — see docs/BACKLOG.md): this checks per-world *presence*
(``worlds_root: true`` on both), not that all three are pointed at the **same**
root path. A misconfig where the backend has ``/a`` but an MCP server has ``/b``
would pass here yet still split-brain. Catching that needs ``/health`` to expose
a root *identity* to compare — a protocol change with real symlink/mount-
comparison fragility (a false mismatch would wrongly refuse a valid deploy).
The common misconfig (one service per-world, another shared) **is** caught; the
same-config-everywhere invariant is otherwise enforced operationally by Slice C's
systemd units setting one env value for all three.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from .config import Settings

logger = logging.getLogger(__name__)


def _default_fetch(url: str, *, timeout: float = 5.0) -> dict:
    """GET ``url`` and parse the JSON body. Raises on transport/parse failure.

    Only ``http(s)`` is allowed — the URLs are operator config (the MCP base
    URLs), not user input, but pinning the scheme keeps a misconfigured
    ``file://`` from reading a local file instead of failing loudly.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing non-HTTP health URL: {url!r}")
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (scheme pinned above)
        return json.loads(resp.read().decode("utf-8"))


def verify_world_mode_agreement(settings: Settings, *, fetch=_default_fetch) -> None:
    """Refuse to start in a split-brain per-world config.

    When ``settings.worlds_root`` is set, assert both MCP servers report
    ``worlds_root: true`` in ``/health``; raise ``RuntimeError`` if either
    disagrees or is unreachable. No-op in shared mode. ``fetch`` is injectable
    for tests.
    """
    if not settings.worlds_root:
        return

    for name, base_url in (
        ("fs-manager", settings.fs_manager_url),
        ("git-sync", settings.git_sync_url),
    ):
        url = f"{base_url.rstrip('/')}/health"
        try:
            body = fetch(url)
        except Exception as exc:
            raise RuntimeError(
                f"per-world mode is on (SENTINEL_WORLDS_ROOT set) but {name} "
                f"/health is unreachable at {url}: {exc}. All three services must "
                f"be up and agree before the cutover."
            ) from exc
        # Strict `is True` — the /health contract is a real bool; a truthy
        # non-bool (e.g. the string "false", or 1) must NOT be read as agreement.
        if not (isinstance(body, dict) and body.get("worlds_root") is True):
            raise RuntimeError(
                f"per-world mode is on (SENTINEL_WORLDS_ROOT set) but {name} "
                f"reports worlds_root=false — the services disagree on per-world "
                f"mode. Set SENTINEL_WORLDS_ROOT to the same value for the backend, "
                f"fs-manager, and git-sync before starting."
            )
    logger.info(
        "Per-world mode agreement OK — fs-manager and git-sync both report "
        "worlds_root=true."
    )

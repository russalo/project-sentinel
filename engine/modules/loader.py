"""Module discovery + loading (ADR-0005 / RFC-0005).

Core modules ship with the engine under
``engine/modules/<subsystem>/<impl>/manifest.toml``. ``discover_modules``
scans that tree; ``load_module`` resolves a module by name into a
``LoadedModule`` (manifest + read prompt-fragment text), going through
the process-lifetime registry cache.

Community-module discovery (under ``data/lore/community/<pack>/modules/``)
is deferred to a later RFC; the loader is structured so that path slots
in without reshaping the API — ``discover_modules`` would gain an
optional ``data_dir`` to also scan community trees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest import ManifestError, ModuleManifest
from .registry import registry

# Core modules live alongside this package: engine/modules/<subsystem>/<impl>/
_CORE_MODULES_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class LoadedModule:
    """A manifest plus its resolved (read-from-disk) contributions.

    ``prompt_fragment_text`` is the module's DM-prompt contribution with
    trailing newlines stripped — so a conventionally newline-terminated
    ``.md`` file still composes byte-cleanly into the assembled prompt.
    None when the module declares no ``prompt_fragment``.
    """

    manifest: ModuleManifest
    manifest_dir: Path
    prompt_fragment_text: str | None


def discover_modules() -> dict[str, Path]:
    """Return ``{module_name: manifest_path}`` for all core modules.

    Walks ``engine/modules/*/*/manifest.toml`` (the two glob levels are
    ``<subsystem>/<impl>``); package dirs without a nested
    ``*/manifest.toml`` don't match. Raises ManifestError if two
    manifests declare the same module name (an authoring mistake we want
    loud, not last-wins).

    The scan result is cached on the registry — repeated calls (e.g. one
    per module on a cold multi-module load) reuse the map rather than
    re-walking the tree (gemini-medium on PR #144). ``registry.clear()``
    forces a fresh scan.
    """
    cached = registry.get_discovery()
    if cached is not None:
        return cached

    found: dict[str, Path] = {}
    for manifest_path in sorted(_CORE_MODULES_ROOT.glob("*/*/manifest.toml")):
        manifest = ModuleManifest.from_toml_file(manifest_path)
        if manifest.name in found:
            raise ManifestError(
                f"duplicate module name {manifest.name!r}: "
                f"{found[manifest.name]} and {manifest_path}"
            )
        found[manifest.name] = manifest_path
    registry.set_discovery(found)
    return found


def load_module(name: str) -> LoadedModule:
    """Resolve a module by name into a LoadedModule, via the registry cache.

    Raises ManifestError (a ValueError subclass) if the name is unknown
    or the prompt fragment it references is missing.
    """
    cached = registry.get(name)
    if cached is not None:
        return cached

    manifests = discover_modules()
    manifest_path = manifests.get(name)
    if manifest_path is None:
        raise ManifestError(f"unknown module {name!r}; discovered: {sorted(manifests)}")

    manifest = ModuleManifest.from_toml_file(manifest_path)
    manifest_dir = manifest_path.parent

    prompt_text: str | None = None
    if manifest.prompt_fragment:
        fragment_path = manifest_dir / manifest.prompt_fragment
        if not fragment_path.exists():
            raise ManifestError(
                f"{manifest_path}: prompt_fragment {manifest.prompt_fragment!r} "
                f"not found at {fragment_path}"
            )
        # rstrip trailing newlines so a conventionally newline-terminated
        # .md composes byte-identically (the assembly joins with "\n\n").
        prompt_text = fragment_path.read_text(encoding="utf-8").rstrip("\n")

    loaded = LoadedModule(
        manifest=manifest,
        manifest_dir=manifest_dir,
        prompt_fragment_text=prompt_text,
    )
    registry.put(name, loaded)
    return loaded

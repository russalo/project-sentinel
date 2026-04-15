"""Load World Generation Layer 2 preset content bundles.

Presets live under ``data/lore/core/presets/`` as TOML files, one file
per preset. Each file has at minimum a ``name`` and a
``prompt_fragment`` — the authored multi-sentence paragraph the DM
intro prompt injects as a WORLD FOUNDATIONS block (see
``engine.agents.dm._format_preset_block``). Regions additionally sit
under a genre subfolder so ``regions/fantasy/the-breach.toml`` and a
hypothetical ``regions/horror/the-breach.toml`` can coexist.

Directory layout::

    data/lore/core/presets/
      genres/      <slug>.toml
      personas/    <slug>.toml
      moods/       <slug>.toml
      regions/<genre>/<slug>.toml

The loader is intentionally lenient: a missing file returns ``None``
and a missing ``prompt_fragment`` field returns ``None``. That way a
session creation request with an unrecognised genre or a newly-added
frontend option just silently falls through to the Layer 1 free-form
label handling in the engine — the frontend does not need to know
which presets have content on the backend side.

No caching yet. These files are small (a few KB each) and read at
most once per session creation. If profiling later shows the TOML
parse cost is meaningful, add an LRU at the module level.
"""

import re
import tomllib
from pathlib import Path

# Preset types the loader knows about. Kept as a tuple (not a set)
# so the lookup order in error messages is stable.
_PRESET_TYPES: tuple[str, ...] = ("genres", "personas", "moods", "regions")


def _slugify(value: str) -> str:
    """Normalize a display string into a preset file slug.

    ``"The Breach"`` → ``"the-breach"``. ``"Sci-Fi"`` → ``"sci-fi"``.
    Any run of non-alphanumeric characters becomes a single hyphen;
    the result is lowercased and stripped of leading/trailing
    hyphens. Mirrors the file naming used under
    ``data/lore/core/presets/`` so frontend display strings can map
    one-to-one onto preset files without an intermediate catalog.
    """
    lowered = value.strip().lower()
    # Replace any non-alphanumeric run with a single hyphen.
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered)
    return collapsed.strip("-")


def load_preset(
    preset_root: Path,
    preset_type: str,
    preset_id: str,
    *,
    genre: str | None = None,
) -> dict | None:
    """Load a single preset file and return its parsed contents.

    Parameters
    ----------
    preset_root
        Absolute path to ``data/lore/core/presets/``. The caller
        supplies this explicitly so tests can point at fixture
        directories and so the backend can pass
        ``settings.data_dir / "lore" / "core" / "presets"``.
    preset_type
        One of ``genres`` / ``personas`` / ``moods`` / ``regions``.
    preset_id
        The file slug (without extension). For ``regions``, this is
        the region slug only; the ``genre`` kwarg selects the
        subfolder.
    genre
        Required only when ``preset_type == "regions"``. Selects the
        per-genre subfolder. Ignored otherwise.

    Returns
    -------
    dict | None
        The parsed TOML as a dict, or ``None`` if the file does not
        exist, the preset type is unknown, or the slug is empty.
        Parse errors on a present file are surfaced by raising —
        a malformed preset is a programmer error worth noticing, not
        a reason to silently fall through.
    """
    if not preset_id:
        return None
    if preset_type not in _PRESET_TYPES:
        return None

    slug = _slugify(preset_id)
    if not slug:
        return None

    if preset_type == "regions":
        if not genre:
            return None
        genre_slug = _slugify(genre)
        if not genre_slug:
            return None
        path = preset_root / "regions" / genre_slug / f"{slug}.toml"
    else:
        path = preset_root / preset_type / f"{slug}.toml"

    if not path.is_file():
        return None

    with path.open("rb") as f:
        return tomllib.load(f)


def get_prompt_fragment(
    preset_root: Path,
    preset_type: str,
    preset_id: str | None,
    *,
    genre: str | None = None,
) -> str | None:
    """Convenience wrapper: load a preset and return its prompt fragment.

    Returns ``None`` when the preset file cannot be found, when the
    ``preset_id`` is ``None``/empty, or when the loaded file is
    missing the ``prompt_fragment`` field. All three cases collapse
    to "no rich content available, fall through to the bare label"
    from the caller's perspective, which is what the engine's
    ``_creation_context_lines`` suppression rule needs.

    Whitespace on the returned fragment is stripped so downstream
    formatting (the ``GENRE:`` / ``STARTING REGION:`` headers in
    ``_format_preset_block``) does not inherit authoring artefacts
    like trailing newlines from multiline TOML strings.
    """
    if preset_id is None:
        return None
    preset = load_preset(preset_root, preset_type, preset_id, genre=genre)
    if preset is None:
        return None
    fragment = preset.get("prompt_fragment")
    if not isinstance(fragment, str):
        return None
    stripped = fragment.strip()
    return stripped if stripped else None

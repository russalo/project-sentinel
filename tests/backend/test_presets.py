"""Unit tests for backend.presets — the World Generation Layer 2
preset-content loader.

Tests do not touch the repo's real ``data/lore/core/presets/`` tree;
each test writes a small fixture under a tmpdir and points the loader
at it. This keeps the tests independent of the authoring work that
ships alongside this PR.
"""

from pathlib import Path

import pytest

from backend.presets import _slugify, get_prompt_fragment, load_preset


def _write_preset(root: Path, rel_path: str, content: str) -> None:
    """Write a TOML fixture under the preset root at ``rel_path``."""
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)


# ── _slugify ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "given,expected",
    [
        ("The Breach", "the-breach"),
        ("Sci-Fi", "sci-fi"),
        ("station alpha", "station-alpha"),
        ("  Dusty Gulch  ", "dusty-gulch"),
        ("Asteroid  Field", "asteroid-field"),
        ("Neural  Net!!", "neural-net"),
        ("CORPORATE TOWER", "corporate-tower"),
        ("", ""),
        ("---", ""),
    ],
)
def test_slugify_normalizes_display_strings(given: str, expected: str) -> None:
    assert _slugify(given) == expected


# ── load_preset ─────────────────────────────────────────────────────


def test_load_preset_returns_parsed_toml(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "genres/fantasy.toml",
        'name = "Fantasy"\nprompt_fragment = "A dark fantasy world."\n',
    )
    preset = load_preset(tmp_path, "genres", "fantasy")
    assert preset == {"name": "Fantasy", "prompt_fragment": "A dark fantasy world."}


def test_load_preset_slugifies_the_id(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "genres/sci-fi.toml",
        'name = "Sci-Fi"\nprompt_fragment = "A spacefaring setting."\n',
    )
    # Caller passes the display string; loader normalizes it.
    preset = load_preset(tmp_path, "genres", "Sci-Fi")
    assert preset is not None
    assert preset["name"] == "Sci-Fi"


def test_load_preset_returns_none_for_unknown_type(tmp_path: Path) -> None:
    assert load_preset(tmp_path, "widgets", "whatever") is None


def test_load_preset_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert load_preset(tmp_path, "genres", "fantasy") is None


def test_load_preset_returns_none_for_empty_id(tmp_path: Path) -> None:
    assert load_preset(tmp_path, "genres", "") is None


def test_load_preset_returns_none_when_slug_is_all_punctuation(
    tmp_path: Path,
) -> None:
    # "---" slugifies to "" which should be treated as no preset.
    assert load_preset(tmp_path, "genres", "---") is None


def test_load_preset_regions_require_genre(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "regions/fantasy/the-breach.toml",
        'name = "The Breach"\nprompt_fragment = "A crater in the land."\n',
    )
    # Without the genre kwarg, a region lookup returns None even
    # when the file exists.
    assert load_preset(tmp_path, "regions", "The Breach") is None
    # With the genre kwarg, it resolves.
    preset = load_preset(tmp_path, "regions", "The Breach", genre="fantasy")
    assert preset is not None
    assert preset["name"] == "The Breach"


def test_load_preset_regions_slugify_the_genre_too(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "regions/sci-fi/station-alpha.toml",
        'name = "Station Alpha"\nprompt_fragment = "Orbital platform."\n',
    )
    # Frontend sends "sci-fi" which is already slug-shaped, but
    # the loader should be tolerant of any casing.
    preset = load_preset(tmp_path, "regions", "Station Alpha", genre="Sci-Fi")
    assert preset is not None
    assert preset["name"] == "Station Alpha"


def test_load_preset_raises_on_malformed_toml(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "genres/broken.toml",
        'name = "Broken\nprompt_fragment = oops\n',  # unterminated string
    )
    # Malformed preset is a programmer error — surface it loudly
    # rather than silently returning None, per the loader docstring.
    with pytest.raises(Exception):
        load_preset(tmp_path, "genres", "broken")


# ── get_prompt_fragment ─────────────────────────────────────────────


def test_get_prompt_fragment_returns_stripped_string(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "personas/oracle.toml",
        '''name = "Oracle"
prompt_fragment = """

The Oracle speaks in fragments of futures half-seen.

"""
''',
    )
    fragment = get_prompt_fragment(tmp_path, "personas", "oracle")
    # Leading/trailing whitespace stripped by the loader.
    assert fragment == "The Oracle speaks in fragments of futures half-seen."


def test_get_prompt_fragment_returns_none_for_missing_preset(tmp_path: Path) -> None:
    assert get_prompt_fragment(tmp_path, "personas", "oracle") is None


def test_get_prompt_fragment_returns_none_for_none_id(tmp_path: Path) -> None:
    assert get_prompt_fragment(tmp_path, "personas", None) is None


def test_get_prompt_fragment_returns_none_when_field_missing(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        "personas/nameless.toml",
        'name = "Nameless"\n',  # no prompt_fragment field
    )
    assert get_prompt_fragment(tmp_path, "personas", "nameless") is None


def test_get_prompt_fragment_returns_none_when_field_is_empty_string(
    tmp_path: Path,
) -> None:
    _write_preset(
        tmp_path,
        "personas/blank.toml",
        'name = "Blank"\nprompt_fragment = "   \\n  "\n',
    )
    # Whitespace-only fragments collapse to None after stripping —
    # a blank fragment is not useful content for the DM prompt.
    assert get_prompt_fragment(tmp_path, "personas", "blank") is None


def test_get_prompt_fragment_threads_genre_through_for_regions(
    tmp_path: Path,
) -> None:
    _write_preset(
        tmp_path,
        "regions/fantasy/the-breach.toml",
        'name = "The Breach"\nprompt_fragment = "A crater in the land."\n',
    )
    _write_preset(
        tmp_path,
        "regions/horror/the-breach.toml",
        'name = "The Breach"\nprompt_fragment = "A thin place between worlds."\n',
    )
    # Same region slug, different genres, distinct content.
    fantasy = get_prompt_fragment(
        tmp_path, "regions", "The Breach", genre="fantasy"
    )
    horror = get_prompt_fragment(
        tmp_path, "regions", "The Breach", genre="horror"
    )
    assert fantasy == "A crater in the land."
    assert horror == "A thin place between worlds."


# ── shipped preset content: smoke tests against the real tree ─────


@pytest.fixture
def real_preset_root() -> Path:
    """Point at the repo's actual preset tree.

    Unlike the tmpdir tests above, these read the content that ships
    with the Layer 2 PR. They exist to catch authoring regressions:
    a broken TOML file, a missing prompt_fragment, a typoed slug.
    """
    return Path(__file__).resolve().parents[2] / "data" / "lore" / "core" / "presets"


@pytest.mark.parametrize(
    "slug",
    ["fantasy", "sci-fi", "western", "horror", "cyberpunk"],
)
def test_shipped_genre_presets_load_with_prompt_fragments(
    real_preset_root: Path, slug: str
) -> None:
    fragment = get_prompt_fragment(real_preset_root, "genres", slug)
    assert fragment is not None and len(fragment) > 50


@pytest.mark.parametrize(
    "slug",
    ["oracle", "chronicler", "cowboy"],
)
def test_shipped_persona_presets_load_with_prompt_fragments(
    real_preset_root: Path, slug: str
) -> None:
    fragment = get_prompt_fragment(real_preset_root, "personas", slug)
    assert fragment is not None and len(fragment) > 50


@pytest.mark.parametrize(
    "slug",
    ["neutral", "ominous", "lore-heavy", "gritty", "humorous", "fast-paced"],
)
def test_shipped_mood_presets_load_with_prompt_fragments(
    real_preset_root: Path, slug: str
) -> None:
    fragment = get_prompt_fragment(real_preset_root, "moods", slug)
    assert fragment is not None and len(fragment) > 30


@pytest.mark.parametrize(
    "genre,region",
    [
        ("fantasy", "The Breach"),
        ("fantasy", "Thornwatch"),
        ("fantasy", "Crown City"),
        ("fantasy", "The Wastes"),
        ("sci-fi", "Station Alpha"),
        ("sci-fi", "Mars Colony"),
        ("sci-fi", "Outer Ring"),
        ("sci-fi", "Asteroid Field"),
        ("western", "Dusty Gulch"),
        ("western", "Frontier Town"),
        ("western", "Desert Wasteland"),
        ("western", "Gold Rush Camp"),
        ("horror", "Abandoned Manor"),
        ("horror", "Dark Forest"),
        ("horror", "Cursed Village"),
        ("horror", "Underground Tomb"),
        ("cyberpunk", "Neon District"),
        ("cyberpunk", "Corporate Tower"),
        ("cyberpunk", "Undercity"),
        ("cyberpunk", "Neural Net"),
    ],
)
def test_shipped_region_presets_load_with_prompt_fragments(
    real_preset_root: Path, genre: str, region: str
) -> None:
    fragment = get_prompt_fragment(
        real_preset_root, "regions", region, genre=genre
    )
    assert fragment is not None and len(fragment) > 50

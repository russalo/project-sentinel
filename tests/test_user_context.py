"""
Project Sentinel — user-context MCP Server Tests

Verifies the storage, retrieval, deletion, export, and pronoun-validation
logic of the user-context MCP server without requiring a running HTTP server.

Run locally:
    pip install fastapi uvicorn pytest
    pytest tests/test_user_context.py -v
"""

import json
import re
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the helpers under test directly from the server module.
# We patch STORAGE_PATH so tests never touch the real data/ directory.
# ---------------------------------------------------------------------------

import sys

SERVER_MODULE_PATH = Path(__file__).parent.parent / "mcp-servers" / "user-context"
sys.path.insert(0, str(SERVER_MODULE_PATH))

import server as uc_server  # noqa: E402  (import after sys.path modification)

CATEGORIES = uc_server.CATEGORIES
CATEGORY_LABELS = uc_server.CATEGORY_LABELS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path):
    """Redirect the server's STORAGE_PATH to a temporary file for isolation."""
    storage = tmp_path / "user_context.json"
    with patch.object(uc_server, "STORAGE_PATH", storage):
        yield storage


# ---------------------------------------------------------------------------
# _contains_prohibited_pronouns
# ---------------------------------------------------------------------------


def test_no_prohibited_pronouns_in_neutral_text():
    assert uc_server._contains_prohibited_pronouns("The user prefers dark mode.") == []


def test_detects_first_person_pronoun():
    found = uc_server._contains_prohibited_pronouns("I prefer dark mode.")
    assert any(p.lower() == "i" for p in found)


def test_detects_second_person_pronoun():
    found = uc_server._contains_prohibited_pronouns("You should know that the user codes.")
    assert any(p.lower() == "you" for p in found)


def test_detects_possessive_pronoun():
    found = uc_server._contains_prohibited_pronouns("My favourite editor is Neovim.")
    assert any(p.lower() == "my" for p in found)


def test_case_insensitive_detection():
    assert uc_server._contains_prohibited_pronouns("YOUR opinion matters.") != []


# ---------------------------------------------------------------------------
# _load_store / _save_store
# ---------------------------------------------------------------------------


def test_load_store_returns_empty_default_when_missing(tmp_store):
    store = uc_server._load_store()
    assert store == {cat: [] for cat in CATEGORIES}


def test_save_and_reload_roundtrip(tmp_store):
    store = {cat: [] for cat in CATEGORIES}
    store["demographics"].append({"id": "abc", "fact": "The user is based in Lisbon."})
    uc_server._save_store(store)
    reloaded = uc_server._load_store()
    assert reloaded["demographics"][0]["fact"] == "The user is based in Lisbon."


def test_load_store_handles_corrupt_file(tmp_store):
    tmp_store.write_text("NOT VALID JSON", encoding="utf-8")
    store = uc_server._load_store()
    # Should return empty default, not raise
    assert store == {cat: [] for cat in CATEGORIES}


# ---------------------------------------------------------------------------
# _render_context_document
# ---------------------------------------------------------------------------


def _make_store(**overrides) -> dict:
    base = {cat: [] for cat in CATEGORIES}
    base.update(overrides)
    return base


def test_render_includes_all_five_section_headers():
    store = _make_store()
    doc = uc_server._render_context_document(store)
    for label in CATEGORY_LABELS.values():
        assert label in doc, f"Missing section header: {label!r}"


def test_render_empty_category_shows_placeholder():
    store = _make_store()
    doc = uc_server._render_context_document(store)
    assert "(No information recorded.)" in doc


def test_render_fact_appears_as_bullet():
    store = _make_store(
        demographics=[
            {"id": "1", "fact": "The user's name is Russ.", "recorded_at": "2026-01-01T00:00:00Z"}
        ]
    )
    doc = uc_server._render_context_document(store)
    assert "- The user's name is Russ." in doc


def test_render_source_quote_appended():
    store = _make_store(
        demographics=[
            {
                "id": "1",
                "fact": "The user's name is Russ.",
                "recorded_at": "2026-01-01T00:00:00Z",
                "source": "My name is Russ",
            }
        ]
    )
    doc = uc_server._render_context_document(store)
    assert 'Source: "My name is Russ"' in doc


def test_render_sections_in_specified_order():
    store = _make_store()
    doc = uc_server._render_context_document(store)
    positions = [doc.index(label) for label in CATEGORY_LABELS.values()]
    assert positions == sorted(positions), "Sections not in specified order"


def test_render_no_first_person_pronouns_in_output():
    """The rendered document itself must not contain first- or second-person pronouns
    in the structural prose (placeholders, headers). Facts are stored validated."""
    store = _make_store()
    doc = uc_server._render_context_document(store)
    # Check structural text only (exclude quoted sources, which may contain pronouns)
    structural_lines = [
        line for line in doc.splitlines() if not line.strip().startswith('Source:')
    ]
    structural_text = "\n".join(structural_lines)
    prohibited = uc_server._contains_prohibited_pronouns(structural_text)
    assert prohibited == [], f"Structural text contains prohibited pronouns: {prohibited}"


# ---------------------------------------------------------------------------
# FastAPI endpoint integration (using TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_store):
    from fastapi.testclient import TestClient

    return TestClient(uc_server.app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["server"] == "user-context"


def test_store_memory_success(client):
    response = client.post(
        "/tools/store_memory",
        json={"category": "demographics", "fact": "The user is based in Lisbon."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stored"
    assert data["category"] == "demographics"
    assert "id" in data


def test_store_memory_with_source(client):
    response = client.post(
        "/tools/store_memory",
        json={
            "category": "demographics",
            "fact": "The user's name is Russ.",
            "source": "My name is Russ",
        },
    )
    assert response.status_code == 200


def test_store_memory_unknown_category(client):
    response = client.post(
        "/tools/store_memory",
        json={"category": "hobbies", "fact": "The user enjoys hiking."},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNKNOWN_CATEGORY"


def test_store_memory_missing_fact(client):
    response = client.post(
        "/tools/store_memory",
        json={"category": "demographics"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MISSING_FACT"


def test_store_memory_rejects_first_person_pronoun(client):
    response = client.post(
        "/tools/store_memory",
        json={"category": "demographics", "fact": "I prefer dark mode."},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROHIBITED_PRONOUNS"


def test_store_memory_rejects_second_person_pronoun(client):
    response = client.post(
        "/tools/store_memory",
        json={"category": "demographics", "fact": "You said the user codes in Python."},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROHIBITED_PRONOUNS"


def test_list_memories_all_categories(client):
    client.post(
        "/tools/store_memory",
        json={"category": "demographics", "fact": "The user is based in Lisbon."},
    )
    response = client.get("/tools/list_memories")
    assert response.status_code == 200
    memories = response.json()["memories"]
    assert set(memories.keys()) == set(CATEGORIES)
    assert len(memories["demographics"]) == 1


def test_list_memories_filtered_by_category(client):
    client.post(
        "/tools/store_memory",
        json={"category": "instructions", "fact": "The user always prefers concise answers."},
    )
    response = client.get("/tools/list_memories", params={"category": "instructions"})
    assert response.status_code == 200
    assert "instructions" in response.json()["memories"]
    assert len(response.json()["memories"]["instructions"]) == 1


def test_list_memories_unknown_category(client):
    response = client.get("/tools/list_memories", params={"category": "bogus"})
    assert response.status_code == 422


def test_delete_memory_success(client):
    store_resp = client.post(
        "/tools/store_memory",
        json={"category": "demographics", "fact": "The user is based in Lisbon."},
    )
    memory_id = store_resp.json()["id"]

    del_resp = client.request(
        "DELETE",
        "/tools/delete_memory",
        json={"id": memory_id},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    list_resp = client.get("/tools/list_memories", params={"category": "demographics"})
    assert list_resp.json()["memories"]["demographics"] == []


def test_delete_memory_not_found(client):
    response = client.request(
        "DELETE",
        "/tools/delete_memory",
        json={"id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_export_context_returns_document(client):
    client.post(
        "/tools/store_memory",
        json={
            "category": "demographics",
            "fact": "The user's name is Russ.",
            "source": "My name is Russ",
        },
    )
    response = client.get("/tools/export_context")
    assert response.status_code == 200
    doc = response.json()["document"]
    assert "1. Demographics Information" in doc
    assert "The user's name is Russ." in doc
    assert 'Source: "My name is Russ"' in doc


def test_export_context_contains_all_sections(client):
    response = client.get("/tools/export_context")
    assert response.status_code == 200
    doc = response.json()["document"]
    for label in CATEGORY_LABELS.values():
        assert label in doc

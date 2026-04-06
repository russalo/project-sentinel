"""
Project Sentinel — user-context MCP Server

Stores and exports structured facts about a user across AI assistant sessions.
Enables cross-assistant context portability: facts are persisted to a JSON file
and can be exported as a formatted, neutral-language summary document for
injection into a new assistant's context window.

Usage:
    python server.py --port 8013

Dependencies:
    pip install -r requirements.txt
"""

import argparse
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
import uvicorn

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("user-context")

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
STORAGE_PATH = REPO_ROOT / "data" / "user_context.json"

# The five ordered categories defined by the context-import specification.
CATEGORIES = [
    "demographics",
    "interests_preferences",
    "relationships",
    "dated_events",
    "instructions",
]

CATEGORY_LABELS = {
    "demographics": "1. Demographics Information",
    "interests_preferences": "2. Interests & Preferences",
    "relationships": "3. Relationships",
    "dated_events": "4. Dated Events, Projects & Plans",
    "instructions": "5. Instructions",
}

# Regex for detecting first- or second-person pronouns that must not appear
# in exported output (used in validation of stored facts).
_PRONOUN_PATTERN = re.compile(
    r"\b(I|me|my|mine|myself|you|your|yours|yourself)\b", re.IGNORECASE
)

# -------------------------------------------------------------------
# Storage helpers
# -------------------------------------------------------------------


def _load_store() -> dict:
    """Load the persisted memory store from disk, or return an empty default."""
    if STORAGE_PATH.exists():
        try:
            return json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not load user context store: {exc}. Starting fresh.")
    return {cat: [] for cat in CATEGORIES}


def _save_store(store: dict) -> None:
    """Persist the memory store to disk."""
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def _contains_prohibited_pronouns(text: str) -> list[str]:
    """Return all first- or second-person pronouns found in *text*."""
    return _PRONOUN_PATTERN.findall(text)


# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------

app = FastAPI(
    title="Sentinel user-context MCP Server",
    description=(
        "Stores and exports structured user context for cross-assistant memory portability."
    ),
    version="0.1.0",
)


# -------------------------------------------------------------------
# MCP Endpoints
# -------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "server": "user-context", "version": "0.1.0"}


@app.post("/tools/store_memory")
async def store_memory(body: dict) -> dict:
    """
    Store a single fact about the user under the specified category.

    Required fields:
      - category  (str): one of demographics | interests_preferences |
                         relationships | dated_events | instructions
      - fact       (str): neutral-language statement about the user
                          (must not contain first- or second-person pronouns)

    Optional fields:
      - source (str): verbatim quote from the original conversation that
                      justifies this fact
    """
    category: str | None = body.get("category")
    fact: str | None = body.get("fact")
    source: str | None = body.get("source")

    if not category:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_CATEGORY", "detail": "category is required."},
        )
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNKNOWN_CATEGORY",
                "detail": f"Unknown category '{category}'. Valid values: {CATEGORIES}",
            },
        )
    if not fact or not fact.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_FACT", "detail": "fact is required and must not be empty."},
        )

    prohibited = _contains_prohibited_pronouns(fact)
    if prohibited:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROHIBITED_PRONOUNS",
                "detail": (
                    f"fact contains first- or second-person pronouns "
                    f"({prohibited}). Use 'the user' or neutral phrasing instead."
                ),
            },
        )

    store = _load_store()
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "fact": fact.strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if source:
        entry["source"] = source

    store.setdefault(category, []).append(entry)
    _save_store(store)

    logger.info(f"store_memory — category={category} id={entry['id']}")
    return {"status": "stored", "id": entry["id"], "category": category}


@app.get("/tools/list_memories")
async def list_memories(category: str | None = None) -> dict:
    """
    Return all stored memories, optionally filtered to a single category.
    """
    store = _load_store()

    if category is not None:
        if category not in CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "UNKNOWN_CATEGORY",
                    "detail": f"Unknown category '{category}'. Valid values: {CATEGORIES}",
                },
            )
        return {"memories": {category: store.get(category, [])}}

    return {"memories": {cat: store.get(cat, []) for cat in CATEGORIES}}


@app.delete("/tools/delete_memory")
async def delete_memory(body: dict) -> dict:
    """
    Delete a stored memory by its unique ID.

    Required fields:
      - id (str): the UUID returned by store_memory
    """
    memory_id: str | None = body.get("id")
    if not memory_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "MISSING_ID", "detail": "id is required."},
        )

    store = _load_store()
    deleted = False
    for cat in CATEGORIES:
        entries = store.get(cat, [])
        new_entries = [e for e in entries if e.get("id") != memory_id]
        if len(new_entries) < len(entries):
            store[cat] = new_entries
            deleted = True
            break

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "detail": f"No memory found with id '{memory_id}'."},
        )

    _save_store(store)
    logger.info(f"delete_memory — id={memory_id}")
    return {"status": "deleted", "id": memory_id}


@app.get("/tools/export_context")
async def export_context() -> dict:
    """
    Export all stored memories as a structured, neutral-language context document
    suitable for injection into a new AI assistant's context window.

    The exported text uses 'the user' (never first- or second-person pronouns)
    and preserves verbatim source quotes where available.
    """
    store = _load_store()
    document = _render_context_document(store)
    return {"document": document}


# -------------------------------------------------------------------
# Rendering helper (also used directly in tests)
# -------------------------------------------------------------------


def _render_context_document(store: dict) -> str:
    """
    Render the stored memories as a human-readable context document.

    Rules:
    - Section headers follow the numbered format from the specification.
    - Each entry is rendered as a bullet point.
    - Verbatim source quotes (if present) are appended on the next line,
      indented, prefixed with "Source:".
    - Empty sections are included as a placeholder so the structure is always
      predictable for downstream parsers.
    """
    sections: list[str] = []

    for cat in CATEGORIES:
        label = CATEGORY_LABELS[cat]
        entries = store.get(cat, [])

        lines: list[str] = [label]
        if entries:
            for entry in entries:
                lines.append(f"- {entry['fact']}")
                if entry.get("source"):
                    lines.append(f'  Source: "{entry["source"]}"')
        else:
            lines.append("(No information recorded.)")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


# -------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel user-context MCP Server")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--dev", action="store_true", help="Enable development mode (verbose logging)"
    )
    args = parser.parse_args()

    if args.dev:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting user-context on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

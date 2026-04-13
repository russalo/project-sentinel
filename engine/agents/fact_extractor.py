"""Fact-Extractor agent — bridges DM narrative and fs-manager schema.

Takes a raw DM response (narrative text plus an embedded <world_update>
hint block) and produces an apply_world_update.schema.json-valid payload
that fs-manager will accept. This is the canonical bridge between the
two <world_update> shapes in the repo: the ORM-flavored hint the DM
emits, and the filesystem-operations contract fs-manager enforces.

Current status: stub. Implementation is the next PR — it's blocked on
the source-of-truth decision (see docs/BACKLOG.md), because the output
shape depends on whether writes land in data/state/*.json or stay in
Postgres.
"""


def extract(raw_response: str, session_id: str) -> dict:
    """Extract a schema-valid apply_world_update payload from a DM response.

    Returns a dict matching schemas/apply_world_update.schema.json.
    Callers should run the result through engine.validate() before
    dispatching it to fs-manager.

    Not yet implemented — scaffolding only.
    """
    raise NotImplementedError(
        "engine.agents.fact_extractor.extract is not implemented yet"
    )

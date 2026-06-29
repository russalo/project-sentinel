"""Adversarial robustness of the world_update parse boundary, via bestiary.

bestiary (`russalo/bestiary`) is a proven-real adversarial-input corpus +
contract-runner for byte-parsers. We point it at the Fact-Extractor's
`<world_update>` extraction (`engine.agents.fact_extractor.extract`) — the
untrusted-LLM-text → validated-payload-or-refusal boundary — and assert it
upholds the robustness contract on every specimen:

- NEVER-CRASH  — hostile input degrades to a structured error, never aborts/hangs
- BOUNDED      — resource use stays capped regardless of input size/nesting
- DETERMINISTIC— identical input → identical verdict
- NO-ESCAPE    — the parser reads nothing outside its input
- (survived_check) STRUCTURED-REFUSAL — a hostile specimen is *refused*
  (no payload smuggled through), not silently misparsed

This complements — does not replace — the semantic schema-gate tests
(protected-field / namespace / path-traversal); those attack the validate +
fs-manager layers, this attacks the parse layer.

bestiary is a LOCAL sibling project (not on PyPI), so this skips where it
isn't installed (e.g. GitHub CI); it runs on origin-core dev where bestiary
is `pip install -e`'d. To gate in CI, make bestiary installable there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

bestiary = pytest.importorskip(
    "bestiary", reason="bestiary not installed (local sibling project)"
)

from bestiary import (  # noqa: E402
    Catalog,
    CallableTarget,
    CliTarget,
    Modality,
    build_seed_catalog,
    run,
)

_CLI = Path(__file__).parent / "bestiary" / "world_update_parse_cli.py"
_FIXED_SESSION = "00000000-0000-4000-8000-000000000000"


def _bytes_catalog() -> Catalog:
    """The corpus scoped to the BYTES modality — the specimens that apply to a
    *content* parser. The Fact-Extractor consumes a single blob of LLM text, so
    it is a BYTES target ("a single file"); FS_LAYOUT specimens point at a tree
    root and exercise filesystem-walking parsers (e.g. file-observer), not a
    content parser — running them here would only test our file-reading adapter,
    not `extract()`. (bestiary's own model: BYTES → a file, FS_LAYOUT → a tree.)"""
    return Catalog(
        [s for s in build_seed_catalog().active() if s.modality is Modality.BYTES]
    )


def _structured_refusal(stdout: str) -> bool:
    """survived_check: the parser produced a structured verdict AND refused the
    hostile specimen (no payload smuggled through). Anything else — empty
    output, unparseable, or an accepted payload — is a finding."""
    try:
        verdict = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return False
    return verdict.get("payload_present") is False and "error_count" in verdict


def _assert_report_clean(report) -> None:
    if not report.ok:
        findings = "\n".join(
            f"  {r.specimen_id} [{r.property}] {r.outcome.value}: {r.detail}"
            for r in report.results
            if r.outcome.value in ("fail", "error")
        )
        pytest.fail(
            f"bestiary surfaced robustness findings in the world_update parser:\n{findings}\n"
            f"counts={report.counts()}"
        )


def test_world_update_parse_survives_adversarial_corpus():
    """CliTarget (subprocess): NEVER-CRASH / BOUNDED / DETERMINISTIC + the
    structured-refusal survived_check over the seed catalog."""
    target = CliTarget([sys.executable, str(_CLI), "{path}"])
    report = run(target, _bytes_catalog(), survived_check=_structured_refusal)
    # Sanity: the run actually exercised specimens (not all skipped).
    counts = report.counts()
    assert counts.get("pass", 0) > 0, f"no specimens evaluated: {counts}"
    _assert_report_clean(report)


def test_world_update_parse_no_escape():
    """CallableTarget (in-process): NO-ESCAPE — the parser reads nothing outside
    its input. Pre-initialize the schema validator so its one-time schema-file
    read doesn't trip the NO-ESCAPE sink during a specimen."""
    import engine.schema as schema

    schema.validate({})  # warm the cached validator (loads the schema file once)
    from engine.agents.fact_extractor import extract

    def parse(path: Path) -> object:
        text = Path(path).read_bytes().decode("utf-8", errors="surrogateescape")
        return extract(text, session_id=_FIXED_SESSION, turn_number=0)

    report = run(CallableTarget(parse, label="world_update_parse"), _bytes_catalog())
    _assert_report_clean(report)

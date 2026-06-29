"""Adversarial robustness of the world_update parse boundary, via bestiary.

bestiary (`russalo/bestiary`) is a proven-real adversarial-input corpus +
contract-runner. We point it at the Fact-Extractor's `<world_update>` extraction
(`engine.agents.fact_extractor.extract`) — the untrusted-LLM-text →
validated-payload-or-refusal boundary — and assert the robustness contract:

- NEVER-CRASH   — hostile input degrades to a structured error, never aborts/hangs
- NO-ESCAPE     — the parser reads nothing outside its input
- STRUCTURED-REFUSAL (survived_check) — a hostile specimen is *refused*
  (no payload smuggled through), never silently misparsed
- BOUNDED       — resource use stays capped regardless of input size/nesting
- DETERMINISTIC — identical input → identical verdict

Two targets (simplified on bestiary v0.10.0, which shipped the two fixes from
Sentinel's bestiary#21):
- A CallableTarget covers NEVER-CRASH + NO-ESCAPE + STRUCTURED-REFUSAL fully
  IN-PROCESS — the survived_check now runs on extract()'s return value (a
  FactExtractResult), so no per-specimen CLI shim is needed for these legs.
- A CliTarget covers BOUNDED + DETERMINISTIC, which need subprocess isolation;
  the minimal CLI shim (tests/bestiary/world_update_parse_cli.py) is kept ONLY
  for those.
Both declare `accepts={Modality.BYTES}` (v0.10), so FS_LAYOUT tree specimens SKIP
rather than false-FAIL a content parser — no manual catalog filtering.

This complements — does not replace — the semantic schema-gate tests
(protected-field / namespace / path-traversal), which attack the validate +
fs-manager layers; this attacks the parse layer.

bestiary is a LOCAL sibling project (not on PyPI), so this skips where it isn't
installed (e.g. GitHub CI); it runs on origin-core dev where bestiary is
`pip install -e`'d. To gate in CI, make bestiary installable there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

bestiary = pytest.importorskip(
    "bestiary", reason="bestiary not installed (local sibling project)"
)

from bestiary import (  # noqa: E402
    CallableTarget,
    CliTarget,
    Modality,
    build_seed_catalog,
    run,
)

# Import the parser + schema at module load (not inside the target fn) so the
# one-time import + schema-file read happen BEFORE any specimen runs — otherwise
# NO-ESCAPE would flag that first-call read. The cached validator is then warmed
# in the test before the run.
from engine.agents.fact_extractor import extract  # noqa: E402

_CLI = Path(__file__).parent / "bestiary" / "world_update_parse_cli.py"
_FIXED_SESSION = "00000000-0000-4000-8000-000000000000"
_BYTES = frozenset({Modality.BYTES})


def _parse(path: Path) -> object:
    """Feed the specimen to the parser exactly as a raw DM response (decode the
    lossless way — the real boundary is LLM *text*). Returns the FactExtractResult
    so survived_check can inspect it in-process. No try/except: a raise IS the
    NEVER-CRASH finding we want surfaced."""
    text = Path(path).read_bytes().decode("utf-8", errors="surrogateescape")
    return extract(text, session_id=_FIXED_SESSION, turn_number=0)


def _refused(result: object) -> bool:
    """survived_check (in-process, on extract()'s FactExtractResult): a hostile
    specimen must be REFUSED — no payload smuggled through. `payload is None`
    means nothing was dispatched. Reads an attribute that always exists, so it
    never raises (a raising check would be recorded as a loud ERROR)."""
    return getattr(result, "payload", "sentinel") is None


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


def test_world_update_parse_robustness_in_process():
    """CallableTarget (accepts BYTES): NEVER-CRASH + NO-ESCAPE + STRUCTURED-REFUSAL,
    all in-process via the return-value survived_check (bestiary v0.10 / #21).
    Pre-warm the cached schema validator so its one-time file read doesn't trip
    the NO-ESCAPE sink during a specimen."""
    import engine.schema as schema

    schema.validate({})  # warm the cached validator (loads the schema file once)
    report = run(
        CallableTarget(_parse, label="world_update_parse", accepts=_BYTES),
        build_seed_catalog(),
        survived_check=_refused,
    )
    # Sanity: the run actually exercised specimens (not all skipped).
    assert report.counts().get("pass", 0) > 0, (
        f"no specimens evaluated: {report.counts()}"
    )
    _assert_report_clean(report)


def test_world_update_parse_bounded():
    """CliTarget (accepts BYTES): BOUNDED + DETERMINISTIC — the legs that need
    subprocess isolation. The minimal CLI shim is kept only for these."""
    report = run(
        CliTarget([sys.executable, str(_CLI), "{path}"], accepts=_BYTES),
        build_seed_catalog(),
    )
    _assert_report_clean(report)

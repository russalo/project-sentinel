"""Boundary tests for the engine package.

Enforces the architectural rule: engine/ must not import from Django,
backend/, apps/, or artifacts/. Violating this rule couples a pure-Python
core to a specific web framework and makes it impossible to later extract
the engine into a standalone service without rewriting imports.

Implemented via AST parsing rather than actual imports — that way the
test runs without requiring the engine's runtime dependencies to be
installed, and catches violations even in stub/unreachable code paths.
"""

import ast
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "engine"
FORBIDDEN_ROOTS = {"django", "backend", "apps", "artifacts"}


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def _iter_engine_source_files():
    return sorted(ENGINE_ROOT.rglob("*.py"))


def test_engine_does_not_import_forbidden_modules():
    violations = []
    for path in _iter_engine_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_root(alias.name) in FORBIDDEN_ROOTS:
                        violations.append(
                            f"{path.relative_to(ENGINE_ROOT.parent)}: import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    if _module_root(node.module) in FORBIDDEN_ROOTS:
                        violations.append(
                            f"{path.relative_to(ENGINE_ROOT.parent)}: "
                            f"from {node.module} import ..."
                        )
    assert not violations, "engine/ boundary violations:\n  " + "\n  ".join(violations)


def test_engine_package_has_expected_surface():
    """Sanity check that the scaffolded files exist and are parseable."""
    expected = {
        "__init__.py",
        "types.py",
        "schema.py",
        "llm.py",
        "prompts/__init__.py",
        "prompts/dm.py",
        "agents/__init__.py",
        "agents/dm.py",
        "agents/fact_extractor.py",
    }
    actual = {
        str(p.relative_to(ENGINE_ROOT)).replace("\\", "/")
        for p in ENGINE_ROOT.rglob("*.py")
    }
    missing = expected - actual
    assert not missing, f"missing engine scaffolding files: {sorted(missing)}"

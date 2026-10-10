"""Layering ratchet for core/cep (spec AC 4, code-level assertion).

Nothing under ``core/cep/`` may import a deployable (``services/*``) or an
integration/executor module (``core.integrations/*``), nor the execution
side of the response path. The engine proposes through the approval gate;
the moment ``core/cep`` reaches into executor territory it would be
capable of bypassing the gate — this test fails first.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List

CEP_DIR = Path(__file__).resolve().parents[3] / "core" / "cep"

FORBIDDEN_PREFIXES = ("services", "core.integrations")
FORBIDDEN_MODULES = (
    # The execution side of the response path: the responder's executor
    # loop and the autonomous service that dispatches approved actions.
    "core.response.autonomous_response_service",
)


def _imported_modules(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
    elif isinstance(node, ast.ImportFrom):
        if node.level != 0:
            return  # relative imports cannot name these modules either way
        if node.module:
            yield node.module


def test_no_executor_or_service_imports_under_core_cep() -> None:
    violations: List[str] = []
    for path in sorted(CEP_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for name in _imported_modules(node):
                forbidden = any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in FORBIDDEN_PREFIXES
                ) or name in FORBIDDEN_MODULES
                if forbidden:
                    violations.append(f"{path.name}: {name}")
    assert violations == [], (
        "core/cep must propose through the approval gate, never execute: "
        + ", ".join(violations)
    )

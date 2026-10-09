"""The compile-versus-memory boundary, held by parsing imports (ADR 0001).

The maturity job consumes operational tables — ``workflow_runs``, ``findings``,
``finding_mitre_predictions``, ``cases``, ``case_closure_info`` — and never
episodic memory. ADR 0015's rule is that memory reorders and never decides; a
maturity job that read ``episodic_*`` would import a second decider into the
compile path, and the boundary would rest on convention. It rests on this test
instead: every module in ``core/policy_compiler`` is parsed and any
``core.memory`` or episodic import fails.
"""

import ast
import pathlib

import pytest

import core.policy_compiler

FORBIDDEN_FRAGMENTS = ("core.memory", "core.memory.")
FORBIDDEN_MODULE_PARTS = ("episodic",)


def _imports_of(path: pathlib.Path) -> list[str]:
    """Every module an import statement in ``path`` names, dotted form."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * node.level
            names.append(f"{prefix}{module}")
            names.extend(f"{prefix}{module}.{alias.name}" for alias in node.names)
    return names


def test_the_policy_compiler_domain_never_imports_episodic_memory():
    package_dir = pathlib.Path(core.policy_compiler.__file__).parent
    offenders: list[str] = []
    for path in sorted(package_dir.rglob("*.py")):
        for name in _imports_of(path):
            dotted = name.lstrip(".")
            if any(
                f == dotted or dotted.startswith(f) for f in FORBIDDEN_FRAGMENTS
            ) or any(part in FORBIDDEN_MODULE_PARTS for part in dotted.split(".")):
                offenders.append(f"{path.name}: {name}")
    assert not offenders, (
        "core.policy_compiler imported episodic memory — the compile path must "
        "read operational tables only (ADR 0001; ADR 0015: memory never decides): "
        f"{offenders}"
    )


def test_the_maturity_module_reads_operational_storage():
    # The positive side of the boundary: the gatherer is expected to import the
    # operational models it reads, so the ratchet cannot go green by an
    # over-trimmed import list.
    from core.policy_compiler import maturity

    for name in (
        "WorkflowRun",
        "Finding",
        "FindingMitrePrediction",
        "Case",
        "CaseClosureInfo",
        "CompiledPolicy",
        "CompiledPolicyDecision",
    ):
        assert hasattr(maturity, name), f"maturity no longer reads {name}"


pytestmark = pytest.mark.unit

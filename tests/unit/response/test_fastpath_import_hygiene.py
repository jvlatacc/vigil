"""The fast-path decision core must not drag the world in with it.

Imported in a fresh interpreter, the package may pull only light
dependencies. Anything that reaches a database, a provider, a queue client,
or the deployables under ``services/`` is a heavy import and fails here.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HEAVY_MODULES = (
    "sqlalchemy",
    "anthropic",
    "openai",
    "redis",
    "core.storage",
    "core.llm",
    "core.integrations",
    "core.agents",
    "core.workflows",
    "services",
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_the_decision_core_imports_without_heavy_dependencies():
    script = (
        "import json, sys\n"
        "import core.response.fastpath.config\n"
        "import core.response.fastpath.policy\n"
        "from core.response.fastpath.policy import FastPathDecision, evaluate_fast_path\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    loaded = set(json.loads(proc.stdout))
    dragged_in = sorted(
        module
        for heavy in _HEAVY_MODULES
        for module in loaded
        if module == heavy or module.startswith(heavy + ".")
    )
    assert dragged_in == []

"""The run-kind vocabulary is declared twice and must say the same thing.

Python enqueues a job naming a run kind; TypeScript validates it against a closed
union and resolves it to an arch. Nothing checked the two lists agreed, and they
had already drifted -- TypeScript carried ``tally`` and Python did not, so a
conformance run could be enqueued by hand and refused, or a kind added on one
side reached production missing from the other.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON = REPO_ROOT / "core" / "agents" / "queue.py"
TYPESCRIPT = REPO_ROOT / "services" / "agent" / "contracts" / "events.ts"
REGISTRY = REPO_ROOT / "services" / "agent" / "arch" / "registry.ts"
EDGE_AGENT = REPO_ROOT / "services" / "edge" / "src" / "agents" / "chat.ts"
EDGE_WRANGLER = REPO_ROOT / "services" / "edge" / "wrangler.jsonc"

# The conformance workflow. It proves the harness boundary holds without a real
# domain, so it is deliberately not something the backend can enqueue.
CONFORMANCE_ONLY = frozenset({"tally"})

# Chat left the queue. A conversation is a Durable Object at the edge, so a turn
# is dispatched to it over HTTP and answered with 202 and a stream to read --
# which means the backend has no chat job to enqueue and must not grow one.
HTTP_DISPATCHED = frozenset({"chat"})

BACKEND_EXCLUDES = CONFORMANCE_ONLY | HTTP_DISPATCHED

pytestmark = pytest.mark.unit


def python_kinds() -> tuple[str, ...]:
    for node in ast.walk(ast.parse(PYTHON.read_text())):
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", None) == "RUN_KINDS" for target in node.targets
        ):
            return tuple(element.value for element in node.value.elts)
    raise AssertionError(f"RUN_KINDS not found in {PYTHON}")


def typescript_kinds() -> tuple[str, ...]:
    match = re.search(r"RUN_KINDS\s*=\s*\[([^\]]*)\]", TYPESCRIPT.read_text())
    assert match, f"RUN_KINDS not found in {TYPESCRIPT}"
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def registered_kinds() -> set[str]:
    # Keys of the REGISTERED record: the kinds that resolve to an arch file.
    body = REGISTRY.read_text()
    start = body.index("const REGISTERED")
    return set(re.findall(r"^  ([a-z_]+):", body[start:], re.MULTILINE))


def test_every_kind_the_backend_enqueues_is_one_typescript_accepts():
    stray = sorted(set(python_kinds()) - set(typescript_kinds()))
    assert not stray, (
        "core/agents/queue.py can enqueue kinds the agent layer will refuse:\n  "
        + "\n  ".join(stray)
    )


def test_every_typescript_kind_is_enqueueable_or_deliberately_not():
    missing = sorted(set(typescript_kinds()) - set(python_kinds()) - BACKEND_EXCLUDES)
    assert not missing, (
        "the agent layer accepts kinds the backend cannot enqueue. Add them to "
        "core/agents/queue.py, or to BACKEND_EXCLUDES here with the reason:\n  "
        + "\n  ".join(missing)
    )


def test_every_kind_resolves_to_an_arch():
    # A kind in the union with no registry entry fails at startup rather than
    # seven iterations in -- but only once something tries to run it.
    orphans = sorted(set(typescript_kinds()) - registered_kinds() - BACKEND_EXCLUDES)
    assert (
        not orphans
    ), "these run kinds are accepted but resolve to no arch:\n  " + "\n  ".join(orphans)


def edge_agent_name() -> str:
    match = re.search(r'Chat\.agentName\s*=\s*"([^"]+)"', EDGE_AGENT.read_text())
    assert match, f"Chat.agentName not found in {EDGE_AGENT}"
    return match.group(1)


def test_the_edge_chat_agent_answers_to_the_chat_run_kind():
    # The name is the conversation's storage key and the Durable Object's class,
    # so a rename is a data migration rather than a refactor.
    assert edge_agent_name() in typescript_kinds()
    assert edge_agent_name() in HTTP_DISPATCHED


def test_the_chat_agent_keeps_its_first_migration_tag():
    # Migrations are append-only: the tag that created the class stays the first
    # entry forever, because rewriting it orphans every conversation already stored.
    body = EDGE_WRANGLER.read_text()
    tags = re.findall(r'"tag"\s*:\s*"([^"]+)"', body)
    assert tags, f"no migration tags in {EDGE_WRANGLER}"
    assert tags[0] == "flue-chat", (
        "the first migration tag must stay flue-chat; append a new tag instead:\n  "
        + tags[0]
    )
    classes = re.search(r'"new_sqlite_classes"\s*:\s*\[([^\]]*)\]', body)
    assert classes, "the first migration must create the chat class as SQLite-backed"
    assert re.findall(r'"([^"]+)"', classes.group(1)), "new_sqlite_classes is empty"


def test_the_exclusion_list_stays_honest():
    stale = sorted(kind for kind in BACKEND_EXCLUDES if kind not in typescript_kinds())
    assert (
        not stale
    ), "BACKEND_EXCLUDES names kinds that no longer exist:\n  " + "\n  ".join(stale)

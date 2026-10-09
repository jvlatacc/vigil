"""The executor protocol and the allowlist registry.

The registry is the edge domain's subprocess gate, the service_manager
pattern: an action type that is not a registered key can never reach an
executor, hence a subprocess. These tests pin that guarantee at its root —
including by arming subprocess.run to detonate if it is ever reached.
"""

from __future__ import annotations

import subprocess

import pytest

from core.edge.executors import (
    ExecutionResult,
    LocalExecutor,
    UnregisteredActionType,
    executor_for,
    register,
)
from core.edge.policy import EdgeAction


class StubExecutor:
    """The minimal self-describing executor, for registry tests."""

    action_type = "block_ip"
    name = "stub"

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        return ExecutionResult(success=True, status="executed", executor=self.name)

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult:
        return ExecutionResult(success=True, status="executed", executor=self.name)


class TestRegistryAllowlist:
    def test_unregistered_action_type_never_reaches_a_subprocess(self, monkeypatch):
        """The core allowlist guarantee: refusal happens at the registry door,
        before any executor — if a subprocess were somehow attempted, this
        test detonates."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: pytest.fail("a subprocess was reached"),
        )
        registry: dict[str, LocalExecutor] = {}
        with pytest.raises(UnregisteredActionType):
            executor_for(registry, "process_kill")

    def test_refusal_names_the_action_type(self):
        registry: dict[str, LocalExecutor] = {}
        with pytest.raises(UnregisteredActionType) as excinfo:
            executor_for(registry, "quarantine_file")
        assert "quarantine_file" in str(excinfo.value)

    def test_registered_executor_is_dispatched(self):
        registry: dict[str, LocalExecutor] = {}
        stub = StubExecutor()
        register(registry, stub)
        assert executor_for(registry, "block_ip") is stub

    def test_registration_is_keyed_by_the_declared_action_type(self):
        registry: dict[str, LocalExecutor] = {}
        register(registry, StubExecutor())
        assert list(registry) == ["block_ip"]

    def test_replacing_a_live_registration_is_refused(self):
        """A silent swap would change what enforces under the journal's
        feet — a second registration for one type is a programming error."""
        registry: dict[str, LocalExecutor] = {}
        register(registry, StubExecutor())
        with pytest.raises(ValueError, match="already registered"):
            register(registry, StubExecutor())

    def test_refusal_does_not_consume_the_registered_executor(self, monkeypatch):
        """An unregistered type must not fall back to whatever else the
        registry holds — the allowlist is exact, not approximate."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: pytest.fail("a subprocess was reached"),
        )
        registry: dict[str, LocalExecutor] = {}
        register(registry, StubExecutor())
        with pytest.raises(UnregisteredActionType):
            executor_for(registry, "process_kill")

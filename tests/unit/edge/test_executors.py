"""The executor protocol and the allowlist registry.

The registry is the edge domain's subprocess gate, the service_manager
pattern: an action type that is not a registered key can never reach an
executor, hence a subprocess. These tests pin that guarantee at its root —
including by arming subprocess.run to detonate if it is ever reached.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from core.edge import executors
from core.edge.executors import (
    BLOCKED,
    CLEAR,
    DRY_RUN,
    EXECUTED,
    FAILED,
    NFT_SET,
    NFT_TABLE,
    NO_OP,
    UNKNOWN,
    DryRunBlockIpExecutor,
    ExecutionResult,
    LocalExecutor,
    NftablesBlockIpExecutor,
    UnregisteredActionType,
    _run_nft,
    build_default_registry,
    executor_for,
    register,
)
from core.edge.policy import EdgeAction

ACTION = EdgeAction(type="block_ip", ttl_minutes=30)
TARGET = "198.51.100.7"  # TEST-NET-2 — documentation space, as in probes.py
ENOENT = "Error: Could not receive element: No such file or directory"


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


# --- the nftables executor ----------------------------------------------------


def _nft_ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["nft"], returncode=0, stdout=stdout, stderr=""
    )


def _nft_err(stderr: str, returncode: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["nft"], returncode=returncode, stdout="", stderr=stderr
    )


# A ready node as the default baseline: infrastructure provisioned (table,
# set, chain with the drop rule listed), the element absent, and adds
# succeeding. Individual tests override the replies they care about.
READY_NODE = {
    ("list", "table"): _nft_ok(),
    ("list", "set"): _nft_ok(),
    ("list", "chain"): _nft_ok(stdout=f"ip saddr @{NFT_SET} drop"),
    ("get", "element"): _nft_err(ENOENT),
    ("add", "element"): _nft_ok(),
}


def scripted(
    spec: dict[tuple[str, str], subprocess.CompletedProcess[str]] | None = None,
):
    """An executor over a scriptable fake runner, pre-loaded with
    ready-infrastructure replies. Unscripted commands answer with a loud
    failure so a test never exercises a path it did not see; an unscripted
    element probe defaults to absent, the common case."""
    replies = {**READY_NODE, **(spec or {})}
    calls: list[list[str]] = []

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        key = (args[0], args[1])
        if key in replies:
            return replies[key]
        if key == ("get", "element"):
            return _nft_err(ENOENT)
        return _nft_err(f"unscripted nft command in test: {' '.join(args)}", 127)

    return NftablesBlockIpExecutor(runner=run), calls


class TestNftablesBlockIpExecutor:
    def test_enforce_adds_the_element_with_the_action_ttl(self):
        executor, calls = scripted(
            {
                ("get", "element"): _nft_err(ENOENT),
                ("add", "element"): _nft_ok(),
            }
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is True
        assert result.status == EXECUTED
        assert result.end_state == BLOCKED
        add = next(args for args in calls if args[:2] == ["add", "element"])
        assert "198.51.100.7" in add
        assert "1800s" in add  # ttl_minutes=30, in the seconds nft expects

    def test_failed_add_is_an_explicit_failure_never_a_success(self):
        """The _execute_isolation lesson, pinned: a refused nft command is a
        failed result naming the stderr — never a success for containment
        that did not occur."""
        executor, _ = scripted(
            {
                ("get", "element"): _nft_err(ENOENT),
                ("add", "element"): _nft_err("Operation not permitted"),
            }
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is False
        assert result.status == FAILED
        assert result.code == "nft-error"
        assert result.end_state == CLEAR  # atomicity: a failed add changed nothing
        assert "nothing was enforced" in result.message
        assert "Operation not permitted" in result.detail["stderr"]

    def test_undo_of_a_never_applied_block_is_a_no_op_success(self):
        """The idempotency criterion: the element is absent (never applied,
        or TTL-expired), the goal state already held — success, honestly
        labelled as nothing-changed, with no delete attempted."""
        executor, calls = scripted()  # default: element probe reads absent
        result = executor.undo(ACTION, TARGET)
        assert result.success is True
        assert result.status == NO_OP
        assert result.end_state == CLEAR
        assert not any(args[:2] == ["delete", "element"] for args in calls)

    def test_undo_removes_a_live_block(self):
        executor, calls = scripted(
            {
                ("get", "element"): _nft_ok(),
                ("delete", "element"): _nft_ok(),
            }
        )
        result = executor.undo(ACTION, TARGET)
        assert result.success is True
        assert result.status == EXECUTED
        assert result.end_state == CLEAR
        delete = next(args for args in calls if args[:2] == ["delete", "element"])
        assert "198.51.100.7" in delete

    def test_failed_undo_reports_the_block_remains_in_force(self):
        """A failed lift is worse than none if recorded as if it happened:
        the result fails and names the end state honestly."""
        executor, _ = scripted(
            {
                ("get", "element"): _nft_ok(),
                ("delete", "element"): _nft_err("Device or resource busy"),
            }
        )
        result = executor.undo(ACTION, TARGET)
        assert result.success is False
        assert result.code == "nft-error"
        assert result.end_state == BLOCKED
        assert "remains in force" in result.message

    def test_unanswerable_probe_never_reads_as_absent(self):
        """A probe that failed for a non-absence reason (permission here)
        must not be mistaken for "not blocked" — the enforce refuses on an
        unknown end state and adds no element."""
        executor, calls = scripted(
            {("get", "element"): _nft_err("netlink: Operation not permitted")}
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is False
        assert result.code == "probe-failed"
        assert result.end_state == UNKNOWN
        assert not any(args[:2] == ["add", "element"] for args in calls)

    def test_unanswerable_probe_blocks_the_undo_too(self):
        executor, calls = scripted(
            {("get", "element"): _nft_err("netlink: Operation not permitted")}
        )
        result = executor.undo(ACTION, TARGET)
        assert result.success is False
        assert result.code == "probe-failed"
        assert result.end_state == UNKNOWN
        assert not any(args[:2] == ["delete", "element"] for args in calls)

    def test_non_ip_target_never_builds_a_command(self):
        """Injection defense, pinned: nft grammar riding in on the target
        cannot reach argv — the executor canonicalizes before it builds."""
        executor, calls = scripted()
        result = executor.enforce(ACTION, "198.51.100.7 } limit rate 1/second drop")
        assert result.success is False
        assert result.code == "invalid-target"
        assert calls == []

    def test_ipv6_target_is_an_explicit_failure(self):
        """The v1 set is ipv4_addr by scope; a v6 target refuses instead of
        silently skipping or claiming a block the set cannot hold."""
        executor, calls = scripted()
        result = executor.enforce(ACTION, "2001:db8::1")
        assert result.success is False
        assert result.code == "unsupported-address-family"
        assert result.end_state == CLEAR
        assert calls == []

    def test_ttl_below_one_minute_is_refused(self):
        executor, calls = scripted()
        result = executor.enforce(EdgeAction(type="block_ip", ttl_minutes=0), TARGET)
        assert result.success is False
        assert result.code == "invalid-ttl"
        assert calls == []

    def test_missing_infrastructure_is_created_before_enforcing(self):
        enoent = _nft_err("Error: No such file or directory")
        executor, calls = scripted(
            {
                ("list", "table"): enoent,
                ("add", "table"): _nft_ok(),
                ("list", "set"): enoent,
                ("add", "set"): _nft_ok(),
                ("list", "chain"): enoent,
                ("add", "chain"): _nft_ok(),
                ("add", "rule"): _nft_ok(),
                ("add", "element"): _nft_ok(),
            }
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is True
        steps = [tuple(args[:2]) for args in calls]
        assert ("add", "table") in steps
        assert ("add", "set") in steps
        assert ("add", "chain") in steps
        assert ("add", "rule") in steps

    def test_a_present_drop_rule_is_never_duplicated(self):
        executor, calls = scripted()  # READY_NODE: chain already lists the rule
        result = executor.enforce(ACTION, TARGET)
        assert result.success is True
        assert not any(args[:2] == ["add", "rule"] for args in calls)

    def test_a_flushed_drop_rule_is_repaired_before_the_element(self):
        """An "executed" must mean packets drop — so a chain that lost its
        rule gets it back BEFORE the element is added, and the order is
        pinned here."""
        executor, calls = scripted(
            {
                ("list", "chain"): _nft_ok(stdout="chain ingress_guard"),
                ("add", "rule"): _nft_ok(),
                ("add", "element"): _nft_ok(),
            }
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is True
        order = [tuple(args[:2]) for args in calls]
        assert order.index(("add", "rule")) < order.index(("add", "element"))

    def test_unprivileged_infrastructure_never_enforces(self):
        """Non-ENOENT probe failures are infrastructure-unavailable, not
        absence — nothing is added, and the failure is explicit."""
        executor, calls = scripted(
            {
                ("list", "table"): _nft_err(
                    "netlink cache initialization failed: Operation not permitted"
                )
            }
        )
        result = executor.enforce(ACTION, TARGET)
        assert result.success is False
        assert result.code == "infrastructure-unavailable"
        assert result.end_state == CLEAR
        assert not any(args[:2] == ["add", "element"] for args in calls)

    def test_every_command_names_only_the_owned_table(self):
        """Structural containment: through a full enforce+undo cycle, every
        argv that names a family names *our* table — nothing else is
        listed, created, flushed, or deleted."""
        executor, calls = scripted(
            {
                ("get", "element"): _nft_err(ENOENT),
                ("add", "element"): _nft_ok(),
                ("delete", "element"): _nft_ok(),
            }
        )
        assert executor.enforce(ACTION, TARGET).success
        assert executor.undo(ACTION, TARGET).success
        assert calls, "the cycle should have issued commands"
        for argv in calls:
            if "inet" in argv:
                assert argv[argv.index("inet") + 1] == NFT_TABLE, argv


class TestNftablesAvailability:
    def test_missing_binary_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)
        available, reason = NftablesBlockIpExecutor.available()
        assert available is False
        assert "nft" in reason

    def test_unprivileged_ruleset_read_is_unavailable(self, monkeypatch):
        """which nft is not enough: without the privilege the ruleset probe
        fails, and that is where the DryRun fallback is still choosable."""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/sbin/nft")
        monkeypatch.setattr(
            executors,
            "_run_nft",
            lambda args: _nft_err("cache init failed: Operation not permitted"),
        )
        available, _ = NftablesBlockIpExecutor.available()
        assert available is False

    def test_readable_ruleset_is_available(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/sbin/nft")
        monkeypatch.setattr(executors, "_run_nft", lambda args: _nft_ok())
        available, _ = NftablesBlockIpExecutor.available()
        assert available is True


class TestRunnerContract:
    """The real runner's promise: it answers, it never raises."""

    def test_a_timeout_is_a_result_not_an_exception(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["nft"], timeout=10)

        monkeypatch.setattr(subprocess, "run", boom)
        result = _run_nft(["list", "ruleset"])
        assert result.returncode != 0
        assert "timed out" in result.stderr

    def test_a_missing_binary_is_a_result_not_an_exception(self, monkeypatch):
        def boom(*args, **kwargs):
            raise FileNotFoundError("nft")

        monkeypatch.setattr(subprocess, "run", boom)
        result = _run_nft(["list", "ruleset"])
        assert result.returncode != 0
        assert "could not run" in result.stderr


class TestUnregisteredTypesStillRefused:
    def test_registered_nftables_executor_satisfies_the_protocol(self):
        registry: dict[str, LocalExecutor] = {}
        register(registry, NftablesBlockIpExecutor())
        assert executor_for(registry, "block_ip").action_type == "block_ip"
        with pytest.raises(UnregisteredActionType):
            executor_for(registry, "process_kill")


class TestDryRunBlockIpExecutor:
    def test_enforce_never_claims_enforcement(self):
        """The fallback's honesty: a success whose status states that no
        containment occurred — the reconcile side reads dry-run executions
        as review items, not enforced actions."""
        result = DryRunBlockIpExecutor().enforce(ACTION, TARGET)
        assert result.success is True
        assert result.status == DRY_RUN
        assert result.end_state == CLEAR
        assert "nothing was enforced" in result.message

    def test_undo_is_equally_honest(self):
        result = DryRunBlockIpExecutor().undo(ACTION, TARGET)
        assert result.success is True
        assert result.status == DRY_RUN
        assert result.end_state == CLEAR

    def test_it_satisfies_the_protocol(self):
        registry: dict[str, LocalExecutor] = {}
        register(registry, DryRunBlockIpExecutor())
        assert executor_for(registry, "block_ip").name == "dryrun"


class TestDefaultRegistry:
    def test_nftables_selected_when_available(self):
        registry = build_default_registry(nftables=True)
        assert isinstance(registry["block_ip"], NftablesBlockIpExecutor)

    def test_dryrun_selected_when_nftables_unavailable_or_unprivileged(self):
        """The selection criterion: an unprivileged node falls back to the
        DryRun executor rather than one that would fail louder later."""
        registry = build_default_registry(nftables=False)
        assert isinstance(registry["block_ip"], DryRunBlockIpExecutor)

    def test_selection_probes_availability_when_not_told(self, monkeypatch):
        monkeypatch.setattr(
            NftablesBlockIpExecutor, "available", classmethod(lambda cls: (False, "no"))
        )
        registry = build_default_registry()
        assert isinstance(registry["block_ip"], DryRunBlockIpExecutor)

    def test_block_ip_is_the_only_registered_type(self):
        """v1 scope: every other action type is unregistered, so the
        registry door refuses it before any subprocess can exist."""
        registry = build_default_registry(nftables=False)
        assert list(registry) == ["block_ip"]
        with pytest.raises(UnregisteredActionType):
            executor_for(registry, "process_kill")

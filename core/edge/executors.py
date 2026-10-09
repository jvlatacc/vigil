"""Local executors — the edge domain's only subprocess surface.

An enforcement decision leaves the pure world of ``decision.py`` here: an
executor turns an allowed ``block_ip`` into a real nftables element (or,
where the node cannot enforce, an honestly-labelled dry run). Three
invariants govern everything in this module:

**The registry is the allowlist.** Following the
``core/platform/service_manager.py`` pattern, ``executor_for`` is the only
dispatch door: an action type absent from the registry raises
``UnregisteredActionType`` before any executor — hence any subprocess — can
be reached. Nothing reads configuration to widen that set; it is exactly
what ``build_default_registry`` (or an embedding runtime) registered.

**A result records what actually happened.** The ``_execute_isolation``
lesson from ``core/response``: a success is never recorded for containment
that did not occur. Every ``ExecutionResult`` carries ``status`` (what the
call did), ``end_state`` (whether the target is blocked afterward) and, on
failures, a ``code`` and the nft stderr. nft commands are atomic — a nonzero
exit changed nothing — so the executor can state the end state: a failed
add leaves the target clear, a failed delete leaves it blocked. A probe may
conclude "absent" only from nft's own ENOENT marker; an unanswerable probe
is a failure with an unknown end state, never a guess.

**Idempotent by construction.** ``enforce`` on an already-blocked address
and ``undo`` of a never-applied block are no-op successes: the goal state
already held. Retries and TTL-expiry races converge instead of erroring.

Division of labor with the decision ladder: the protected-target guard ran
in ``decide_local_action``, before any executor — the executor's target
duty is narrower but hard: a target only ever reaches argv as the canonical
``str()`` of a parsed IP address, so alert-controlled junk cannot shape the
command. v1 blocks IPv4 addresses in a dedicated ``inet vigil_warden``
table (host-firewall input hook, per the spec's scope boundary); IPv6
targets and non-``block_ip`` action types are explicit failures, never
silently skipped.
"""

from __future__ import annotations

import ipaddress
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Literal, Mapping, Protocol

from core.edge.policy import EdgeAction

__all__ = [
    "BLOCKED",
    "CLEAR",
    "EXECUTED",
    "FAILED",
    "NO_OP",
    "UNKNOWN",
    "ExecutionResult",
    "LocalExecutor",
    "NftablesBlockIpExecutor",
    "UnregisteredActionType",
    "executor_for",
    "register",
]

# --- what a result records --------------------------------------------------

# ``status``: what this call did. ``executed`` — the element state changed in
# this call; ``no-op`` — the goal state already held, nothing changed;
# ``dry-run`` — nothing was enforced (the fallback executor's mode);
# ``failed`` — the command failed or could not run.
Status = Literal["executed", "no-op", "dry-run", "failed"]
EXECUTED: Status = "executed"
NO_OP: Status = "no-op"
DRY_RUN: Status = "dry-run"
FAILED: Status = "failed"

# ``end_state``: whether the target is blocked once the call returned — the
# journal's honesty field. ``unknown`` is a failure state, never an excuse.
EndState = Literal["blocked", "clear", "unknown"]
BLOCKED: EndState = "blocked"
CLEAR: EndState = "clear"
UNKNOWN: EndState = "unknown"


@dataclass(frozen=True)
class ExecutionResult:
    """What actually happened when an executor handled one action.

    Built by executors, consumed by the journal: ``status`` and ``end_state``
    are the fields a reconcile-time audit reads to reconstruct whether the
    containment a record claims is the containment that occurred.
    """

    success: bool
    status: Status
    executor: str
    end_state: EndState = UNKNOWN
    code: str | None = None
    message: str = ""
    detail: Mapping[str, object] = field(default_factory=dict)


# --- the protocol ------------------------------------------------------------


class LocalExecutor(Protocol):
    """One reversible enforcement primitive, self-describing.

    ``action_type`` is the registry key this executor answers to and ``name``
    is what the journal records as the enforcement mechanism. Both
    ``enforce`` and ``undo`` take the decided action and the canonical
    target, and both are idempotent: applied twice, the second call is a
    no-op success. They never raise — every outcome, including a lost
    subprocess, is an ``ExecutionResult``.
    """

    action_type: str
    name: str

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult: ...

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult: ...


# --- the allowlist registry ---------------------------------------------------


class UnregisteredActionType(KeyError):
    """Raised for an action type outside the registry's allowlist."""


def register(registry: dict[str, LocalExecutor], executor: LocalExecutor) -> None:
    """Add an executor to the allowlist.

    Keyed by the executor's declared ``action_type`` — a registry that agreed
    with anything other than the executor's own self-description would be a
    lie of exactly the kind this module exists to prevent. Replacing a live
    registration would swap enforcement primitives under the journal's feet,
    so it is refused.
    """
    if executor.action_type in registry:
        raise ValueError(
            f"an executor for {executor.action_type!r} is already registered"
        )
    registry[executor.action_type] = executor


def executor_for(
    registry: Mapping[str, LocalExecutor], action_type: str
) -> LocalExecutor:
    """The registered executor for ``action_type`` — or a refusal.

    The allowlist's only read door, the ``service_manager`` pattern: an
    action type that is not a key here raises before any executor, hence any
    subprocess, can be reached. There is no path through this module that
    enforces an unregistered type.
    """
    try:
        return registry[action_type]
    except KeyError:
        raise UnregisteredActionType(action_type) from None


# --- the nftables executor ----------------------------------------------------

# The owned infrastructure. This executor's whole command surface names this
# table — nothing here lists, creates, flushes, or deletes anything else.
NFT_TABLE = "vigil_warden"
NFT_SET = "blocked_ips"
NFT_CHAIN = "ingress_guard"

# nft's absence marker. "Missing" is concluded only from this string; any
# other failure (permission, timeout) is unanswerable and must never read
# as absence.
_NFT_ENOENT = "No such file or directory"

# nft operations are netlink round-trips — sub-second normally. Ten seconds
# is already a hung kernel, and a hang is a failure, not an excuse to stall
# the decision loop.
_NFT_TIMEOUT_S = 10.0

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _stderr_text(err: BaseException) -> str:
    """A best-effort stderr from an exception — text or bytes, or the repr."""
    raw = getattr(err, "stderr", None)
    if isinstance(raw, bytes):
        return raw.decode(errors="replace").strip()
    return str(raw or err).strip()


def _run_nft(args: list[str]) -> subprocess.CompletedProcess[str]:
    """The real runner. Contract: returns a CompletedProcess, never raises —
    a timeout or a missing binary is an outcome, not an exception, so the
    honesty ladder in the executor below always gets to answer."""
    argv = ["nft", *args]
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=_NFT_TIMEOUT_S
        )
    except subprocess.TimeoutExpired as err:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=-1,
            stdout="",
            stderr=f"nft timed out after {_NFT_TIMEOUT_S:.0f}s ({_stderr_text(err)})",
        )
    except OSError as err:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=127,
            stdout="",
            stderr=f"nft could not run: {err}",
        )


def _canonical_ip(target: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The parsed target address, or None.

    The executor's injection defense: a target reaches argv only as the
    ``str()`` of a parsed address, so a crafted value — a closing brace, a
    second rule, shell metacharacters — cannot ride alert data into the
    element syntax. The ladder's guard refused unparseable targets first;
    this is the executor's own check, because the executor is the thing
    that builds a subprocess.
    """
    try:
        ip = ipaddress.ip_address(str(target).strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def _failure(
    code: str,
    executor: str,
    message: str,
    *,
    end_state: EndState,
    detail: dict[str, object] | None = None,
) -> ExecutionResult:
    """The one way executors fail: an explicit result — never an exception,
    and never a success."""
    return ExecutionResult(
        success=False,
        status=FAILED,
        executor=executor,
        code=code,
        message=message,
        end_state=end_state,
        detail=detail or {},
    )


class NftablesBlockIpExecutor:
    """Enforce ``block_ip`` as an element of the dedicated ``vigil_warden``
    table — the host-firewall block/unblock of the spec's v1 scope.

    The executor owns its infrastructure outright: the ``inet vigil_warden``
    table, the timeout-bearing ``blocked_ips`` set, and the input-hook chain
    whose rule drops traffic from listed addresses. Every enforce re-checks
    that the drop rule is in place before adding an element, so an
    "executed" result always means packets from that address now drop — not
    merely that a set gained a member nobody reads. Nothing outside the
    owned table is touched: every argv names ``inet vigil_warden``.

    nft commands are atomic — a nonzero exit changed nothing. That is what
    lets a result state the end state: a failed add leaves the target
    clear, a failed delete leaves it blocked, and both facts are recorded,
    because a success is never recorded for containment that did not occur
    (the ``_execute_isolation`` lesson).
    """

    action_type = "block_ip"
    name = "nftables"

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner: CommandRunner = runner or _run_nft

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """Whether this node can enforce with nftables at all.

        The binary must exist AND the caller must be privileged enough to
        read the ruleset — the same capability creating the owned table
        needs. ``which nft`` alone would select an executor that fails later
        and louder; the privilege is probed here, where the DryRun fallback
        is still choosable.
        """
        if shutil.which("nft") is None:
            return False, "nft not found on PATH"
        probe = _run_nft(["list", "ruleset"])
        if probe.returncode != 0:
            reason = probe.stderr.strip().splitlines() or ["nft ruleset unreadable"]
            return False, reason[0]
        return True, "nft ruleset readable"

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        """Add the target to ``blocked_ips`` with the action's TTL.

        Idempotent: an address already present is a no-op success — the
        containment is in force either way. A refused or failed enforcement
        leaves the target clear and says so.
        """
        ip = _canonical_ip(target)
        if ip is None:
            return _failure(
                "invalid-target",
                self.name,
                f"target {target!r} is not an IP address; nothing was enforced",
                end_state=CLEAR,
            )
        if ip.version != 4:
            # The owned set is ipv4_addr (v1 scope: host-firewall blocks).
            # Refusing is the honest outcome — silently skipping, or
            # reporting success, would fake containment the set cannot hold.
            return _failure(
                "unsupported-address-family",
                self.name,
                f"{ip} is IPv6; the v1 {NFT_SET} set is ipv4-only"
                " — nothing was enforced",
                end_state=CLEAR,
            )
        if action.ttl_minutes < 1:
            return _failure(
                "invalid-ttl",
                self.name,
                f"ttl_minutes={action.ttl_minutes} cannot be enforced"
                " — nothing was enforced",
                end_state=CLEAR,
            )

        not_ready = self._ensure_infrastructure()
        if not_ready is not None:
            return not_ready

        present = self._element_present(str(ip))
        if present is None:
            return _failure(
                "probe-failed",
                self.name,
                f"nft could not report whether {ip} is already blocked;"
                " refusing to guess — nothing was enforced",
                end_state=UNKNOWN,
            )
        if present:
            return ExecutionResult(
                success=True,
                status=NO_OP,
                executor=self.name,
                end_state=BLOCKED,
                message=f"{ip} was already blocked — nothing changed",
                detail={"was_present": True},
            )

        added = self._runner(
            [
                "add",
                "element",
                "inet",
                NFT_TABLE,
                NFT_SET,
                "{",
                str(ip),
                "timeout",
                f"{action.ttl_minutes * 60}s",
                "}",
            ]
        )
        if added.returncode != 0:
            # Atomicity: the failed add changed nothing, so the target is
            # still clear — recorded, not assumed.
            return _failure(
                "nft-error",
                self.name,
                f"nft refused the block for {ip}: {self._nft_error(added)}"
                " — nothing was enforced",
                end_state=CLEAR,
                detail={
                    "exit_code": added.returncode,
                    "stderr": added.stderr.strip() or "(no stderr)",
                },
            )
        return ExecutionResult(
            success=True,
            status=EXECUTED,
            executor=self.name,
            end_state=BLOCKED,
            message=f"{ip} blocked for {action.ttl_minutes}m ({NFT_TABLE}/{NFT_SET})",
        )

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult:
        """Delete the target from ``blocked_ips``.

        Idempotent: undoing a block that is not in force — never applied, or
        its nft timeout already expired it — is a no-op success, because the
        goal state (an unblocked target) already held. No infrastructure is
        created on the way down: an undo that re-built the enforcement
        machinery would be recreating the power it is lifting.
        """
        ip = _canonical_ip(target)
        if ip is None:
            # On enforce a non-IP target is provably clear; here the honest
            # answer is that this executor cannot know — refusing, not
            # laundering an upstream bug into a success.
            return _failure(
                "invalid-target",
                self.name,
                f"target {target!r} is not an IP address; blocked state left as-is",
                end_state=UNKNOWN,
            )

        present = self._element_present(str(ip))
        if present is None:
            return _failure(
                "probe-failed",
                self.name,
                f"nft could not report whether {ip} is blocked;"
                " refusing to guess — any block is left in place",
                end_state=UNKNOWN,
            )
        if not present:
            return ExecutionResult(
                success=True,
                status=NO_OP,
                executor=self.name,
                end_state=CLEAR,
                message=f"{ip} was not blocked — nothing to lift",
                detail={"was_present": False},
            )

        deleted = self._runner(
            ["delete", "element", "inet", NFT_TABLE, NFT_SET, "{", str(ip), "}"]
        )
        if deleted.returncode != 0:
            # Atomicity: the failed delete changed nothing, so the block is
            # still in force — the one thing worse than a failed lift is
            # recording it as if it happened.
            return _failure(
                "nft-error",
                self.name,
                f"nft refused the unblock for {ip}: {self._nft_error(deleted)}"
                " — the block remains in force",
                end_state=BLOCKED,
                detail={
                    "exit_code": deleted.returncode,
                    "stderr": deleted.stderr.strip() or "(no stderr)",
                },
            )
        return ExecutionResult(
            success=True,
            status=EXECUTED,
            executor=self.name,
            end_state=CLEAR,
            message=f"{ip} unblocked ({NFT_TABLE}/{NFT_SET})",
        )

    def _element_present(self, ip: str) -> bool | None:
        """True/False when nft could answer; None when it could not.

        Absence is concluded only from nft's ENOENT marker — an unanswerable
        probe (permission, timeout) must never read as "not blocked", or an
        enforce would proceed on a guess.
        """
        probe = self._runner(
            ["get", "element", "inet", NFT_TABLE, NFT_SET, "{", ip, "}"]
        )
        if probe.returncode == 0:
            return True
        if _NFT_ENOENT in probe.stderr:
            return False
        return None

    def _ensure_infrastructure(self) -> ExecutionResult | None:
        """Idempotently put the owned table, set, chain and drop rule in
        place. Returns a failed result when any step cannot be confirmed,
        None when ready.

        Each "missing" is concluded only from nft's ENOENT marker; any other
        failure (unprivileged, timeout) is a failed result — unknown
        infrastructure state never reads as ready, because enforcing into
        infrastructure whose state is unknown is how a "success" stops
        meaning anything.
        """
        table = self._runner(["list", "table", "inet", NFT_TABLE])
        if table.returncode != 0:
            if _NFT_ENOENT not in table.stderr:
                return self._infra_failure("list table", table)
            created = self._runner(["add", "table", "inet", NFT_TABLE])
            if created.returncode != 0:
                return self._infra_failure("add table", created)

        members = self._runner(["list", "set", "inet", NFT_TABLE, NFT_SET])
        if members.returncode != 0:
            if _NFT_ENOENT not in members.stderr:
                return self._infra_failure("list set", members)
            created = self._runner(
                [
                    "add",
                    "set",
                    "inet",
                    NFT_TABLE,
                    NFT_SET,
                    "{",
                    "type",
                    "ipv4_addr",
                    ";",
                    "flags",
                    "timeout",
                    ";",
                    "}",
                ]
            )
            if created.returncode != 0:
                return self._infra_failure("add set", created)

        chain = self._runner(["list", "chain", "inet", NFT_TABLE, NFT_CHAIN])
        if chain.returncode != 0:
            if _NFT_ENOENT not in chain.stderr:
                return self._infra_failure("list chain", chain)
            created = self._runner(
                [
                    "add",
                    "chain",
                    "inet",
                    NFT_TABLE,
                    NFT_CHAIN,
                    "{",
                    "type",
                    "filter",
                    "hook",
                    "input",
                    "priority",
                    "filter",
                    ";",
                    "policy",
                    "accept",
                    ";",
                    "}",
                ]
            )
            if created.returncode != 0:
                return self._infra_failure("add chain", created)

        if "@" + NFT_SET not in chain.stdout:
            # The chain exists but its drop rule does not — flushed, or
            # created by a run before the rule existed. Without the rule the
            # set is bookkeeping: elements nobody reads, "executed" a lie.
            # Re-adding is idempotent at the rule level.
            ruled = self._runner(
                [
                    "add",
                    "rule",
                    "inet",
                    NFT_TABLE,
                    NFT_CHAIN,
                    "ip",
                    "saddr",
                    "@" + NFT_SET,
                    "drop",
                ]
            )
            if ruled.returncode != 0:
                return self._infra_failure("add rule", ruled)
        return None

    def _infra_failure(
        self, step: str, result: subprocess.CompletedProcess[str]
    ) -> ExecutionResult:
        return _failure(
            "infrastructure-unavailable",
            self.name,
            f"nft could not {step} the {NFT_TABLE} infrastructure:"
            f" {self._nft_error(result)} — nothing was enforced",
            end_state=CLEAR,
            detail={
                "exit_code": result.returncode,
                "stderr": result.stderr.strip() or "(no stderr)",
            },
        )

    @staticmethod
    def _nft_error(result: subprocess.CompletedProcess[str]) -> str:
        """nft's first error line — its stderr is how failures explain."""
        lines = (result.stderr or "").strip().splitlines()
        return lines[0] if lines else f"exit {result.returncode} (no stderr)"

"""The guard chain: one fail-closed gate between the Responder's confidence
and the containment actuator (#944, spec D1).

Four checks, ordered cheapest-and-most-specific first — the never-quarantine
invariant, the circuit breaker, evidence-origin trust, and the blast-radius
quotas. Every outcome renders a ``decision_rule``-style rationale (#917), and
no rejection ever drops an action: the verdict forces the caller onto the
human-approval path, where a person may still decide (the audited emergency
valve).

Consumed at exactly two enforcement sites (#944, locked architecture):
``create_isolation_action`` before ``approval_requirement``, and
``execute_approved_actions`` before dispatching — closing the create-to-execute
gap for rows whose guards moved between the two transactions.

The dependencies are asyncio-native (async Redis clients, loop-bound locks)
while both enforcement sites are and must stay synchronous — existing callers
and tests call them without an event loop. :class:`_GuardLoop` runs one
dedicated loop thread for the life of the process: every breaker/quota await
lands on the same loop (connections and locks never cross loops) and a caller
in a foreign loop or without one needs nothing special. A guard evaluation
that cannot finish within ``GUARD_EVALUATION_TIMEOUT_SECONDS`` — a hung
Redis, a wedged loop — must not block the response pipeline: it fails closed
to :class:`GuardState.GUARDS_UNAVAILABLE`, machine speed waits for a person.

Lives in ``core/`` because ``core`` must not import ``services``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Coroutine, Mapping, Optional, Sequence, Tuple

from core.response.breaker import OPEN, ContainmentBreaker, open_state_rule
from core.response.config import decision_rule
from core.response.guards_config import GuardConfig, GuardConfigError
from core.response.origin import OriginConfigError, OriginTrustIndex
from core.response.protected_assets import protected_asset_hit
from core.response.quotas import ContainmentQuota, QuotaState

logger = logging.getLogger(__name__)

# An origin attests for machine-speed response when its scope names it — the
# vocabulary env.example documents on DAEMON_TRUSTED_ORIGINS — or when it is
# scoped for everything ("*").
AUTO_RESPONSE_SCOPE = "auto_response"
ANY_SCOPE = "*"

# The guard chain answers within this bound or fails closed: machine-speed
# response never waits indefinitely on shared state.
GUARD_EVALUATION_TIMEOUT_SECONDS = 10.0


def _first_line(value: Any) -> str:
    # An exception's str() can be empty (TimeoutError, for one) — a blank
    # rationale would read worse than the truth: "unknown".
    text = str(value).strip()
    return text.splitlines()[0][:200] if text else "unknown"


class GuardState(Enum):
    """What the chain decided, keyed the way the audit rows name it."""

    ALLOWED = "allowed"
    PROTECTED_ASSET = "protected_asset"
    BREAKER_OPEN = "breaker_open"
    ORIGIN_UNVERIFIED = "origin_unverified"
    QUOTA_SOFT = "quota_soft"
    QUOTA_HARD = "quota_hard"
    # The chain could not be evaluated honestly (unbuildable config, hung
    # shared state, unexpected failure). Needs a person — never "allow".
    GUARDS_UNAVAILABLE = "guards_unavailable"


@dataclass(frozen=True)
class GuardVerdict:
    """One guard evaluation, rendered the way every decision is (#917)."""

    state: GuardState
    needs_human: bool  # True -> pending approval regardless of confidence
    rule: str  # the rationale the action row and audit log record
    # Set when this evaluation's note or quota verdict tripped the breaker:
    # the caller claims the once-per-OPEN escalation for exactly this hold.
    tripped: bool = False


@dataclass(frozen=True)
class FindingOriginStatus:
    """One evidencing finding's origin stamp, as the chain reads it.

    Verification happened at ingest (the webhook's attestation check); the
    chain reads stamps, it does not verify. Carried from the finding the
    Responder already holds — ``origin_statuses_for`` — so decision time
    needs no database round trip.
    """

    finding_id: str
    origin_verified: bool = False
    origin_id: Optional[str] = None


def origin_statuses_for(finding: Mapping[str, Any]) -> Tuple[FindingOriginStatus, ...]:
    """The origin stamps of the finding dict the responder is acting on.

    A finding that never carried a stamp (polled sources, or a caller that
    predates the stamps) reads as unverified — the safe branch, per D5.
    """
    finding_id = str(finding.get("finding_id") or "unknown")
    return (
        FindingOriginStatus(
            finding_id=finding_id,
            origin_verified=bool(finding.get("origin_verified", False)),
            origin_id=finding.get("origin_id"),
        ),
    )


def _origin_auto_verified(status: FindingOriginStatus, index: OriginTrustIndex) -> bool:
    """Whether one status may drive machine-speed response (#944, D5).

    Verified at ingest, from a registered origin, scoped for auto-response.
    An origin the trust index no longer knows cannot vouch — a stamp from a
    since-disabled origin reads as unverified here, not as trusted.
    """
    if not status.origin_verified or not status.origin_id:
        return False
    scope = index.scope_of(status.origin_id)
    if scope is None:
        return False
    return scope in (ANY_SCOPE, AUTO_RESPONSE_SCOPE)


async def evaluate_guards(
    action_type: str,
    target_ip: Optional[str],
    target_hostname: Optional[str],
    evidence_origins: Sequence[FindingOriginStatus],
    config: GuardConfig,
    breaker: ContainmentBreaker,
    quota: ContainmentQuota,
    *,
    spend_quota: bool = True,
) -> GuardVerdict:
    """The ordered gate for one would-be action (#944, D1).

    Invariant, then breaker, then origin, then quota. ``spend_quota=False``
    is the dry-run shape: the quota is judged on its current windows without
    consuming a slot, because a dry-run executes nothing and must not mutate
    enforcement state. The breaker notes fire either way — the flood they
    count is real even when the response is a log line.

    Returns ``(verdict)``; every rejection carries the rationale the caller
    renders on the action row, and ``needs_human`` forces the human path.
    """
    # ORM columns hand back str-subclass enums; the quota keys and the
    # rationales want the plain string.
    action_type = str(getattr(action_type, "value", action_type))
    # 1. Never-quarantine invariant: a protected target waits for a person at
    #    any confidence, any severity, any breaker state. The hold feeds the
    #    breaker's probe counter (D4b) — someone may be probing the set.
    hit = protected_asset_hit(target_ip, target_hostname)
    if hit is not None:
        trip_rule = await breaker.note_invariant_block()
        logger.warning(
            "Guard held %s on %s: %s%s",
            action_type,
            target_ip or target_hostname,
            hit.rule(),
            " (trip rule: %s)" % trip_rule if trip_rule else "",
        )
        return GuardVerdict(
            GuardState.PROTECTED_ASSET, True, hit.rule(), tripped=trip_rule is not None
        )

    # 2. Breaker: one shared state read. While OPEN, auto-response is
    #    suspended for everything — verified, under-quota, whatever. A
    #    degraded read answers OPEN (fail safe), so this cannot be raced
    #    by an unreadable store.
    status = await breaker.status()
    if status.state == OPEN:
        logger.warning(
            "Guard held %s on %s: breaker OPEN — %s",
            action_type,
            target_ip or target_hostname,
            status.reason or "auto-response suspended",
        )
        return GuardVerdict(
            GuardState.BREAKER_OPEN, True, open_state_rule(status.seconds_left)
        )

    # 3. Origin: every evidencing finding must be origin-verified from an
    #    origin scoped for auto-response (D5). Crypto happened at ingest;
    #    this reads the stamps and feeds the flood counter (D4c).
    try:
        index = OriginTrustIndex.from_entries(config.trusted_origins)
    except OriginConfigError as e:
        logger.error("Trust roots cannot be honored; suspending machine speed: %s", e)
        return GuardVerdict(
            GuardState.GUARDS_UNAVAILABLE,
            True,
            decision_rule("response.guards_config", _first_line(e)),
        )
    unverified = [f for f in evidence_origins if not _origin_auto_verified(f, index)]
    if unverified:
        trip_rule = await breaker.note_origin_unverified()
        rule = decision_rule("response.origin_unverified", len(unverified))
        logger.warning(
            "Guard held %s on %s: %s (%s)%s",
            action_type,
            target_ip or target_hostname,
            rule,
            ", ".join(sorted({f.finding_id for f in unverified})),
            " (trip rule: %s)" % trip_rule if trip_rule else "",
        )
        return GuardVerdict(
            GuardState.ORIGIN_UNVERIFIED, True, rule, tripped=trip_rule is not None
        )

    # 4. Blast-radius quota: the only check that mutates counters (the spend
    #    happens at guard time — an action that pends on its own quota verdict
    #    still consumed a slot, the overshoot the breaker exists to catch).
    if spend_quota:
        quota_verdict = await quota.record_and_check(action_type, target_ip, config)
    else:
        quota_verdict = await quota.check_only(action_type, target_ip, config)
    if quota_verdict.state is QuotaState.SOFT_EXCEEDED:
        return GuardVerdict(GuardState.QUOTA_SOFT, True, quota_verdict.rule)
    if quota_verdict.state is QuotaState.HARD_EXCEEDED:
        await breaker.trip_on_quota(quota_verdict)
        logger.warning(
            "Guard held %s on %s: %s — breaker opened",
            action_type,
            target_ip or target_hostname,
            quota_verdict.rule,
        )
        return GuardVerdict(
            GuardState.QUOTA_HARD, True, quota_verdict.rule, tripped=True
        )

    return GuardVerdict(
        GuardState.ALLOWED, False, decision_rule("response.guards_passed", True)
    )


class _GuardLoop:
    """One private event-loop thread for the chain's asyncio-native pieces.

    The breaker and quota are constructed once and served by this loop for
    their whole life; sync enforcement sites submit coroutines through
    :meth:`run`. A daemon thread, started lazily on first use — a deployment
    that never responds pays nothing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(
                    target=loop.run_forever,
                    name="vigil-guard-chain",
                    daemon=True,
                ).start()
                self._loop = loop
            return self._loop

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        loop = self._ensure()
        return asyncio.run_coroutine_threadsafe(coro, loop).result()


_GUARD_LOOP = _GuardLoop()


def evaluate_guards_sync(
    config: GuardConfig,
    breaker: ContainmentBreaker,
    quota: ContainmentQuota,
    action_type: str,
    target_ip: Optional[str],
    target_hostname: Optional[str],
    evidence_origins: Sequence[FindingOriginStatus],
    *,
    spend_quota: bool = True,
) -> GuardVerdict:
    """:func:`evaluate_guards` for a caller without an event loop.

    Bounded by ``GUARD_EVALUATION_TIMEOUT_SECONDS``; a timeout or any
    unexpected failure fails closed to ``GUARDS_UNAVAILABLE`` — logged at
    error, never read as "allow", because a guard that crashes open is not
    a guard.
    """
    try:
        coro = asyncio.wait_for(
            evaluate_guards(
                action_type,
                target_ip,
                target_hostname,
                evidence_origins,
                config,
                breaker,
                quota,
                spend_quota=spend_quota,
            ),
            GUARD_EVALUATION_TIMEOUT_SECONDS,
        )
        return _GUARD_LOOP.run(coro)
    except TimeoutError:
        logger.error(
            "Guard chain evaluation timed out after %.1fs; suspending "
            "machine-speed response",
            GUARD_EVALUATION_TIMEOUT_SECONDS,
        )
        return GuardVerdict(
            GuardState.GUARDS_UNAVAILABLE,
            True,
            decision_rule("response.guards_timeout", GUARD_EVALUATION_TIMEOUT_SECONDS),
        )
    except Exception as e:  # noqa: BLE001 — fail closed on every failure shape
        logger.error(
            "Guard chain evaluation failed; suspending machine-speed response: %s", e
        )
        return GuardVerdict(
            GuardState.GUARDS_UNAVAILABLE,
            True,
            decision_rule("response.guards_error", _first_line(e)),
        )


class GuardChain:
    """The chain's dependencies, built once and fail-closed on bad config.

    A :class:`GuardConfigError` at construction suspends machine-speed
    response — every evaluation returns ``GUARDS_UNAVAILABLE`` — rather than
    running on guessed blast bounds: the contract guards_config ships.
    ``breaker``/``quota`` are injectable for tests; without them the real
    Redis-backed instances are built on the chain's own loop.
    """

    def __init__(
        self,
        config: Optional[GuardConfig] = None,
        *,
        breaker: Optional[ContainmentBreaker] = None,
        quota: Optional[ContainmentQuota] = None,
    ):
        self._config_error: Optional[str] = None
        if config is None:
            try:
                config = GuardConfig.from_settings()
            except GuardConfigError as e:
                self._config_error = _first_line(e)
        self.config = config
        self.breaker = breaker or ContainmentBreaker(config)
        self.quota = quota or ContainmentQuota()

    @property
    def available(self) -> bool:
        return self._config_error is None

    def unavailable_rule(self) -> str:
        return decision_rule("response.guards_config", self._config_error or "unknown")

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Await ``coro`` on the chain's loop — for callers holding a bare
        coroutine of the chain's dependencies (the escalation claim)."""
        return _GUARD_LOOP.run(coro)

    def evaluate_sync(
        self,
        action_type: str,
        target_ip: Optional[str],
        target_hostname: Optional[str],
        evidence_origins: Sequence[FindingOriginStatus],
        *,
        spend_quota: bool = True,
    ) -> GuardVerdict:
        if not self.available:
            logger.error(
                "Guard chain unavailable (%s); every action waits for a person",
                self._config_error,
            )
            return GuardVerdict(
                GuardState.GUARDS_UNAVAILABLE, True, self.unavailable_rule()
            )
        return evaluate_guards_sync(
            self.config,
            self.breaker,
            self.quota,
            action_type,
            target_ip,
            target_hostname,
            evidence_origins,
            spend_quota=spend_quota,
        )


_shared_chain: Optional[GuardChain] = None


def shared_guard_chain() -> GuardChain:
    """The process-wide chain: one config build, one breaker, one quota.

    The daemon constructs services freely; the guards are daemon-wide state
    (the breaker is daemon-wide by spec), so every enforcement site —
    creation, execution, dry-run — shares one chain. Tests inject their own
    via the service's ``guards`` argument instead.
    """
    global _shared_chain
    if _shared_chain is None:
        _shared_chain = GuardChain()
    return _shared_chain

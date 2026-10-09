"""Persistence for the policy fast path: load evaluating policies, record
every evaluation, backfill agreements, suspend on drift, retire stale
policies.

The store is the only DB-facing module of the fast path's runtime half (the
maturity job owns compile-time reads). Functions are synchronous and
session-scoped — the daemon hook runs them via ``asyncio.to_thread`` — and
they raise on failure rather than degrade quietly: the hook is the single
catch point that fails closed to the LLM path, because a triage whose
decision row could not be written is an unlogged decision, and the audit
rule ("what was trusted, and why, is reconstructable per finding") forbids
acting on one.

Load order is the documented evaluation order: active rows first (a hit
there saves the LLM — the point of the path), then shadow, then suspended
(which evaluates as shadow); within a state, policy id ascending and version
descending, so the newest compile of an archetype is scanned before its
elders.

Row state, not the IR's embedded ``state``, is the lifecycle truth: at load
the document is re-pinned to the row's state column (the content hash
excludes state, so the row's pinned hash still validates — a tampered
document fails ``PolicyIR.from_dict`` and is skipped with an error logged,
never evaluated).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, List, Mapping, Optional, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult, Result

from core.policy_compiler.evaluator import PolicyEvaluation
from core.policy_compiler.models import PolicyIR, PolicyValidationError
from core.storage.connection import get_db_manager
from core.storage.models import CompiledPolicy, CompiledPolicyDecision
from core.time import utcnow

logger = logging.getLogger(__name__)

# States that evaluate (candidate and retired never reach the evaluator).
EVALUATING_STATES = ("active", "shadow", "suspended")


def _rowcount(result: Result) -> int:
    """Affected-row count of an UPDATE (``Result`` has no rowcount in the
    SQLAlchemy stubs; the object ``Session.execute`` returns at runtime is a
    ``CursorResult``, which does)."""
    return cast(CursorResult, result).rowcount


# State rank for the documented evaluation order (lower scans first).
_STATE_RANK = {"active": 0, "shadow": 1, "suspended": 2}

# Lifecycle actors recorded when the daemon's own safeguards transition a
# policy — distinct from a console username so the audit shows who acted.
DRIFT_ACTOR = "system:drift_auto_brake"
STALENESS_ACTOR = "system:staleness"


def load_evaluating_policies() -> List[PolicyIR]:
    """Validated IRs of every evaluating row, in documented scan order.

    A row whose stored document fails load validation is skipped with an
    error logged — a tampered or malformed policy is never evaluated, and
    one bad row must not take down the others.
    """
    with get_db_manager().session_scope() as session:
        rows = (
            session.execute(
                select(CompiledPolicy).where(
                    CompiledPolicy.state.in_(EVALUATING_STATES)
                )
            )
            .scalars()
            .all()
        )

        policies: List[PolicyIR] = []
        for row in rows:
            document: Optional[Mapping[str, Any]] = getattr(row, "policy_ir", None)
            if not isinstance(document, Mapping):
                logger.error(
                    "compiled policy %s v%s: policy_ir is not a document; skipping",
                    row.policy_id,
                    row.version,
                )
                continue
            # The row's state column is the lifecycle truth; the row's
            # content_hash column is the pinned identity the compiler wrote.
            # State is hash-excluded, so the pin still validates after the swap.
            pinned = dict(document)
            pinned["state"] = row.state
            pinned["content_hash"] = row.content_hash
            try:
                policies.append(PolicyIR.from_dict(pinned))
            except PolicyValidationError as e:
                logger.error(
                    "compiled policy %s v%s failed load validation; skipping: %s",
                    row.policy_id,
                    row.version,
                    e,
                )

    policies.sort(
        key=lambda p: (
            _STATE_RANK.get(p.state, len(_STATE_RANK)),
            p.policy_id,
            -p.version,
        )
    )
    return policies


def record_decision(
    finding_id: str,
    evaluation: Optional[PolicyEvaluation],
    evaluation_us: int,
) -> Optional[int]:
    """Write one decision row for one evaluation (hit or miss); row id back.

    Outcome follows the evaluation: an ACTIVE hit ``applied``, a SHADOW hit
    ``shadow_logged``, a miss ``no_match`` (policy columns NULL — the schema's
    pairing CHECKs pin this).
    """
    with get_db_manager().session_scope() as session:
        row = CompiledPolicyDecision(
            finding_id=finding_id,
            evaluation_us=evaluation_us,
            evaluated_at=utcnow(),
        )
        if evaluation is not None:
            row.policy_id = evaluation.policy_id
            row.policy_version = evaluation.policy_version
            row.content_hash = evaluation.content_hash
            row.mode = evaluation.mode.value
            row.decision = evaluation.decision.as_triage_result()
            row.outcome = (
                "applied" if evaluation.mode.value == "active" else "shadow_logged"
            )
        else:
            row.outcome = "no_match"
        session.add(row)
        session.flush()
        return int(row.id)


def backfill_llm_agreement(
    decision_row_id: int,
    actual_result: Mapping[str, Any],
    agrees: bool,
) -> bool:
    """Backfill the shadow row's agreement with the eventual LLM triage.

    ``agreement_source='llm'`` — the comparison the drift counter reads. The
    pairing CHECK pins ``actual_decision``/``agrees``/``agreement_source`` to
    move together.
    """
    with get_db_manager().session_scope() as session:
        result = session.execute(
            update(CompiledPolicyDecision)
            .where(CompiledPolicyDecision.id == decision_row_id)
            .values(
                actual_decision=dict(actual_result),
                agreement_source="llm",
                agrees=agrees,
            )
        )
        return bool(_rowcount(result))


def disagreements_in_window(
    policy_id: str, policy_version: int, window_days: int
) -> int:
    """Recorded LLM/analyst disagreements for one policy version in the window.

    The drift counter the auto-brake reads — counted from the same decision
    rows the audit sees.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    with get_db_manager().session_scope() as session:
        count = session.execute(
            select(CompiledPolicyDecision.id).where(
                CompiledPolicyDecision.policy_id == policy_id,
                CompiledPolicyDecision.policy_version == policy_version,
                CompiledPolicyDecision.agrees.is_(False),
                CompiledPolicyDecision.evaluated_at >= cutoff,
            )
        ).all()
        return len(count)


def suspend_for_drift(policy_id: str, policy_version: int, reason: str) -> bool:
    """The drift auto-brake: active/shadow -> suspended, actor stamped.

    Idempotent: an already-suspended (or retired/candidate) row transitions
    nothing and returns False. Never deletes — suspension is a lifecycle
    state, and the row stays for audit.
    """
    with get_db_manager().session_scope() as session:
        result = session.execute(
            update(CompiledPolicy)
            .where(
                CompiledPolicy.policy_id == policy_id,
                CompiledPolicy.version == policy_version,
                CompiledPolicy.state.in_(("active", "shadow")),
            )
            .values(
                state="suspended",
                suspended_by=DRIFT_ACTOR,
                suspended_at=utcnow(),
            )
        )
        affected = _rowcount(result)
        if affected:
            logger.warning(
                "Drift auto-brake suspended compiled policy %s v%s: %s",
                policy_id,
                policy_version,
                reason,
            )
        return bool(affected)


def retire_stale_policies(window_days: int) -> List[str]:
    """Retire every evaluating policy with no recorded decision in the window.

    Staleness is policy-level evidence — the archetype has gone quiet — so
    every still-evaluating version of a quiet policy retires, not just the
    newest compile (an elder left evaluating would start matching again once
    the latest went retired). Idempotent like ``suspend_for_drift``:
    candidate and already-retired rows are untouched; returns the policy ids
    retired by this pass. The maturity pass owns when to call this; the
    single-writer transition lives here.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    with get_db_manager().session_scope() as session:
        quiet_ids = (
            select(CompiledPolicy.policy_id)
            .where(
                CompiledPolicy.state.in_(("shadow", "active")),
                ~select(CompiledPolicyDecision.id)
                .where(
                    CompiledPolicyDecision.policy_id == CompiledPolicy.policy_id,
                    CompiledPolicyDecision.evaluated_at >= cutoff,
                )
                .exists(),
            )
            .distinct()
        )
        quiet = list(session.execute(quiet_ids).scalars().all())
        if not quiet:
            return []
        session.execute(
            update(CompiledPolicy)
            .where(
                CompiledPolicy.policy_id.in_(quiet),
                CompiledPolicy.state.in_(("shadow", "active")),
            )
            .values(state="retired", retired_by=STALENESS_ACTOR, retired_at=utcnow())
        )
        logger.info("Staleness retired compiled policies: %s", ", ".join(quiet))
        return sorted(quiet)

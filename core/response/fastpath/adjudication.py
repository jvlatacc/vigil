"""Speculative-action adjudication: the brief, the verdict, the review seam.

The slow path of the dual-track design, in one module's worth of seams:

- ``build_adjudication_brief`` / ``adjudication_hypothesis`` — pure
  renderers from a committed speculative row: what the adjudicator reads
  and what belief it tests. Both are built from the row as the ledger
  holds it, never from an in-memory decision.
- ``parse_verdict`` / ``verdict_from_events`` — the run's verdict, read
  from the CONCLUDE decision the run journaled, or None.
- ``consume_verdict`` — the review seam. Maps a verdict onto the rollback
  service: release lifts the restriction, escalate creates the full
  containment through the unmodified approval pipeline, retain extends
  the TTL once, bounded. Anything it cannot act on is refused, said so
  on the run, and left to the TTL sweep.
- ``consume_completed_adjudications`` — the scheduled scan: terminal
  adjudication runs, one verdict each, once.

Authority, in one place (locked decision 5): a verdict applies only while
the row is still ``speculative``. A human decision, the TTL sweep or an
earlier verdict resolved it first, and the late verdict is recorded as
superseded and takes no action — including the disagreement with a human
resolver, which the run row carries. The fail-safe is never the verdict:
whatever the adjudicator says, the TTL sweep releases a row past expiry.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

from sqlalchemy import select

from core.response.approval_service import ActionStatus, PendingAction
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.rollback import (
    RELEASE_REASON_ADJUDICATED,
    SOURCE_ADJUDICATOR,
    EscalationRequest,
    RollbackService,
)
from core.storage.connection import get_db_manager
from core.storage.models import WorkflowRun

logger = logging.getLogger(__name__)

# The verdict vocabulary the brief asks for — the spec's three resolutions.
VERDICT_RELEASE = "release"
VERDICT_ESCALATE = "escalate"
VERDICT_RETAIN = "retain"
VERDICTS = frozenset({VERDICT_RELEASE, VERDICT_ESCALATE, VERDICT_RETAIN})

# The verdict consumer's declared actor: distinct from the fast path (which
# creates rows), the TTL sweep (which releases past expiry) and any person.
# The run id rides on the run row; the actor name stays one constant so a
# released row's record reads the same everywhere.
ADJUDICATOR_ACTOR = "adjudicator"


def adjudicator_actor(run_id: str) -> str:
    """The actor name for one adjudication run's resolutions."""
    return f"{ADJUDICATOR_ACTOR}:{run_id}"


# What the run row's ``trigger_context.verdict_status`` can say. ``pending``
# is written at enqueue; the scan moves a terminal run to exactly one of the
# others, once — the marker is what makes the scan idempotent.
VERDICT_PENDING = "pending"
VERDICT_CONSUMED = "consumed"
VERDICT_SUPERSEDED = "superseded"
VERDICT_REFUSED = "refused"

# Terminal workflow_runs statuses the scan will pick up. ``completed`` runs
# are read for a verdict; anything else ended without one.
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled")

# Rows examined per scan tick. Each read is one HTTP call to the agent
# layer; a bounded batch keeps a backlog of finished runs from holding the
# daemon's event loop.
CONSUME_BATCH = 10


@dataclass(frozen=True)
class FastPathVerdict:
    """The adjudicator's verdict, parsed from the journaled decision.

    ``confidence`` is None unless the run named a probability: a
    non-confidence number is the caller inflating the claim, and nothing
    downstream may read it as one.
    """

    verdict: str
    rationale: str = ""
    confidence: Optional[float] = None
    # retain only: the extension asked for, in seconds. None asks for the
    # config default; the retain verb clamps whatever arrives.
    retention_seconds: Optional[int] = None
    # escalate only: the full containment action asked for. A missing or
    # shapeless proposal refuses the verdict — escalation never guesses.
    proposed_full_action: Optional[Dict[str, Any]] = None


def parse_verdict(decision: Mapping[str, Any]) -> Optional[FastPathVerdict]:
    """The verdict a CONCLUDE decision carries, or None.

    A decision that names no verdict — an intake shadow's CONCLUDE, a
    verb that is not CONCLUDE, a verdict outside the vocabulary — parses
    to None: nothing here guesses what a run meant.
    """
    if not isinstance(decision, Mapping):
        return None
    if decision.get("action") != "CONCLUDE":
        return None
    verdict = decision.get("verdict")
    if verdict not in VERDICTS:
        return None
    confidence: Optional[float] = None
    stated = decision.get("stated_confidence")
    if isinstance(stated, (int, float)) and not isinstance(stated, bool):
        if 0.0 <= float(stated) <= 1.0:
            confidence = float(stated)
    retention: Optional[int] = None
    asked = decision.get("retention_seconds")
    if (
        verdict == VERDICT_RETAIN
        and isinstance(asked, (int, float))
        and not isinstance(asked, bool)
        and asked > 0
    ):
        retention = int(asked)
    proposed = decision.get("proposed_full_action")
    full_action = dict(proposed) if isinstance(proposed, Mapping) else None
    return FastPathVerdict(
        verdict=str(verdict),
        rationale=str(decision.get("rationale") or ""),
        confidence=confidence,
        retention_seconds=retention,
        proposed_full_action=full_action,
    )


def verdict_from_events(
    events: List[Dict[str, Any]],
) -> Optional[FastPathVerdict]:
    """The run's verdict: the last verdict-bearing CONCLUDE it journaled."""
    for event in reversed(events):
        if not isinstance(event, Mapping) or event.get("kind") != "decision":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        decision = payload.get("decision")
        if not isinstance(decision, Mapping):
            continue
        verdict = parse_verdict(decision)
        if verdict is not None:
            return verdict
    return None


# ---------------------------------------------------------------------------
# The brief — built from the row as the ledger holds it
# ---------------------------------------------------------------------------


def _parameter(row: PendingAction, key: str, default: Any) -> Any:
    return (row.parameters or {}).get(key, default)


def _signals(row: PendingAction) -> Dict[str, Any]:
    signals = _parameter(row, "signals", {})
    return dict(signals) if isinstance(signals, Mapping) else {}


def _finding_id(row: PendingAction) -> str:
    finding = _signals(row).get("finding_id")
    return str(finding) if finding else "unknown"


def _simulation_label(row: PendingAction) -> str:
    return "simulated" if _parameter(row, "simulation", False) else "enforced"


def _ttl(row: PendingAction) -> str:
    ttl = _parameter(row, "ttl_seconds", "unrecorded")
    expires = _parameter(row, "expires_at", "unrecorded")
    return f"{ttl}s, expiring {expires}"


def _rollback_recipe(row: PendingAction) -> str:
    recipe = _parameter(row, "rollback", {})
    if not isinstance(recipe, Mapping):
        return "unrecorded"
    external_ref = recipe.get("external_ref")
    return (
        f"adapter {recipe.get('adapter', 'unrecorded')} releasing "
        f"{recipe.get('action_type', 'unrecorded')} on "
        f"{recipe.get('target', 'unrecorded')}"
        + (f" (external ref {external_ref})" if external_ref else "")
    )


def _deciding_rule(row: PendingAction) -> str:
    rule = _parameter(row, "rule", "")
    return str(rule) if rule else "unrecorded"


def build_adjudication_brief(row: PendingAction) -> str:
    """The brief one speculative row's adjudication runs on.

    Pure render from the committed row — the record the fast path wrote,
    the verdict contract it is being asked to rule on, and the authority
    that outranks it. The brief includes the speculative-action record by
    construction: every caller holds a row that was read back from the
    ledger, so the record is present, not hoped for.
    """
    simulated = _simulation_label(row)
    return f"""\

## Speculative action under adjudication

A speculative containment restriction is LIVE on {row.target} and this run
decides its fate. The fast path applied it with no model call and no person;
you are the slow path's second opinion over the record below. You execute
nothing: release, escalation and retention are applied by the consumer of
your verdict, never by this run.

- Action: {row.action_id} ({row.action_type})
- Applied by: {row.created_by} — deciding rule: {_deciding_rule(row)}
- Enforcement: {simulated} — a simulated row records intent only; treat
  its absence of external effect when you weigh the benign account.
- Time box: {_ttl(row)}
- Rollback recipe: {_rollback_recipe(row)}
- Triggering finding: {_finding_id(row)}
- Signal snapshot — exactly the fields the deciding rule read:
  {sorted(_signals(row).items())}

## Your verdict

Test the stated hypothesis against the evidence as on any adjudication,
then CONCLUDE with the verdict field set to exactly one of:

- "release" — the benign account stood, or the signals do not support
  restricting this address any longer.
- "escalate" — full containment is warranted: set proposed_full_action to
  an object with action_type (a full containment type — a speculative
  micro-action is refused) and optionally target. The proposal goes to
  the human approval gate; nothing here enforces it.
- "retain" — the restriction is warranted but not yet settled: set
  retention_seconds to the extension you are asking for. It is clamped
  to the row's ceiling and applies at most once.

For this run, proposed_workflow is "none": the verdict fields are the
conclusion, and the catalogue question does not apply. Whatever you
conclude, the row resolves no later than its expiry — a missing, refused
or late verdict releases it by the TTL sweep.
"""


def adjudication_hypothesis(row: PendingAction) -> str:
    """The belief the run tests: that the restriction is warranted.

    Stated as intake's intent was — the adversary claim the lead tests
    against the seeded benign account, with the record's deciding rule
    and signal snapshot as the grounds.
    """
    return (
        f"The speculative restriction on {row.target} is warranted: the "
        f"deciding rule ({_deciding_rule(row)}) read signal evidence "
        f"consistent with an attacker operating from that address."
    )


# ---------------------------------------------------------------------------
# The review seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictOutcome:
    """What consuming one verdict did.

    ``applied`` — a rollback verb ran and claimed the row.
    ``superseded`` — the row was already resolved (a human, the sweep, an
    earlier verdict); the verdict is recorded on the run and nothing else
    moved. ``refused`` — the verdict could not be acted on; the run row
    says why, and the TTL sweep stays the fail-safe.
    """

    action_id: str
    run_id: str
    verdict: Optional[str]
    applied: bool
    superseded: bool
    detail: str


def _resolved_by(action: PendingAction) -> str:
    """Who resolved a no-longer-speculative row, from the row's own record."""
    if action.status == ActionStatus.ROLLED_BACK.value:
        result = action.execution_result or {}
        reason = result.get("reason", "unknown reason")
        actor = result.get("actor", "unknown actor")
        return f"released ({reason}) by {actor}"
    if action.status == ActionStatus.ESCALATED.value:
        parameters = action.parameters or {}
        escalation = parameters.get("escalation") or {}
        source = escalation.get("source", "unknown source")
        return f"escalated ({source}) to {escalation.get('action_id', 'unknown')}"
    if action.status == ActionStatus.EXECUTED.value:
        return "the full pipeline executed the escalated action"
    return f"resolved to {action.status}"


def _mark_run(run_id: str, status: str, **fields: Any) -> None:
    """Record the verdict outcome on the run row — the adjudication's record.

    Best effort: a run row that never landed (begin_run is best effort
    too) leaves nothing to mark, and the row's own record still says what
    happened.
    """
    db = get_db_manager()
    with db.session_scope() as session:
        row = session.get(WorkflowRun, run_id)
        if row is None:
            return
        context = dict(row.trigger_context or {})
        context["verdict_status"] = status
        context.update(fields)
        row.trigger_context = context


def _escalation_request(
    verdict: FastPathVerdict, action: PendingAction
) -> Optional[EscalationRequest]:
    """The escalation the verdict asks for, or None when it names none.

    The target defaults to the speculative row's own target — the same
    adversary — and the type must be present: an escalation without a
    full containment type is refused, never guessed.
    """
    proposed = verdict.proposed_full_action or {}
    action_type = proposed.get("action_type")
    if not isinstance(action_type, str) or not action_type:
        return None
    target = proposed.get("target") or action.target
    if not isinstance(target, str) or not target:
        return None
    return EscalationRequest(
        action_type=action_type,
        target=target,
        confidence=verdict.confidence if verdict.confidence is not None else 0.0,
        reasoning=verdict.rationale,
    )


def consume_verdict(
    action_id: str,
    verdict: FastPathVerdict,
    *,
    run_id: str,
    config: FastPathConfig,
    rollback: Optional[RollbackService] = None,
) -> VerdictOutcome:
    """Apply one adjudicated verdict at the review seam.

    The verdict wins only over a live row. The supersession check and the
    verbs' own guarded claims are two halves of one rule: whatever raced
    the adjudicator — a person's release, the TTL sweep, a person's
    approval — is resolved first, and the late verdict records the
    disagreement on the run and changes nothing else.
    """
    service = rollback or RollbackService(config=config)
    actor = adjudicator_actor(run_id)
    action = service.approvals.get_action(action_id)
    if action is None:
        detail = "the speculative row no longer exists"
        _mark_run(run_id, VERDICT_REFUSED, verdict=verdict.verdict, detail=detail)
        return VerdictOutcome(action_id, run_id, verdict.verdict, False, False, detail)
    if action.status != ActionStatus.SPECULATIVE.value:
        resolver = _resolved_by(action)
        detail = (
            f"the row was resolved by {resolver} before the verdict arrived; "
            f"the disagreement is recorded here and nothing was changed"
        )
        _mark_run(
            run_id,
            VERDICT_SUPERSEDED,
            verdict=verdict.verdict,
            resolved_by=resolver,
            detail=detail,
        )
        return VerdictOutcome(action_id, run_id, verdict.verdict, False, True, detail)

    applied = False
    detail = ""
    if verdict.verdict == VERDICT_RELEASE:
        outcome = service.release(action_id, RELEASE_REASON_ADJUDICATED, actor)
        applied, detail = outcome.released, outcome.detail
    elif verdict.verdict == VERDICT_ESCALATE:
        request = _escalation_request(verdict, action)
        if request is None:
            detail = "escalation named no full containment action; refusing to guess"
        else:
            outcome = service.escalate(
                action_id, request, decided_by=actor, source=SOURCE_ADJUDICATOR
            )
            applied, detail = outcome.escalated, outcome.detail
    else:
        outcome = service.retain(action_id, verdict.retention_seconds, actor=actor)
        applied, detail = outcome.extended, outcome.detail

    if applied:
        _mark_run(run_id, VERDICT_CONSUMED, verdict=verdict.verdict, detail=detail)
        return VerdictOutcome(action_id, run_id, verdict.verdict, True, False, detail)

    # Either the verdict was refused outright (still speculative) or the
    # verb lost the claim to a racer (resolved in between) — the row's
    # state now says which.
    after = service.approvals.get_action(action_id)
    if after is not None and after.status != ActionStatus.SPECULATIVE.value:
        resolver = _resolved_by(after)
        detail = (
            f"the row was resolved by {resolver} while the verdict was "
            "being applied; the disagreement is recorded here and the "
            "verdict took no action"
        )
        _mark_run(
            run_id,
            VERDICT_SUPERSEDED,
            verdict=verdict.verdict,
            resolved_by=resolver,
            detail=detail,
        )
        return VerdictOutcome(action_id, run_id, verdict.verdict, False, True, detail)
    _mark_run(run_id, VERDICT_REFUSED, verdict=verdict.verdict, detail=detail)
    return VerdictOutcome(action_id, run_id, verdict.verdict, False, False, detail)


# ---------------------------------------------------------------------------
# The scheduled scan
# ---------------------------------------------------------------------------


def _default_events_reader() -> Callable[[str], Awaitable[Optional[List[Dict]]]]:
    # Imported at call time: the reader is agent-layer plumbing, and the
    # module stays import-light for every consumer that only wants the
    # brief or the parse.
    from core.agents.projections import read_events

    return read_events


def _pending_adjudications(batch: int) -> List[Tuple[str, str, str]]:
    """Terminal adjudication runs still marked pending, oldest first.

    Returns (run_id, action_id, run_status): ``completed`` runs carry a
    verdict to read; the other terminal statuses ended without one and
    are refused without a read. Runs still executing are not here — a
    run must finish before its CONCLUDE can be final.
    """
    db = get_db_manager()
    with db.session_scope() as session:
        rows = (
            session.execute(
                select(WorkflowRun)
                .where(
                    WorkflowRun.trigger_context["speculative_action_id"].isnot(None),
                    WorkflowRun.trigger_context["verdict_status"].astext
                    == VERDICT_PENDING,
                    WorkflowRun.status.in_(TERMINAL_RUN_STATUSES),
                )
                .order_by(WorkflowRun.started_at)
                .limit(batch)
            )
            .scalars()
            .all()
        )
        pending = [
            (
                row.run_id,
                str(row.trigger_context.get("speculative_action_id") or ""),
                row.status,
            )
            for row in rows
        ]
    return [entry for entry in pending if entry[1]]


async def consume_completed_adjudications(
    batch: int = CONSUME_BATCH,
    config: Optional[FastPathConfig] = None,
    rollback: Optional[RollbackService] = None,
    events_reader: Optional[
        Callable[[str], Awaitable[Optional[List[Dict[str, Any]]]]]
    ] = None,
) -> Dict[str, int]:
    """Consume every finished adjudication's verdict, once.

    The scheduler's entry. A completed run's ledger is read for its
    verdict; a run that ended without one — budget, abort, a CONCLUDE
    that named no verdict — is marked refused and the row waits for the
    TTL sweep. A run whose agent layer is unreachable is left pending and
    retried next tick: an outage must not spend a run's verdict.
    """
    reader = events_reader or _default_events_reader()
    settings = config or FastPathConfig()
    pending = await asyncio.to_thread(_pending_adjudications, batch)
    counts = {
        "examined": len(pending),
        "consumed": 0,
        "superseded": 0,
        "refused": 0,
        "unavailable": 0,
    }
    for run_id, action_id, run_status in pending:
        if run_status != "completed":
            detail = f"the run ended {run_status} without a verdict"
            _mark_run(run_id, VERDICT_REFUSED, detail=detail)
            counts["refused"] += 1
            continue
        try:
            events = await reader(run_id)
        except Exception:
            # Unreachable is not terminal: the read is retried next tick.
            logger.exception("could not read the adjudication ledger for %s", run_id)
            counts["unavailable"] += 1
            continue
        if events is None:
            detail = "the run's ledger holds no events"
            _mark_run(run_id, VERDICT_REFUSED, detail=detail)
            counts["refused"] += 1
            continue
        verdict = verdict_from_events(events)
        if verdict is None:
            detail = "the run concluded without a verdict"
            _mark_run(run_id, VERDICT_REFUSED, detail=detail)
            counts["refused"] += 1
            continue
        outcome = await asyncio.to_thread(
            consume_verdict,
            action_id,
            verdict,
            run_id=run_id,
            config=settings,
            rollback=rollback,
        )
        if outcome.applied:
            counts["consumed"] += 1
        elif outcome.superseded:
            counts["superseded"] += 1
        else:
            counts["refused"] += 1
    return counts

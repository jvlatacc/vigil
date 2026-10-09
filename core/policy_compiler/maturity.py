"""The maturity job: operational outcomes in, compiled candidates and lifecycle
edges out.

One scheduled pass owns all three directions of the evidence:

1. **Compile** — group terminal workflow runs by archetype, read the closures
   their cases received, and compile a candidate when the evidence qualifies.
2. **Drift** — count a promoted or shadowing policy's disagreements with the
   eventual LLM outcome plus analyst reopens of policy-triaged closures, and
   auto-brake over the drift limit.
3. **Staleness** — retire a policy no windowed finding matches any more.

Every query reads operational tables only — ``workflow_runs``, ``findings``,
``finding_mitre_predictions``, ``cases``, ``case_closure_info`` — and never
``episodic_*`` (ADR 0001's compile-versus-memory boundary, the ADR 0015 line
seen from the compile side). ``tests/unit/policy_compiler/test_import_boundary.py``
holds the module to that by parsing imports, not by convention.

The semantic decisions below are the correctness heart of the feature; each
one is pinned by a test named for it.

**One outcome per run.** A run's outcome is the closure its work received:
of the cases its trigger finding is linked to, the latest in-window closure
by ``closed_at`` is the determination's current state. A retracted closure —
a ``case_closure_info`` row on a case whose status is no longer ``closed``,
which is what ``CaseWorkflowService.reopen_case`` leaves behind (it resets the
category and keeps the row) — is an **analyst override**, not an outcome: the
determination was withdrawn. Overrides are counted per run, never as an
inconsistency share, and any override in the window blocks compilation.

**Duplicate closures are not evidence.** A ``duplicate`` closure writes no
Verdict in episodic memory (``core/memory/case_distil.py``), and the same
logic binds here: it is neither a resolution nor a refutation, so it counts
in neither the numerator nor the denominator of consistency. A duplicate-heavy
archetype therefore fails eligibility on N — there is less counted evidence
than the raw case count suggests.

**Archetype identity.** The grouping key is ``(workflow_id, data_source)``;
the archetype's technique set is derived — the union of the trigger findings'
ATT&CK predictions across the runs whose outcome counts as evidence. The
brief's "technique set" is that derived identity, not a partition key:
predictions are model-emitted and noisy run to run, and partitioning by exact
set would split one archetype into fragments none of which ever reach the
minimum N. Entity-context types are the opposite cut — the intersection over
findings that carry any (absence of an entity context is absence of evidence,
not evidence of a wider match), because the IR matches them with ``all_of``:
every observed entity context carried them.

**The decision the policy replays** is the modal recorded triage of the
resolved runs' trigger findings, per field (severity, category, recommended
action), ties broken alphabetically — deterministic, and only values the IR
vocabulary accepts vote (an out-of-vocabulary value cannot be replayed, so it
cannot be what the policy claims was learned).

**Drift is one counter fed by both signals.** Disagreements are decision rows
for the policy's current version where the backfilled ``agrees`` is false —
the shadow path runs the LLM anyway, so its rows get the eventual model
outcome; analyst-sourced agreement needs a vocabulary mapping nothing defines
yet, so the reopen signal below is the analyst channel (backfilling the
``analyst`` source stays with whoever defines that mapping). Reopens are
cases linked to findings the policy triaged (``outcome='applied'`` decisions)
whose closure row exists but whose status is no longer closed, bounded by the
case's ``updated_at`` in the window — the trace a reopen leaves, since the
retraction itself rewrites the closure row in place. The brake fires when the
sum passes the drift limit; a policy both drifting and stale suspends rather
than retires — a wrong policy needs review, a quiet one only needs archiving.

**Staleness asks the evaluator.** A policy is stale when no finding in the
window matches its IR — matched by the same ``evaluate()`` the fast path
runs, so there is one definition of matching everywhere. The scan caps at the
most recent windowed findings for the policy's data sources; a policy whose
recent findings never match is stale for the purpose the lifecycle names.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.platform.runtime_config import get_ai_operations_setting
from core.policy_compiler.compiler import (
    ArchetypeEvidence,
    CompileError,
    archetype_policy_id,
    compile_policy,
)
from core.policy_compiler.config import (
    DRIFT_LIMIT_DEFAULT,
    DRIFT_LIMIT_KEY,
    MIN_CONSISTENCY_DEFAULT,
    MIN_CONSISTENCY_KEY,
    MIN_RUNS_DEFAULT,
    MIN_RUNS_KEY,
    WINDOW_DAYS_DEFAULT,
    WINDOW_DAYS_KEY,
)
from core.policy_compiler.evaluator import _observed_entity_types, evaluate
from core.policy_compiler.models import (
    RECOMMENDED_ACTIONS,
    SEVERITIES,
    PolicyIR,
    build_render_hashes,
)
from core.policy_compiler.renderers import RENDER_TARGETS, render
from core.storage.models import (
    Case,
    CaseClosureInfo,
    CompiledPolicy,
    CompiledPolicyDecision,
    Finding,
    FindingMitrePrediction,
    WorkflowRun,
)
from core.storage.models.base import case_findings
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow

logger = logging.getLogger(__name__)

# The pass that owns the evidence both ways runs at most once, here or on any
# other instance: the advisory transaction lock is held for the pass's whole
# transaction and released at its commit. Same mechanism core/backup/create.py
# uses for its single-flight; a key string hashed to the bigint the lock takes,
# so the object id is stable across processes and deployments.
LOCK_KEY = "policy_compiler.maturity_pass"
LOCK_OBJECT_ID = int.from_bytes(
    hashlib.sha256(LOCK_KEY.encode()).digest()[:8], "big", signed=True
)

# The actor the automatic lifecycle edges name. Promote/suspend/retire from the
# console name the human; the job's own edges say so.
AUTO_ACTOR = "maturity-job"

# A terminal run that did its work. ``failed`` and ``cancelled`` are crashes and
# stops — "a crash is not an outcome" (core/memory/distil.py) — and a run
# stopped at its budget ceiling still finished as ``completed`` on this side
# (core/workflows/run_bridge_router.py TERMINAL_STATUS).
COMPLETED_STATUS = "completed"

# The status ``close_case`` leaves; anything else on a case with a closure row
# means the determination was retracted.
CASE_CLOSED_STATUS = "closed"

# The closure category that is no determination at all. It counts in N as an
# inconsistency (a case closed with nothing stated proves nothing), but it is
# also what a retraction leaves behind — which is why a retracted case is read
# as an override and never as this outcome.
UNSPECIFIED_CATEGORY = "unspecified"

# The run-level outcome words, one per run, from classify_run.
REOPENED = "reopened"
DUPLICATE = "duplicate"

# Staleness scan cap: the most recent windowed findings per policy. A policy
# whose most recent findings never match is stale for the lifecycle's purpose;
# the cap keeps a noisy source from making every pass scan unbounded history.
STALENESS_SCAN_CAP = 500

# What a recorded triage must look like to be replayable. Severity and action
# have vocabularies (models.SEVERITIES / RECOMMENDED_ACTIONS); the category is
# free-ish text whose shape models._CATEGORY_RE pins — mirrored here so an
# out-of-shape recorded value cannot win the modal vote and fail the compile
# for the whole archetype.
_CATEGORY_SHAPE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")


@dataclass(frozen=True)
class ClosureObservation:
    """One linked case's closure row, with the flags the outcome rules read.

    ``in_window`` is the gatherer's bound: the row's own ``closed_at`` for an
    intact closure; for a retracted one, its ``closed_at`` or the case's
    ``updated_at`` being in window — a reopen rewrites the category in place,
    so the case row is the only dated trace it leaves.
    """

    category: str
    case_closed: bool
    in_window: bool


@dataclass(frozen=True)
class RunObservation:
    """One terminal run, its archetype fields, and its classified outcome.

    ``techniques``/``entity_types`` are the trigger finding's predictions and
    entity-context types, already normalized the way the evaluator matches.
    ``outcome`` is :func:`classify_run`'s word for the run's linked cases.
    The observed_* fields are the trigger finding's recorded triage, filtered
    to what the IR vocabulary accepts.
    """

    run_id: str
    workflow_id: str
    data_source: str
    techniques: frozenset[str]
    entity_types: frozenset[str]
    outcome: str | None
    observed_severity: str | None
    observed_category: str | None
    observed_action: str | None


def classify_run(closures: Sequence[ClosureObservation]) -> str | None:
    """One outcome word for one run's linked cases, or None for no evidence.

    Precedence: a retracted closure in the window is an override (the
    determination was withdrawn — that is what an analyst reopen is);
    otherwise the latest intact in-window closure is the outcome; otherwise
    the evidence is not in yet. ``closures`` is ordered by ``closed_at``
    ascending, so the last intact one wins.
    """
    for closure in closures:
        if not closure.case_closed and closure.in_window:
            return REOPENED
    latest = next(
        (c for c in reversed(closures) if c.case_closed and c.in_window), None
    )
    return latest.category if latest is not None else None


def accumulate_outcomes(
    runs: Sequence[RunObservation],
) -> tuple[dict[str, int], int]:
    """Counted outcomes by closure category, and the override count.

    ``duplicate`` is excluded outright (it must not inflate consistency — a
    duplicate-heavy archetype fails on N instead), a ``reopened`` run is an
    override and never an outcome, and a run with no in-window outcome
    contributes neither.
    """
    outcomes: dict[str, int] = {}
    overrides = 0
    for run in runs:
        if run.outcome == REOPENED:
            overrides += 1
        elif run.outcome is None or run.outcome == DUPLICATE:
            continue
        else:
            outcomes[run.outcome] = outcomes.get(run.outcome, 0) + 1
    return outcomes, overrides


def consistency_of(outcomes: Mapping[str, int]) -> float:
    """Resolved share of the counted outcomes: the policy's later confidence."""
    total = sum(outcomes.values())
    if total == 0:
        return 0.0
    return outcomes.get("resolved", 0) / total


def _modal(values: Iterable[str | None]) -> str | None:
    """Most common value; ties break alphabetically, so the vote is stable."""
    counts = Counter(v for v in values if v)
    if not counts:
        return None
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def build_evidence(
    workflow_id: str,
    data_source: str,
    runs: Sequence[RunObservation],
    *,
    window_days: int,
) -> ArchetypeEvidence | None:
    """Assemble one archetype's evidence, or None when it cannot match.

    Identity pools the technique predictions and entity-context types of the
    runs whose outcome counts as evidence; the decision replays the modal
    recorded triage of the resolved runs. An archetype whose counted runs
    predict no techniques returns None — such a document could never match a
    finding honestly, and the compiler refuses it (``CompileError``).
    """
    outcomes, overrides = accumulate_outcomes(runs)
    evidence_runs = [
        run for run in runs if run.outcome not in (None, DUPLICATE, REOPENED)
    ]
    techniques: set[str] = set()
    for run in evidence_runs:
        techniques.update(run.techniques)

    # Entity types the archetype's evidence findings all carried (runs without
    # one do not vote — all_of claims what was always there, nothing more).
    voters = [run.entity_types for run in evidence_runs if run.entity_types]
    common_types: set[str] = (
        set.intersection(*(set(voter) for voter in voters)) if voters else set()
    )

    if not techniques:
        return None

    resolved = [run for run in evidence_runs if run.outcome == "resolved"]
    return ArchetypeEvidence(
        workflow_id=workflow_id,
        window_days=window_days,
        data_sources=[data_source],
        techniques=sorted(techniques),
        entity_context_types=sorted(common_types),
        outcomes=outcomes,
        consistency=consistency_of(outcomes),
        analyst_overrides=overrides,
        observed_severity=_modal(run.observed_severity for run in resolved),
        observed_category=_modal(run.observed_category for run in resolved),
        observed_recommended_action=_modal(run.observed_action for run in resolved),
    )


def is_eligible(
    evidence: ArchetypeEvidence, *, min_runs: int, min_consistency: float
) -> bool:
    """The compile gate: enough outcomes, consistently resolved, no overrides.

    Reopened cases in the window block regardless of the counts — an override
    is a determination withdrawn, the strongest evidence the archetype is not
    settled.
    """
    return (
        evidence.total() >= min_runs
        and evidence.consistency >= min_consistency
        and evidence.analyst_overrides == 0
    )


def _replayable_severity(*values: Any) -> str | None:
    """The first value in the severity vocabulary, else None."""
    for value in values:
        if isinstance(value, str) and value in SEVERITIES:
            return value
    return None


def _replayable_action(value: Any) -> str | None:
    return value if isinstance(value, str) and value in RECOMMENDED_ACTIONS else None


def _replayable_category(value: Any) -> str | None:
    return value if isinstance(value, str) and _CATEGORY_SHAPE.match(value) else None


# --- The pass ---------------------------------------------------------------


def run_maturity_pass_sync(now: datetime | None = None) -> dict[str, int]:
    """One pass in a worker thread: lock, gather, compile, apply lifecycle.

    Returns a counts report for the daemon log and the tests. Single-flight:
    a second instance's ``pg_try_advisory_xact_lock`` fails and it reports a
    skipped pass rather than compiling against the first one's transaction.
    """
    if now is None:
        now = utcnow()

    min_runs = int(get_ai_operations_setting(MIN_RUNS_KEY, MIN_RUNS_DEFAULT))
    min_consistency = float(
        get_ai_operations_setting(MIN_CONSISTENCY_KEY, MIN_CONSISTENCY_DEFAULT)
    )
    window_days = int(get_ai_operations_setting(WINDOW_DAYS_KEY, WINDOW_DAYS_DEFAULT))
    drift_limit = int(get_ai_operations_setting(DRIFT_LIMIT_KEY, DRIFT_LIMIT_DEFAULT))
    window_start = now - timedelta(days=window_days)

    report: dict[str, int] = {
        "lock_skipped": 0,
        "runs_in_window": 0,
        "archetypes_eligible": 0,
        "candidates_written": 0,
        "shadowed": 0,
        "unchanged": 0,
        "compile_errors": 0,
        "suspended": 0,
        "retired": 0,
    }

    with unit_of_work() as session:
        if not _try_lock(session):
            report["lock_skipped"] = 1
            return report

        runs = _run_observations(session, window_start)
        report["runs_in_window"] = len(runs)

        groups: dict[tuple[str, str], list[RunObservation]] = {}
        for run in runs:
            groups.setdefault((run.workflow_id, run.data_source), []).append(run)

        for (workflow_id, data_source), group in sorted(groups.items()):
            evidence = build_evidence(
                workflow_id, data_source, group, window_days=window_days
            )
            if evidence is None:
                continue
            if not is_eligible(
                evidence, min_runs=min_runs, min_consistency=min_consistency
            ):
                continue
            report["archetypes_eligible"] += 1
            _compile_and_store(
                session,
                evidence,
                now=now,
                report=report,
            )

        _apply_lifecycle(
            session,
            now=now,
            window_start=window_start,
            drift_limit=drift_limit,
            report=report,
        )

    return report


async def run_maturity_pass(now: datetime | None = None) -> dict[str, int]:
    """The pass off the event loop — the sync session work runs in a thread."""
    return await asyncio.to_thread(run_maturity_pass_sync, now)


def _try_lock(session: Session) -> bool:
    """Take the pass's advisory transaction lock; False means someone else has."""
    row = session.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_OBJECT_ID}
    ).scalar()
    return bool(row)


def _run_observations(session: Session, window_start: datetime) -> list[RunObservation]:
    """Read every terminal run in the window and classify its outcome.

    Four queries for the whole pass (runs, findings, predictions, case
    closures), joined in Python: the trigger context is JSONB, so the run to
    finding step cannot be a join, and the rest is IN-lists over the ids it
    yields. A run with no trigger finding, or whose finding predicts no
    techniques, contributes no archetype evidence — it cannot be grouped or
    matched, and counting it would grow N with evidence no policy could
    replay.
    """
    run_rows = session.execute(
        select(WorkflowRun.run_id, WorkflowRun.workflow_id, WorkflowRun.trigger_context)
        .where(
            WorkflowRun.status == COMPLETED_STATUS,
            WorkflowRun.started_at >= window_start,
        )
        .order_by(WorkflowRun.started_at)
    ).all()

    finding_ids = sorted(
        {
            str(context.get("finding_id"))
            for _, _, context in run_rows
            if isinstance(context, Mapping) and context.get("finding_id")
        }
    )
    if not finding_ids:
        return []

    finding_rows = {
        row.finding_id: row
        for row in session.execute(
            select(
                Finding.finding_id,
                Finding.data_source,
                Finding.entity_context,
                Finding.severity,
                Finding.ai_enrichment,
            ).where(Finding.finding_id.in_(finding_ids))
        ).all()
    }

    techniques: dict[str, set[str]] = {}
    for finding_id, technique_id in session.execute(
        select(
            FindingMitrePrediction.finding_id,
            FindingMitrePrediction.technique_id,
        ).where(FindingMitrePrediction.finding_id.in_(finding_ids))
    ).all():
        techniques.setdefault(finding_id, set()).add(technique_id)

    links: dict[str, list[str]] = {}
    for finding_id, case_id in session.execute(
        select(case_findings.c.finding_id, case_findings.c.case_id).where(
            case_findings.c.finding_id.in_(finding_ids)
        )
    ).all():
        links.setdefault(finding_id, []).append(case_id)

    case_ids = sorted({case_id for ids in links.values() for case_id in ids})
    closure_rows: dict[str, ClosureObservation] = {}
    if case_ids:
        for case_id, status, updated_at, category, closed_at in session.execute(
            select(
                Case.case_id,
                Case.status,
                Case.updated_at,
                CaseClosureInfo.closure_category,
                CaseClosureInfo.closed_at,
            )
            .join(CaseClosureInfo, CaseClosureInfo.case_id == Case.case_id)
            .where(Case.case_id.in_(case_ids))
            .order_by(CaseClosureInfo.closed_at)
        ).all():
            closure_rows[case_id] = ClosureObservation(
                category=category or UNSPECIFIED_CATEGORY,
                case_closed=status == CASE_CLOSED_STATUS,
                in_window=_closure_in_window(closed_at, updated_at, window_start),
            )

    observations: list[RunObservation] = []
    for run_id, workflow_id, context in run_rows:
        if not isinstance(context, Mapping):
            continue
        finding_id = context.get("finding_id")
        if not finding_id:
            continue
        finding = finding_rows.get(str(finding_id))
        if finding is None:
            continue
        run_techniques = techniques.get(finding.finding_id, set())
        if not run_techniques:
            continue

        observed = _recorded_triage(finding)
        observations.append(
            RunObservation(
                run_id=run_id,
                workflow_id=workflow_id,
                data_source=finding.data_source,
                techniques=frozenset(run_techniques),
                entity_types=_observed_entity_types(finding.entity_context),
                outcome=classify_run(
                    [
                        closure_rows[case_id]
                        for case_id in links.get(finding.finding_id, [])
                        if case_id in closure_rows
                    ]
                ),
                observed_severity=observed[0],
                observed_category=observed[1],
                observed_action=observed[2],
            )
        )
    return observations


def _closure_in_window(
    closed_at: datetime | None,
    case_updated_at: datetime | None,
    window_start: datetime,
) -> bool:
    """Whether this closure is in-window evidence, on either dated trace.

    An intact closure is dated by its own ``closed_at``. A retracted one keeps
    that timestamp but is re-read through the case's ``updated_at`` too — the
    reopen that retracted it moved the case row, and the retraction is the
    event the override rule needs to catch.
    """
    if closed_at is not None and closed_at >= window_start:
        return True
    return case_updated_at is not None and case_updated_at >= window_start


def _recorded_triage(finding: Any) -> tuple[str | None, ...]:
    """The finding's recorded triage, filtered to replayable values.

    Reads the flat keys the triage write path persists in ``ai_enrichment``
    (``services/daemon/processor.py`` ``_AI_ANALYSIS_KEYS``); the stored
    ``severity`` column is the severity fallback. Values outside the IR's
    vocabularies return None — they cannot be replayed, so they do not vote.
    """
    enrichment = finding.ai_enrichment
    if not isinstance(enrichment, Mapping):
        enrichment = {}
    severity = _replayable_severity(
        enrichment.get("severity"), getattr(finding, "severity", None)
    )
    return (
        severity,
        _replayable_category(enrichment.get("category")),
        _replayable_action(enrichment.get("recommended_action")),
    )


def _compile_and_store(
    session: Session,
    evidence: ArchetypeEvidence,
    *,
    now: datetime,
    report: dict[str, int],
) -> None:
    """Compile the evidence and write the version the store is missing.

    Dedupe is by content hash against the archetype's head version: the hash
    is clock-stable, so an unchanged archetype recompiled every pass writes
    nothing. A changed archetype appends a version — the id covers identity
    (workflow, match sets), the version covers content.
    """
    try:
        head = session.execute(
            select(CompiledPolicy.version, CompiledPolicy.content_hash)
            .where(CompiledPolicy.policy_id == archetype_policy_id(evidence))
            .order_by(CompiledPolicy.version.desc())
            .limit(1)
        ).first()
    except Exception:
        logger.exception(
            "maturity job could not read the head of %s", evidence.workflow_id
        )
        return

    try:
        result = compile_policy(
            evidence, now=now, previous_version=head.version if head else None
        )
    except CompileError as exc:
        # Eligible evidence that cannot become an honest policy is a bug in
        # the evidence or the compiler — log it, never swallow it into a
        # quiet pass.
        report["compile_errors"] += 1
        logger.error(
            "maturity job refused eligible evidence for %s: %s",
            evidence.workflow_id,
            exc,
        )
        return

    if head and head.content_hash == result.content_hash:
        report["unchanged"] += 1
        return

    document = dict(result.ir)
    try:
        # The compile validation gate: the IR must be representable in every
        # export format before it shadows (ADR 0001 — an export that cannot
        # exist means the IR overclaimed). Render digests are pinned in the
        # stored document; the content hash excludes them, so pinning keeps
        # the hash stable.
        rendered = [
            (target, render(_stored_policy(document), target))
            for target in RENDER_TARGETS
        ]
        document["renders"] = build_render_hashes(rendered)
        document["state"] = "shadow"
    except Exception as exc:
        logger.error(
            "policy %s v%s stays a candidate: renders failed validation: %s",
            result.policy_id,
            result.version,
            exc,
        )

    # The row is built once, document complete: a JSONB column does not track
    # in-place mutation, so the state flip cannot come back to patch the dict.
    session.add(
        CompiledPolicy(
            policy_id=result.policy_id,
            version=result.version,
            state=document["state"],
            policy_ir=document,
            content_hash=result.content_hash,
            maturity_evidence=dict(document["maturity"]),
            compiled_at=now,
            compiled_by=AUTO_ACTOR,
        )
    )
    report["candidates_written"] += 1

    if document["state"] == "shadow":
        # Validation gate passed: the candidate shadows. It cannot act there —
        # shadow only logs — and promotion stays human-only.
        report["shadowed"] += 1
        logger.info(
            "compiled policy %s v%s is shadowing (%s)",
            result.policy_id,
            result.version,
            document["maturity"].get("consistency"),
        )


def _stored_policy(document: Mapping[str, Any]) -> PolicyIR:
    """The document as a PolicyIR for rendering (state is not hashed)."""
    return PolicyIR.from_dict(dict(document))


def _apply_lifecycle(
    session: Session,
    *,
    now: datetime,
    window_start: datetime,
    drift_limit: int,
    report: dict[str, int],
) -> None:
    """Drift auto-brake and staleness retirement for every live policy.

    The same pass owns both edges: one job holds the evidence for compiling
    and for taking it back. A policy drifting over the limit suspends (a
    wrong policy needs review before it either resumes or retires); a policy
    nothing matches retires. Retired is terminal and kept for audit.
    """
    rows = (
        session.execute(
            select(CompiledPolicy).where(
                CompiledPolicy.state.in_(("shadow", "active", "suspended"))
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        drift = _drift_counts(session, row, window_start)
        if row.state in ("shadow", "active") and drift > drift_limit:
            row.state = "suspended"
            row.suspended_by = AUTO_ACTOR
            row.suspended_at = now
            report["suspended"] += 1
            logger.warning(
                "policy %s v%s auto-suspended: %s drift signals in the window "
                "(limit %s) — disagreements and analyst reopens of "
                "policy-triaged closures",
                row.policy_id,
                row.version,
                drift,
                drift_limit,
            )
            continue
        if _policy_is_stale(session, row, window_start):
            row.state = "retired"
            row.retired_by = AUTO_ACTOR
            row.retired_at = now
            report["retired"] += 1
            logger.info(
                "policy %s v%s retired: no finding matched it in the window",
                row.policy_id,
                row.version,
            )


def _drift_counts(session: Session, row: CompiledPolicy, window_start: datetime) -> int:
    """Disagreements with the eventual LLM outcome plus policy-triage reopens.

    Both signals live in the window and name the policy: disagreement rows are
    the current version's backfilled ``agrees = false`` decisions; reopens are
    cases holding a finding the policy applied to (``outcome='applied'``)
    whose closure row exists but whose status is no longer closed.
    """
    disagreements = session.execute(
        select(func.count())
        .select_from(CompiledPolicyDecision)
        .where(
            CompiledPolicyDecision.policy_id == row.policy_id,
            CompiledPolicyDecision.policy_version == row.version,
            CompiledPolicyDecision.agrees.is_(False),
            CompiledPolicyDecision.evaluated_at >= window_start,
        )
    ).scalar()

    triaged_finding_ids = select(CompiledPolicyDecision.finding_id).where(
        CompiledPolicyDecision.policy_id == row.policy_id,
        CompiledPolicyDecision.outcome == "applied",
        CompiledPolicyDecision.evaluated_at >= window_start,
    )
    reopens = session.execute(
        select(func.count(func.distinct(Case.case_id)))
        .select_from(Case)
        .join(case_findings, case_findings.c.case_id == Case.case_id)
        .join(CaseClosureInfo, CaseClosureInfo.case_id == Case.case_id)
        .where(
            case_findings.c.finding_id.in_(triaged_finding_ids),
            Case.status != CASE_CLOSED_STATUS,
            Case.updated_at >= window_start,
        )
    ).scalar()

    return int(disagreements or 0) + int(reopens or 0)


def _policy_is_stale(
    session: Session, row: CompiledPolicy, window_start: datetime
) -> bool:
    """Whether no windowed finding matches the policy, asked of the evaluator.

    The stored document is the thing the fast path would evaluate, so
    staleness is its own match semantics, not a second one. The scan is
    capped at the most recent windowed findings for the policy's data sources
    (all windowed findings when the match binds no source); the policy's
    state rides in from the row, since the stored document's state field is
    not what the row says after a lifecycle edge.
    """
    policy = PolicyIR.from_dict(dict(row.policy_ir))
    policy = replace(policy, state=row.state)

    findings_query = (
        select(Finding.finding_id, Finding.data_source, Finding.entity_context)
        .where(Finding.timestamp >= window_start)
        .order_by(Finding.timestamp.desc())
        .limit(STALENESS_SCAN_CAP)
    )
    if policy.match.data_source is not None:
        findings_query = findings_query.where(
            Finding.data_source.in_(policy.match.data_source)
        )
    findings = session.execute(findings_query).all()
    if not findings:
        return True

    prediction_ids = [finding.finding_id for finding in findings]
    techniques: dict[str, set[str]] = {}
    for finding_id, technique_id in session.execute(
        select(
            FindingMitrePrediction.finding_id,
            FindingMitrePrediction.technique_id,
        ).where(FindingMitrePrediction.finding_id.in_(prediction_ids))
    ).all():
        techniques.setdefault(finding_id, set()).add(technique_id)

    for finding in findings:
        probe = {
            "finding_id": finding.finding_id,
            "data_source": finding.data_source,
            "mitre_predictions": {
                technique: 1.0 for technique in techniques.get(finding.finding_id, ())
            },
            "entity_context": finding.entity_context or {},
        }
        if evaluate([policy], probe) is not None:
            return False
    return True

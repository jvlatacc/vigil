"""Deterministic compiler: maturity evidence in, versioned policy IR out.

The compiler is pure: the same evidence plus the same injected clock yields a
byte-identical document — no wall-clock reads, no randomness, no I/O. It mints
the archetype's stable policy id, assigns the version from the store's current
head, builds and validates the IR, and computes the content hash over the
canonical semantic serialization (lifecycle state, compile time, and render
digests excluded — a recompile of unchanged evidence reproduces the same hash).

Eligibility is the maturity job's decision (thresholds are runtime tunables);
the compiler only refuses structurally impossible evidence — no closed cases,
no data sources, no techniques — because such a document could not match any
finding honestly. Validation proper lives in :mod:`core.policy_compiler.models`
and is the same gate the evaluator and the renderers lean on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from core.policy_compiler.models import (
    PolicyValidationError,
    canonical_json,
    compute_content_hash,
    validate_ir,
)


class CompileError(Exception):
    """The maturity evidence cannot become an honest, matchable policy."""


@dataclass(frozen=True)
class ArchetypeEvidence:
    """What the maturity job proved about one workflow-and-archetype pairing.

    Identity: ``workflow_id`` refined by ``data_sources``, ATT&CK ``techniques``
    and ``entity_context_types`` — the same fields the compiled match clause
    binds to, so a policy can only ever match the archetype it was compiled
    from. ``outcomes`` counts closed cases by closure category;
    ``observed_*`` carries the modal triage the resolved cases received (what
    the compiled decision replays).
    """

    workflow_id: str
    window_days: int
    data_sources: Sequence[str]
    techniques: Sequence[str]
    entity_context_types: Sequence[str]
    outcomes: Mapping[str, int]
    consistency: float
    analyst_overrides: int
    observed_severity: str | None
    observed_recommended_action: str | None
    observed_category: str | None

    def resolved(self) -> int:
        return int(self.outcomes.get("resolved", 0))

    def total(self) -> int:
        return int(sum(self.outcomes.values()))


@dataclass(frozen=True)
class CompileResult:
    """A compiled policy: the validated document plus its pinned hash.

    ``ir`` is the exact document to store in ``compiled_policies.policy_ir`` —
    self-describing, with ``content_hash`` and (once renderers run at compile
    time) per-format render digests inside. ``content_hash`` repeats the pinned
    value for the table's own column.
    """

    policy_id: str
    version: int
    content_hash: str
    ir: dict[str, Any]

    def as_row(self) -> dict[str, Any]:
        """The columns the maturity job writes for a candidate row."""
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "state": "candidate",
            "policy_ir": self.ir,
            "content_hash": self.content_hash,
            "maturity_evidence": dict(self.ir["maturity"]),
        }


def archetype_policy_id(evidence: ArchetypeEvidence) -> str:
    """Mint the stable policy id for an archetype: ``pol_`` + 16 hex chars.

    Identity covers the archetype (workflow + sorted match sets), not the
    decision — a recompile with a changed observed severity keeps the id and
    takes a new version, so every decision still names one version of one
    archetype deterministically.
    """
    identity = {
        "workflow_id": evidence.workflow_id,
        "data_sources": sorted(evidence.data_sources),
        "techniques": sorted(evidence.techniques),
        "entity_context_types": sorted(evidence.entity_context_types),
    }
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return f"pol_{digest[:16]}"


def next_version(previous_version: Optional[int]) -> int:
    """A recompile of the same archetype bumps the version; the first is 1."""
    if previous_version is not None and previous_version < 1:
        raise CompileError(
            f"previous_version: {previous_version} is not a positive version "
            "(the store's version column starts at 1)"
        )
    return 1 if previous_version is None else previous_version + 1


def _reasoning(evidence: ArchetypeEvidence) -> str:
    """The provenance sentence a compiled decision carries — derived, honest."""
    overrides = evidence.analyst_overrides
    override_note = (
        "no analyst overrides"
        if overrides == 0
        else f"{overrides} analyst override{'s' if overrides != 1 else ''}"
    )
    return (
        f"Compiled from {evidence.total()} closed cases of "
        f"{evidence.workflow_id}: {evidence.resolved()}/{evidence.total()} "
        f"resolved consistently, {override_note} in the "
        f"{evidence.window_days}-day window."
    )


def compile_policy(
    evidence: ArchetypeEvidence,
    *,
    now: datetime,
    previous_version: Optional[int] = None,
) -> CompileResult:
    """Compile maturity evidence into a validated, hashed candidate document.

    ``now`` is the caller's clock, injected: determinism is same evidence and
    same clock in, byte-identical document out. The content hash itself is
    clock-stable — ``compiled_at`` is excluded — so a recompile of unchanged
    evidence reproduces the hash even across days.
    """
    if evidence.total() == 0:
        raise CompileError(
            "outcomes: no closed cases in the evidence window — there is "
            "nothing this policy could claim was learned"
        )
    if not evidence.data_sources:
        raise CompileError(
            "data_sources: empty — an archetype without a source refines to "
            "the whole workflow and would match far more than it learned from"
        )
    if not evidence.techniques:
        raise CompileError(
            "techniques: empty — technique predictions are the archetype's "
            "identity; compile nothing without them"
        )
    if not (
        evidence.observed_severity
        and evidence.observed_category
        and evidence.observed_recommended_action
    ):
        raise CompileError(
            "observed triage: incomplete — the resolved runs record no complete "
            "severity/category/action to replay, and a decision with holes in "
            "it is not one the fast path may write"
        )

    policy_id = archetype_policy_id(evidence)
    document = {
        "ir_version": 1,
        "policy_id": policy_id,
        "version": next_version(previous_version),
        "state": "candidate",
        "compiled_at": _iso_utc(now),
        "match": {
            "workflow_id": evidence.workflow_id,
            "data_source": {"any_of": sorted(evidence.data_sources)},
            "techniques": {"any_of": sorted(evidence.techniques)},
            # An archetype the evidence never pinned to entity-context shapes
            # stays unconstrained there — omit the clause, don't emit an empty
            # (and unmatchable) group.
            **(
                {
                    "entity_context_types": {
                        "all_of": sorted(evidence.entity_context_types)
                    }
                }
                if evidence.entity_context_types
                else {}
            ),
        },
        "decision": {
            "severity": evidence.observed_severity,
            "confidence": evidence.consistency,
            "recommended_action": evidence.observed_recommended_action,
            "category": evidence.observed_category,
            "reasoning": _reasoning(evidence),
            "actions_human_only": True,
        },
        "maturity": {
            "workflow_id": evidence.workflow_id,
            "window_days": evidence.window_days,
            "outcomes": dict(evidence.outcomes),
            "consistency": evidence.consistency,
            "analyst_overrides": evidence.analyst_overrides,
        },
    }
    try:
        ir = validate_ir(document)
    except PolicyValidationError as exc:
        raise CompileError(f"compiled document failed validation: {exc}") from exc
    ir["content_hash"] = compute_content_hash(ir)
    return CompileResult(
        policy_id=policy_id,
        version=ir["version"],
        content_hash=ir["content_hash"],
        ir=ir,
    )


def _iso_utc(now: datetime) -> str:
    """Canonical UTC Z-form instant, second precision (the IR's timestamp form)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (
        now.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

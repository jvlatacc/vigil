"""The versioned policy IR — the canonical artifact of the JIT policy compiler.

One compiled policy is a JSON condition tree over **pre-LLM finding fields
only**: workflow identity, ``data_source``, ATT&CK technique predictions, and
entity-context key *types*. Python evaluates it in-process (``evaluator.py``)
in microseconds; Rego, Snort, Suricata, and iptables are rendered projections
(``renderers/``), pinned to the IR by golden-file tests and content hashes.

Security stance (``docs/adr/0001-jit-policy-fast-path.md``): a compiled policy
is data with a hash, not code with a prompt. Validation is the enforcement
point for two of its rules —

- **Predicates bind only to evidence-anchored fields.** Free-text finding
  fields (``title``, ``description``, anything the match schema does not name)
  are rejected here, so an adversary who can shape alert text cannot steer a
  compiled policy — the deterministic counterpart of the prompt-injection
  scan the LLM path applies.
- **No new autonomy.** ``decision.actions_human_only`` must be true; a policy
  that claims otherwise fails the compile gate. Elevation is a separate,
  explicitly governed decision (ADR 0001, locked decision 4).

The document's own version lives in ``ir_version`` (the format of the condition
tree); ``version`` is the policy's lifecycle version — a recompile of the same
archetype issues a new one. ``content_hash`` is computed over the canonical
serialization of everything except the envelope fields that lifecycle changes
without changing semantics (``HASH_EXCLUDED_KEYS``): two compiles of the same
evidence at different times share a hash, so a hash match means "no semantic
change" and the maturity job can skip re-versioning.

Two vocabularies are restated here rather than imported because the modules
that own them sit in tiers this domain may not depend on the other way:
``SEVERITIES``/``RECOMMENDED_ACTIONS`` mirror ``services/daemon/probes.py``
(core must not import services), and ``POLICY_REASONING_CAP`` follows the
2,000-character prose cap ``core/memory/recall_contract.py`` applies to
Verdict statements. Lifecycle states come from the storage models, which this
domain legitimately depends on.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from core.storage.models.policy_compiler import POLICY_STATES

__all__ = [
    "ENTITY_CONTEXT_TYPE_BY_KEY",
    "HASH_EXCLUDED_KEYS",
    "IR_VERSION",
    "POLICY_REASONING_CAP",
    "RECOMMENDED_ACTIONS",
    "RENDER_TARGETS",
    "SEVERITIES",
    "EntityTypeSet",
    "MatchClause",
    "MaturityEvidence",
    "PolicyDecision",
    "PolicyIR",
    "PolicyMode",
    "PolicyValidationError",
    "TechniqueSet",
    "canonical_json",
    "compute_content_hash",
    "mode_for_state",
    "validate_ir",
]

# --- Format and vocabulary constants ---------------------------------------

# Bumped when the condition tree itself changes shape. A stored IR whose
# ``ir_version`` is not this value is not interpretable by this code and is
# refused at validation rather than misread.
IR_VERSION = 1

# The renderers ``core/policy_compiler/renderers/`` ships. A target outside
# this tuple is a compile-validation error — the renderer set cannot represent
# it — never a silent render-time fallback.
RENDER_TARGETS = ("rego", "snort", "suricata", "iptables")

# Envelope fields excluded from the content hash: they change over the policy
# lifecycle (state, compiled_at), are derived from the content (renders), are
# the hash itself, or are row identity rather than content (version — a
# recompile of unchanged evidence at a bumped version reproduces the hash).
# Everything else — ir_version, policy_id, match, decision, maturity — is
# semantic; equal hash means equal behavior.
HASH_EXCLUDED_KEYS = frozenset(
    {"content_hash", "renders", "state", "compiled_at", "version"}
)

# Finding-severity vocabulary the triage prompt asks the model for and the
# response pipeline keys on (services/daemon/probes.py SEVERITIES).
SEVERITIES = ("critical", "high", "medium", "low")

# Recommended-action vocabulary the responder consumes
# (services/daemon/probes.py ACTIONS). ``deceive`` is the daemon's MTD verb:
# divert the source into a decoy instead of containing it — additive to the
# containment vocabulary, never a replacement.
RECOMMENDED_ACTIONS = (
    "isolate",
    "block",
    "investigate",
    "monitor",
    "dismiss",
    "deceive",
)

# Longest ``reasoning`` a policy stores. The cap follows the episodic-prose
# convention (core/memory/recall_contract.py EPISODIC_PROSE_CAP): the text is
# replayed into audit and console views and must stay bounded where written.
POLICY_REASONING_CAP = 2000

# How a finding's ``entity_context`` dict keys (the daemon writes plural keys:
# ``src_ips``, ``hostnames``, …) name themselves in the IR: as singular entity
# types. The four keys the daemon pollers write are mapped explicitly; host,
# user, domain, url, email, and hash line up with the Entity Key vocabulary
# (core/memory/recall_contract.py ENTITY_KEY_TYPES) while src_ip/dest_ip keep
# the direction the finding carries. An unmapped key passes through verbatim —
# a future poller key is matchable the day it appears, without editing this
# table first.
ENTITY_CONTEXT_TYPE_BY_KEY: dict[str, str] = {
    "src_ips": "src_ip",
    "dest_ips": "dest_ip",
    "hostnames": "host",
    "usernames": "user_account",
    "domains": "domain",
    "urls": "url",
    "emails": "email",
    "hashes": "hash",
    "processes": "process",
    "files": "file",
    # Legacy singular keys the daemon's enrich step still reads
    # (services/daemon/processor.py falls back to src_ip/dst_ip/dest_ip when
    # the plural form is absent); normalized to the same types.
    "src_ip": "src_ip",
    "dest_ip": "dest_ip",
    "dst_ip": "dest_ip",
    "hostname": "host",
    "username": "user_account",
}


class PolicyValidationError(ValueError):
    """A policy IR (or one of its parts) failed the compile/load validation gate.

    The message names the offending path in the document (``match.title``) so
    a rejected compile says what was wrong, not just that something was.
    """


class PolicyMode(str, Enum):
    """How a policy's evaluation may act: the two evaluating row states.

    ``shadow`` and ``suspended`` rows evaluate as SHADOW (log, never act);
    only ``active`` rows are ACTIVE (write triage keys). ``candidate`` and
    ``retired`` rows are never evaluated at all — ``mode_for_state`` refuses
    them, so the modes and the storage states (``POLICY_STATES``) cannot
    silently drift apart.
    """

    SHADOW = "shadow"
    ACTIVE = "active"


def mode_for_state(state: str) -> PolicyMode:
    """The evaluation mode a stored policy row's state evaluates as.

    Raises ``ValueError`` for ``candidate``/``retired`` — the caller should
    have filtered them before loading; an invisible state reaching the
    evaluator is a bug, not a policy to skip quietly.
    """
    if state == "active":
        return PolicyMode.ACTIVE
    if state in ("shadow", "suspended"):
        return PolicyMode.SHADOW
    raise ValueError(
        f"state {state!r} is never evaluated (expected one of "
        f"'shadow', 'suspended', 'active')"
    )


# --- Canonical serialization and content hash -------------------------------


def canonical_json(obj: Any) -> str:
    """Deterministic JSON text for hashing: sorted keys, tight separators.

    Set-valued lists must already be sorted (``validate_ir`` canonicalizes
    them) — ``sort_keys`` orders object keys, not array elements.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_content_hash(ir: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` over the canonical serialization of the semantic IR.

    Envelope fields (``HASH_EXCLUDED_KEYS``) are dropped first: the hash is
    the identity of what the policy *does*, not of when it was compiled or
    what state it sits in.
    """
    semantic = {k: v for k, v in ir.items() if k not in HASH_EXCLUDED_KEYS}
    digest = hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# --- Structural patterns -----------------------------------------------------
#
# One regex per token-shaped field. Together they are the free-text gate: a
# predicate element carrying whitespace, control characters, or prose cannot
# match any of them, and unknown predicate *keys* are rejected by name in
# ``_validate_match``.

_WORKFLOW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_DATA_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
# ATT&CK technique or sub-technique identifier (T1110, T1110.003). Tactic
# names are refused: a policy is compiled over the technique set the evidence
# names, and "Credential Access" in a predicate is a grouping mistake, not a
# technique.
_TECHNIQUE_RE = re.compile(r"^T[0-9]{4}(\.[0-9]{3})?$")
_ENTITY_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
_CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")
# Compiler-minted identity (compiler.py: 'pol_' + sha256 of the archetype key,
# hex, 16 chars). Validation pins the mint so a policy_id can only come from
# this compiler.
_POLICY_ID_RE = re.compile(r"^pol_[0-9a-f]{16}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Keys the match clause may name. Anything else — in particular the free-text
# finding fields an adversary could shape — is rejected with the allowed set
# named in the error.
_MATCH_KEYS = frozenset(
    {"workflow_id", "data_source", "techniques", "entity_context_types"}
)


def _require_printable(value: str, path: str) -> str:
    """Reject control characters and surrounding whitespace in any IR string.

    The regex-gated fields mostly imply this; it guards the one free-prose
    field (``decision.reasoning``) and any future string field from carrying
    an invisible payload out of the validator.
    """
    if value != value.strip():
        raise PolicyValidationError(f"{path}: leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PolicyValidationError(f"{path}: control characters are not allowed")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    """A JSON list of non-empty strings, or a clear error naming the path."""
    if not isinstance(value, list) or not value:
        raise PolicyValidationError(f"{path}: expected a non-empty list of strings")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise PolicyValidationError(f"{path}[{i}]: expected a non-empty string")
        out.append(_require_printable(item, f"{path}[{i}]"))
    return out


def _canonical_set(value: Any, path: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    """Validate a set-valued predicate: deduped, sorted, pattern-checked."""
    items = _string_list(value, path)
    for i, item in enumerate(items):
        if not pattern.match(item):
            raise PolicyValidationError(
                f"{path}[{i}]: {item!r} does not match the required form {pattern.pattern!r}"
            )
    return tuple(sorted(set(items)))


def _int_in_range(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyValidationError(f"{path}: expected an integer")
    if not minimum <= value <= maximum:
        raise PolicyValidationError(
            f"{path}: {value} outside the permitted range [{minimum}, {maximum}]"
        )
    return value


def _finite_float(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyValidationError(f"{path}: expected a number")
    out = float(value)
    if not math.isfinite(out):
        raise PolicyValidationError(f"{path}: must be a finite number")
    return out


def _iso_utc(value: Any, path: str) -> str:
    """An ISO-8601 timestamp, canonicalized to a UTC ``…Z`` string."""
    if not isinstance(value, str) or not value:
        raise PolicyValidationError(f"{path}: expected an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PolicyValidationError(
            f"{path}: {value!r} is not an ISO-8601 timestamp"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    rendered = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return _require_printable(rendered, path)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyValidationError(f"{path}: expected an object")
    return value


# --- Predicate groups --------------------------------------------------------


@dataclass(frozen=True)
class TechniqueSet:
    """The ATT&CK technique constraint: ``any_of`` / ``all_of`` over ids.

    ``any_of`` holds when at least one listed technique is predicted on the
    finding; ``all_of`` when every listed one is. Both present means both must
    hold (AND across the two, OR within each). An absent group constrains
    nothing.
    """

    any_of: tuple[str, ...] = ()
    all_of: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.any_of:
            out["any_of"] = list(self.any_of)
        if self.all_of:
            out["all_of"] = list(self.all_of)
        return out

    @classmethod
    def from_dict(cls, value: Any, path: str) -> "TechniqueSet":
        obj = _object(value, path)
        unknown = set(obj) - {"any_of", "all_of"}
        if unknown:
            raise PolicyValidationError(
                f"{path}: unknown key(s) {sorted(unknown)}; allowed: any_of, all_of"
            )
        any_of = (
            _canonical_set(obj["any_of"], f"{path}.any_of", _TECHNIQUE_RE)
            if "any_of" in obj
            else ()
        )
        all_of = (
            _canonical_set(obj["all_of"], f"{path}.all_of", _TECHNIQUE_RE)
            if "all_of" in obj
            else ()
        )
        if not any_of and not all_of:
            raise PolicyValidationError(
                f"{path}: at least one of any_of/all_of must be a non-empty list"
            )
        return cls(any_of=any_of, all_of=all_of)


@dataclass(frozen=True)
class EntityTypeSet:
    """Entity-context key *type* constraint, same any_of/all_of semantics.

    Types name what a finding's ``entity_context`` contains (``src_ip``,
    ``user_account``) — never which entity. Bounding the predicate to types is
    deliberate: an attacker controls which entities appear in their own
    alerts, so values must never steer a compiled policy.
    """

    any_of: tuple[str, ...] = ()
    all_of: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.any_of:
            out["any_of"] = list(self.any_of)
        if self.all_of:
            out["all_of"] = list(self.all_of)
        return out

    @classmethod
    def from_dict(cls, value: Any, path: str) -> "EntityTypeSet":
        obj = _object(value, path)
        unknown = set(obj) - {"any_of", "all_of"}
        if unknown:
            raise PolicyValidationError(
                f"{path}: unknown key(s) {sorted(unknown)}; allowed: any_of, all_of"
            )
        any_of = (
            _canonical_set(obj["any_of"], f"{path}.any_of", _ENTITY_TYPE_RE)
            if "any_of" in obj
            else ()
        )
        all_of = (
            _canonical_set(obj["all_of"], f"{path}.all_of", _ENTITY_TYPE_RE)
            if "all_of" in obj
            else ()
        )
        if not any_of and not all_of:
            raise PolicyValidationError(
                f"{path}: at least one of any_of/all_of must be a non-empty list"
            )
        return cls(any_of=any_of, all_of=all_of)


@dataclass(frozen=True)
class MatchClause:
    """The condition tree's one level: which findings the policy matches.

    Exactly the four evidence-anchored predicate families the ADR allows.
    ``workflow_id`` is required — a policy is compiled from one workflow's
    maturity evidence and names it. ``data_source`` accepts either the bare
    list form the spec's sample shows or the ``{"any_of": [...]}`` object
    form; both canonicalize to the same document, so both hash identically.
    """

    workflow_id: str
    data_source: Optional[tuple[str, ...]] = None
    techniques: Optional[TechniqueSet] = None
    entity_context_types: Optional[EntityTypeSet] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"workflow_id": self.workflow_id}
        if self.data_source is not None:
            out["data_source"] = {"any_of": list(self.data_source)}
        if self.techniques is not None:
            out["techniques"] = self.techniques.to_dict()
        if self.entity_context_types is not None:
            out["entity_context_types"] = self.entity_context_types.to_dict()
        return out

    @classmethod
    def from_dict(cls, value: Any) -> "MatchClause":
        obj = _object(value, "match")
        unknown = set(obj) - _MATCH_KEYS
        if unknown:
            raise PolicyValidationError(
                f"match: predicate key(s) {sorted(unknown)} are not evidence-anchored "
                f"fields; allowed: {sorted(_MATCH_KEYS)}. Free-text finding fields "
                "(title, description, …) are rejected — the alert-farming defense."
            )
        if "workflow_id" not in obj:
            raise PolicyValidationError("match.workflow_id: required")
        workflow_id = obj["workflow_id"]
        if not isinstance(workflow_id, str) or not _WORKFLOW_ID_RE.match(workflow_id):
            raise PolicyValidationError(
                f"match.workflow_id: {workflow_id!r} does not match the required "
                f"form {_WORKFLOW_ID_RE.pattern!r}"
            )
        _require_printable(workflow_id, "match.workflow_id")

        data_source: Optional[tuple[str, ...]] = None
        if "data_source" in obj:
            raw = obj["data_source"]
            # The spec's sample shows a bare list; accept it and the object form.
            items = (
                _string_list(raw, "match.data_source")
                if isinstance(raw, list)
                else _string_list(
                    _object(raw, "match.data_source").get("any_of"),
                    "match.data_source.any_of",
                )
            )
            for i, item in enumerate(items):
                if not _DATA_SOURCE_RE.match(item):
                    raise PolicyValidationError(
                        f"match.data_source[{i}]: {item!r} does not match the "
                        f"required form {_DATA_SOURCE_RE.pattern!r}"
                    )
            data_source = tuple(sorted(set(items)))

        techniques = (
            TechniqueSet.from_dict(obj["techniques"], "match.techniques")
            if "techniques" in obj
            else None
        )
        entity_context_types = (
            EntityTypeSet.from_dict(
                obj["entity_context_types"], "match.entity_context_types"
            )
            if "entity_context_types" in obj
            else None
        )
        return cls(
            workflow_id=workflow_id,
            data_source=data_source,
            techniques=techniques,
            entity_context_types=entity_context_types,
        )


# --- Decision and maturity evidence ------------------------------------------


@dataclass(frozen=True)
class PolicyDecision:
    """The triage a matching policy writes — the LLM triage key set, compiled.

    ``actions_human_only`` is validated to be true: v1 grants the fast path no
    unattended power (ADR 0001, locked decision 4). A policy document that
    claims otherwise fails validation instead of being silently corrected.
    """

    severity: str
    confidence: float
    recommended_action: str
    category: str
    reasoning: str
    actions_human_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "category": self.category,
            "reasoning": self.reasoning,
            "actions_human_only": self.actions_human_only,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PolicyDecision":
        obj = _object(value, "decision")
        unknown = set(obj) - {
            "severity",
            "confidence",
            "recommended_action",
            "category",
            "reasoning",
            "actions_human_only",
        }
        if unknown:
            raise PolicyValidationError(f"decision: unknown key(s) {sorted(unknown)}")
        for required in ("severity", "confidence", "recommended_action", "category"):
            if required not in obj:
                raise PolicyValidationError(f"decision.{required}: required")

        severity = obj["severity"]
        if severity not in SEVERITIES:
            raise PolicyValidationError(
                f"decision.severity: {severity!r} not in {list(SEVERITIES)}"
            )
        action = obj["recommended_action"]
        if action not in RECOMMENDED_ACTIONS:
            raise PolicyValidationError(
                f"decision.recommended_action: {action!r} not in {list(RECOMMENDED_ACTIONS)}"
            )
        confidence = _finite_float(obj["confidence"], "decision.confidence")
        if not 0.0 <= confidence <= 1.0:
            raise PolicyValidationError(
                f"decision.confidence: {confidence} outside [0, 1]"
            )
        category = obj["category"]
        if not isinstance(category, str) or not _CATEGORY_RE.match(category):
            raise PolicyValidationError(
                f"decision.category: {category!r} does not match the required "
                f"form {_CATEGORY_RE.pattern!r}"
            )
        _require_printable(category, "decision.category")

        reasoning = obj.get("reasoning", "")
        if not isinstance(reasoning, str):
            raise PolicyValidationError("decision.reasoning: expected a string")
        _require_printable(reasoning, "decision.reasoning")
        if len(reasoning) > POLICY_REASONING_CAP:
            raise PolicyValidationError(
                f"decision.reasoning: {len(reasoning)} characters exceeds the "
                f"{POLICY_REASONING_CAP}-character cap"
            )

        human_only = obj.get("actions_human_only", True)
        if human_only is not True:
            raise PolicyValidationError(
                "decision.actions_human_only: must be true — v1 grants the fast "
                "path no unattended power; policy-triaged actions stay "
                "human-only (ADR 0001). Elevation is a separate, explicitly "
                "governed decision."
            )
        return cls(
            severity=severity,
            confidence=confidence,
            recommended_action=action,
            category=category,
            reasoning=reasoning,
            actions_human_only=True,
        )


@dataclass(frozen=True)
class MaturityEvidence:
    """The evidence the compile trusted — carried in the IR for audit.

    Recorded, not interpreted: eligibility (minimum runs, consistency ratio,
    window, no analyst overrides) is the maturity job's gate, checked before
    the compiler is called. Validation here keeps the record honest and the
    archetype identity consistent with the match clause.
    """

    workflow_id: str
    window_days: int
    outcomes: Mapping[str, int]
    consistency: float
    analyst_overrides: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "window_days": self.window_days,
            "outcomes": dict(sorted(self.outcomes.items())),
            "consistency": self.consistency,
            "analyst_overrides": self.analyst_overrides,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "MaturityEvidence":
        obj = _object(value, "maturity")
        unknown = set(obj) - {
            "workflow_id",
            "window_days",
            "outcomes",
            "consistency",
            "analyst_overrides",
        }
        if unknown:
            raise PolicyValidationError(f"maturity: unknown key(s) {sorted(unknown)}")
        for required in (
            "workflow_id",
            "window_days",
            "outcomes",
            "consistency",
            "analyst_overrides",
        ):
            if required not in obj:
                raise PolicyValidationError(f"maturity.{required}: required")

        workflow_id = obj["workflow_id"]
        if not isinstance(workflow_id, str) or not _WORKFLOW_ID_RE.match(workflow_id):
            raise PolicyValidationError(
                f"maturity.workflow_id: {workflow_id!r} does not match the "
                f"required form {_WORKFLOW_ID_RE.pattern!r}"
            )

        outcomes_raw = _object(obj["outcomes"], "maturity.outcomes")
        outcomes: dict[str, int] = {}
        for key, count in outcomes_raw.items():
            if not _CATEGORY_RE.match(str(key)):
                raise PolicyValidationError(
                    f"maturity.outcomes: key {key!r} is not a closure-category token"
                )
            outcomes[key] = _int_in_range(count, f"maturity.outcomes.{key}", 0, 10**9)

        consistency = _finite_float(obj["consistency"], "maturity.consistency")
        if not 0.0 <= consistency <= 1.0:
            raise PolicyValidationError(
                f"maturity.consistency: {consistency} outside [0, 1]"
            )
        return cls(
            workflow_id=workflow_id,
            window_days=_int_in_range(
                obj["window_days"], "maturity.window_days", 1, 3650
            ),
            outcomes=outcomes,
            consistency=consistency,
            analyst_overrides=_int_in_range(
                obj["analyst_overrides"], "maturity.analyst_overrides", 0, 10**9
            ),
        )


# --- The document ------------------------------------------------------------


@dataclass(frozen=True)
class PolicyIR:
    """A compiled policy: the validated condition tree plus its provenance.

    Instances are constructed through :meth:`from_dict` (which validates) —
    the dataclass is the typed view of the canonical document, and the
    document is what is stored, hashed, and rendered.
    """

    ir_version: int
    policy_id: str
    version: int
    state: str
    compiled_at: str
    match: MatchClause
    decision: PolicyDecision
    maturity: MaturityEvidence
    content_hash: Optional[str] = None
    renders: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ir_version": self.ir_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "state": self.state,
            "compiled_at": self.compiled_at,
            "match": self.match.to_dict(),
            "decision": self.decision.to_dict(),
            "maturity": self.maturity.to_dict(),
        }
        if self.content_hash is not None:
            out["content_hash"] = self.content_hash
        if self.renders:
            out["renders"] = dict(sorted(self.renders.items()))
        return out

    @classmethod
    def from_dict(cls, value: Any) -> "PolicyIR":
        canonical = validate_ir(value)
        match = MatchClause.from_dict(canonical["match"])
        decision = PolicyDecision.from_dict(canonical["decision"])
        maturity = MaturityEvidence.from_dict(canonical["maturity"])
        return cls(
            ir_version=canonical["ir_version"],
            policy_id=canonical["policy_id"],
            version=canonical["version"],
            state=canonical["state"],
            compiled_at=canonical["compiled_at"],
            match=match,
            decision=decision,
            maturity=maturity,
            content_hash=canonical.get("content_hash"),
            renders=canonical.get("renders", {}),
        )


def validate_ir(value: Any) -> dict[str, Any]:
    """Validate an IR document and return it in canonical form.

    The single validation path for both directions: the compiler runs it on
    the document it just built, and every load from storage (evaluator cache,
    console inspect, renderer) runs it again — so a document that was tampered
    with, or written by anything but this compiler, is refused where it is
    read, not merely where it was made. Canonicalization (sorted sets, ``Z``-
    suffixed timestamp, object-form ``data_source``) happens here, which is
    what makes ``compute_content_hash`` stable across equivalent inputs.

    When ``content_hash`` is present it is verified against the recomputed
    hash — the tamper check.
    """
    obj = _object(value, "ir")

    unknown_top = set(obj) - {
        "ir_version",
        "policy_id",
        "version",
        "state",
        "compiled_at",
        "content_hash",
        "match",
        "decision",
        "maturity",
        "renders",
    }
    if unknown_top:
        raise PolicyValidationError(f"ir: unknown key(s) {sorted(unknown_top)}")

    for required in (
        "ir_version",
        "policy_id",
        "version",
        "state",
        "compiled_at",
        "match",
        "decision",
        "maturity",
    ):
        if required not in obj:
            raise PolicyValidationError(f"ir.{required}: required")

    _int_in_range(obj["ir_version"], "ir.ir_version", IR_VERSION, IR_VERSION)

    policy_id = obj["policy_id"]
    if not isinstance(policy_id, str) or not _POLICY_ID_RE.match(policy_id):
        raise PolicyValidationError(
            f"ir.policy_id: {policy_id!r} is not a compiler-minted policy id "
            f"(expected form {_POLICY_ID_RE.pattern!r})"
        )

    version = _int_in_range(obj["version"], "ir.version", 1, 10**9)

    state = obj["state"]
    if state not in POLICY_STATES:
        raise PolicyValidationError(f"ir.state: {state!r} not in {list(POLICY_STATES)}")

    compiled_at = _iso_utc(obj["compiled_at"], "ir.compiled_at")

    content_hash: Optional[str] = None
    if "content_hash" in obj and obj["content_hash"] is not None:
        raw_hash = obj["content_hash"]
        if not isinstance(raw_hash, str) or not _HASH_RE.match(raw_hash):
            raise PolicyValidationError(
                f"ir.content_hash: {raw_hash!r} is not a 'sha256:<hex>' digest"
            )
        content_hash = raw_hash

    renders: dict[str, str] = {}
    if "renders" in obj and obj["renders"] is not None:
        renders_obj = _object(obj["renders"], "ir.renders")
        for target, digest in renders_obj.items():
            if target not in RENDER_TARGETS:
                raise PolicyValidationError(
                    f"ir.renders: render target {target!r} is not one the renderer "
                    f"set can represent (allowed: {list(RENDER_TARGETS)})"
                )
            if not isinstance(digest, str) or not _HASH_RE.match(digest):
                raise PolicyValidationError(
                    f"ir.renders.{target}: {digest!r} is not a 'sha256:<hex>' digest"
                )
            renders[target] = digest

    match = MatchClause.from_dict(obj["match"])
    decision = PolicyDecision.from_dict(obj["decision"])
    maturity = MaturityEvidence.from_dict(obj["maturity"])

    # The compiled policy is evidence about one workflow; match and maturity
    # must name the same one, or the document is internally incoherent.
    if match.workflow_id != maturity.workflow_id:
        raise PolicyValidationError(
            f"ir: match.workflow_id {match.workflow_id!r} and maturity.workflow_id "
            f"{maturity.workflow_id!r} name different workflows"
        )

    canonical: dict[str, Any] = {
        "ir_version": IR_VERSION,
        "policy_id": policy_id,
        "version": version,
        "state": state,
        "compiled_at": compiled_at,
        "match": match.to_dict(),
        "decision": decision.to_dict(),
        "maturity": maturity.to_dict(),
    }
    if content_hash is not None:
        canonical["content_hash"] = content_hash
    if renders:
        canonical["renders"] = renders

    if content_hash is not None:
        recomputed = compute_content_hash(canonical)
        if recomputed != content_hash:
            raise PolicyValidationError(
                f"ir.content_hash: {content_hash} does not match the recomputed "
                f"hash {recomputed} — the document was modified after hashing"
            )

    return canonical


def build_render_hashes(
    rendered: Sequence[tuple[str, str]],
) -> dict[str, str]:
    """``sha256:`` digests for rendered exports, keyed by target.

    Content hashes of the rendered artifacts themselves — the pins that let a
    download be checked against what the compile generated, and what the
    golden-file tests pin the renderers with.
    """
    out: dict[str, str] = {}
    for target, content in rendered:
        if target not in RENDER_TARGETS:
            raise PolicyValidationError(
                f"render target {target!r} is not one the renderer set can "
                f"represent (allowed: {list(RENDER_TARGETS)})"
            )
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        out[target] = f"sha256:{digest}"
    return out

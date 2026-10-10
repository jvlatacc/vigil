"""The policy bundle: what the operator signed, as the daemon reads it.

Wire form is the DSSE payload (``application/vnd.deeptempo.vigil.edge-bundle
.v1+json``). Parsing is strict: unknown fields, wrong types, or out-of-range
values refuse the bundle — a signer's typo must not silently widen or narrow
what a node may do. Signing the bundle IS the human promotion of edge
autonomy, so the model it signs is exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from typing import TYPE_CHECKING, Any

from services.edge.gate.tiers import V1_CEILING, AutonomyTier, parse_tier

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Set as AbstractSet

    from services.edge.observations.base import Observation

BUNDLE_PAYLOAD_TYPE = "application/vnd.deeptempo.vigil.edge-bundle.v1+json"
SCHEMA_VERSION = 1

SEVERITIES = ("low", "medium", "high", "critical")
RULE_DIRECTIONS = ("ingress", "egress", "any")
DEST_KINDS = ("ip", "domain")
IOC_KINDS = ("cidr", "ip", "domain")
ACTION_TYPES = ("block_ip", "block_domain")
EXECUTORS = ("nftables", "k8s_networkpolicy")

_BUNDLE_FIELDS = frozenset(
    {
        "bundle_id",
        "edge_schema_version",
        "segment_scope",
        "version",
        "parent_version",
        "not_before",
        "expires_at",
        "min_edge_version",
        "autonomy_tier",
        "decision",
        "allowed_actions",
        "rules",
        "ioc_sets",
        "revocations",
        "rollback_reference",
    }
)
_DECISION_FIELDS = frozenset(
    {
        "auto_act_confidence",
        "escalate_confidence",
        "max_actions_per_hour",
        "max_active_blocks",
        "default_block_ttl_seconds",
    }
)
_SCOPE_FIELDS = frozenset({"vpc", "cidrs", "node_selector"})
_IOC_FIELDS = frozenset({"kind", "entries", "source"})
_ACTION_PARAM_FIELDS = frozenset({"max_ttl_seconds", "namespaces"})


class BundleError(ValueError):
    """The payload is not a bundle this daemon can act on."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class IocSet:
    name: str
    kind: str  # cidr | ip | domain
    entries: tuple[str, ...]
    source: str | None = None

    def contains_ip(self, ip: str | None) -> bool:
        if self.kind not in ("cidr", "ip") or not ip:
            return False
        try:
            addr = ip_address(ip)
        except ValueError:
            return False
        for entry in self.entries:
            try:
                if self.kind == "cidr":
                    if addr in ip_network(entry, strict=False):
                        return True
                elif addr == ip_address(entry):
                    return True
            except ValueError:
                continue
        return False

    def contains_domain(self, domain: str | None) -> bool:
        if self.kind != "domain" or not domain:
            return False
        lowered = domain.lower().rstrip(".")
        for entry in self.entries:
            candidate = entry.lower().rstrip(".")
            if lowered == candidate or lowered.endswith("." + candidate):
                return True
        return False


@dataclass(frozen=True)
class Rule:
    rule_id: str
    direction: str  # ingress | egress | any
    dest_kind: str  # ip | domain
    ioc_set: str | None
    severity_floor: str


@dataclass(frozen=True)
class AllowedAction:
    action_type: str
    executor: str
    max_ttl_seconds: int | None
    namespaces: tuple[str, ...]  # k8s_networkpolicy scope, else ()


@dataclass(frozen=True)
class DecisionPolicy:
    auto_act_confidence: float
    escalate_confidence: float
    max_actions_per_hour: int
    max_active_blocks: int
    default_block_ttl_seconds: int


@dataclass(frozen=True)
class SegmentScope:
    vpc: str | None
    cidrs: tuple[str, ...]
    node_selector: dict[str, str]

    def matches_labels(self, node_labels: Mapping[str, str]) -> bool:
        """A node serves a segment only if it carries every selector label."""
        return all(node_labels.get(k) == v for k, v in self.node_selector.items())


@dataclass(frozen=True)
class Revocation:
    bundle_id: str
    version: int | None  # None = every version of bundle_id


@dataclass(frozen=True)
class Bundle:
    bundle_id: str
    version: int
    parent_version: int | None
    not_before: datetime
    expires_at: datetime
    min_edge_version: str | None  # contract-optional: None = no daemon floor
    autonomy_tier: AutonomyTier
    decision: DecisionPolicy
    allowed_actions: tuple[AllowedAction, ...]
    rules: tuple[Rule, ...]
    ioc_sets: dict[str, IocSet]
    revocations: tuple[Revocation, ...]
    segment_scope: SegmentScope
    rollback_reference: dict[str, Any] | None
    raw: dict[str, Any]  # the payload as signed — decisions cite its digest

    def in_validity(self, now: datetime) -> bool:
        return self.not_before <= now < self.expires_at

    def effective_tier(self, now: datetime) -> AutonomyTier:
        """The tier the node may act at at `now`: expired means Tier 0 — an
        expired bundle is never silently extended (design spec, DEGRADED)."""
        if now >= self.expires_at:
            return AutonomyTier.TIER_0
        return self.autonomy_tier

    def revokes(self, other: Bundle) -> bool:
        """Central revocation beats local allowance (W precedence rule)."""
        return any(
            revocation.bundle_id == other.bundle_id
            and (revocation.version is None or revocation.version == other.version)
            for revocation in self.revocations
        )

    def match(self, observation: Observation) -> Rule | None:
        """First rule that hits, or None."""
        for rule in self.rules:
            if self._rule_hits(rule, observation):
                return rule
        return None

    def _rule_hits(self, rule: Rule, observation: Observation) -> bool:
        if rule.direction != "any" and rule.direction != observation.direction:
            return False
        ioc_set = self.ioc_sets.get(rule.ioc_set or "")
        if ioc_set is None:
            return False
        if rule.dest_kind == "ip":
            return ioc_set.contains_ip(observation.dest_ip)
        if rule.dest_kind == "domain":
            return ioc_set.contains_domain(observation.dest_domain)
        return False


def parse_bundle(payload: Mapping[str, Any]) -> Bundle:
    """Strict parse. Raises BundleError with a stable code on every refusal;
    verify.py layers signature, validity, scope, version, and revocation
    checks on top of this."""
    if not isinstance(payload, dict):
        raise BundleError("B-SCHEMA", "payload must be a JSON object")
    _unknown_fields(payload, _BUNDLE_FIELDS, "bundle")

    bundle_id = payload.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise BundleError("B-SCHEMA", "bundle_id must be a non-empty string")

    schema_version = payload.get("edge_schema_version")
    if schema_version != SCHEMA_VERSION:
        raise BundleError(
            "B-SCHEMA-VERSION",
            f"edge_schema_version {schema_version!r} unsupported (daemon speaks {SCHEMA_VERSION})",
        )

    version = _positive_int(payload.get("version"), "version")
    parent_version = payload.get("parent_version")
    if parent_version is not None:
        parent_version = _positive_int(parent_version, "parent_version")

    not_before = _timestamp(payload.get("not_before"), "not_before")
    expires_at = _timestamp(payload.get("expires_at"), "expires_at")
    if expires_at <= not_before:
        raise BundleError("B-BOUNDS", "expires_at must be after not_before")

    min_edge_version = payload.get("min_edge_version")
    if min_edge_version is not None and (
        not isinstance(min_edge_version, str) or _semver(min_edge_version) is None
    ):
        raise BundleError(
            "B-SCHEMA", f"min_edge_version not semver: {min_edge_version!r}"
        )

    raw_tier = payload.get("autonomy_tier")
    if not isinstance(raw_tier, str):
        raise BundleError("B-TIER", f"autonomy_tier must be a string, got {raw_tier!r}")
    try:
        tier = parse_tier(raw_tier)
    except ValueError as exc:
        raise BundleError("B-TIER", str(exc)) from exc
    if tier > V1_CEILING:
        raise BundleError(
            "B-TIER-CEILING",
            f"{raw_tier} is unsignable in v1 (ceiling tier{V1_CEILING.value})",
        )

    decision = _parse_decision(payload.get("decision"))
    allowed_actions = _parse_allowed_actions(payload.get("allowed_actions"))
    ioc_sets, rules = _parse_rules_and_iocs(
        payload.get("ioc_sets"), payload.get("rules")
    )
    revocations = _parse_revocations(payload.get("revocations"))
    scope = _parse_scope(payload.get("segment_scope"))

    rollback_reference = payload.get("rollback_reference")
    if rollback_reference is not None and not isinstance(rollback_reference, dict):
        raise BundleError("B-SCHEMA", "rollback_reference must be an object")

    return Bundle(
        bundle_id=bundle_id,
        version=version,
        parent_version=parent_version,
        not_before=not_before,
        expires_at=expires_at,
        min_edge_version=min_edge_version,
        autonomy_tier=tier,
        decision=decision,
        allowed_actions=allowed_actions,
        rules=rules,
        ioc_sets=ioc_sets,
        revocations=revocations,
        segment_scope=scope,
        rollback_reference=dict(rollback_reference) if rollback_reference else None,
        raw=dict(payload),
    )


def rule_for_observation(bundle: Bundle, observation: Observation) -> Rule | None:
    """The rule the gate will see, resolved once so the advisor and the gate
    classify the same match."""
    return bundle.match(observation)


def _unknown_fields(
    obj: Mapping[str, Any], known: AbstractSet[str], where: str
) -> None:
    extra = sorted(set(obj) - known)
    if extra:
        raise BundleError("B-SCHEMA", f"unknown {where} field(s): {', '.join(extra)}")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BundleError(
            "B-BOUNDS", f"{field} must be a positive integer, got {value!r}"
        )
    return value


def _unit_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BundleError("B-BOUNDS", f"{field} must be a number, got {value!r}")
    as_float = float(value)
    if not 0.0 <= as_float <= 1.0:
        raise BundleError("B-BOUNDS", f"{field} must be within 0..1, got {as_float}")
    return as_float


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise BundleError(
            "B-SCHEMA", f"{field} must be an ISO-8601 string, got {value!r}"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise BundleError("B-SCHEMA", f"{field} not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BundleError("B-SCHEMA", f"{field} must carry a timezone: {value!r}")
    return parsed.astimezone(UTC)


def _semver(value: str) -> tuple[int, int, int] | None:
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _parse_decision(raw: Any) -> DecisionPolicy:
    if not isinstance(raw, dict):
        raise BundleError("B-SCHEMA", "decision must be an object")
    _unknown_fields(raw, _DECISION_FIELDS, "decision")
    auto_act = _unit_float(raw.get("auto_act_confidence"), "auto_act_confidence")
    escalate = _unit_float(raw.get("escalate_confidence"), "escalate_confidence")
    if escalate > auto_act:
        raise BundleError(
            "B-BOUNDS", "escalate_confidence must not exceed auto_act_confidence"
        )
    return DecisionPolicy(
        auto_act_confidence=auto_act,
        escalate_confidence=escalate,
        max_actions_per_hour=_positive_int(
            raw.get("max_actions_per_hour"), "max_actions_per_hour"
        ),
        max_active_blocks=_positive_int(
            raw.get("max_active_blocks"), "max_active_blocks"
        ),
        default_block_ttl_seconds=_positive_int(
            raw.get("default_block_ttl_seconds"), "default_block_ttl_seconds"
        ),
    )


def _parse_allowed_actions(raw: Any) -> tuple[AllowedAction, ...]:
    if not isinstance(raw, list) or not raw:
        raise BundleError("B-SCHEMA", "allowed_actions must be a non-empty list")
    actions: list[AllowedAction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise BundleError("B-SCHEMA", "allowed_actions entries must be objects")
        _unknown_fields(entry, {"action_type", "executor", "params"}, "allowed_action")
        action_type = entry.get("action_type")
        if action_type not in ACTION_TYPES:
            raise BundleError("B-ACTION", f"unsupported action_type: {action_type!r}")
        executor = entry.get("executor")
        if executor not in EXECUTORS:
            raise BundleError("B-ACTION", f"unsupported executor: {executor!r}")
        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise BundleError("B-SCHEMA", "params must be an object")
        _unknown_fields(params, _ACTION_PARAM_FIELDS, "params")
        max_ttl = params.get("max_ttl_seconds")
        if max_ttl is not None:
            max_ttl = _positive_int(max_ttl, "max_ttl_seconds")
        raw_namespaces = params.get("namespaces")
        if raw_namespaces is not None and (
            not isinstance(raw_namespaces, list)
            or not all(isinstance(n, str) for n in raw_namespaces)
        ):
            raise BundleError("B-SCHEMA", "namespaces must be a list of strings")
        namespaces = tuple(raw_namespaces or ())
        actions.append(
            AllowedAction(
                action_type=action_type,
                executor=executor,
                max_ttl_seconds=max_ttl,
                namespaces=namespaces,
            )
        )
    return tuple(actions)


def _parse_rules_and_iocs(
    raw_iocs: Any, raw_rules: Any
) -> tuple[dict[str, IocSet], tuple[Rule, ...]]:
    if not isinstance(raw_iocs, dict):
        raise BundleError("B-SCHEMA", "ioc_sets must be an object")
    ioc_sets: dict[str, IocSet] = {}
    for name, spec in raw_iocs.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            raise BundleError("B-SCHEMA", "ioc_sets must map names to objects")
        _unknown_fields(spec, _IOC_FIELDS, "ioc_set")
        kind = spec.get("kind")
        if kind not in IOC_KINDS:
            raise BundleError(
                "B-SCHEMA", f"ioc_set {name!r} kind must be one of {IOC_KINDS}"
            )
        entries = spec.get("entries")
        if (
            not isinstance(entries, list)
            or not entries
            or not all(isinstance(e, str) for e in entries)
        ):
            raise BundleError(
                "B-SCHEMA",
                f"ioc_set {name!r} entries must be a non-empty list of strings",
            )
        if kind in ("cidr", "ip"):
            for entry in entries:
                try:
                    (
                        ip_network(entry, strict=False)
                        if kind == "cidr"
                        else ip_address(entry)
                    )
                except ValueError as exc:
                    raise BundleError(
                        "B-SCHEMA", f"ioc_set {name!r} bad {kind} entry {entry!r}"
                    ) from exc
        source = spec.get("source")
        if source is not None and not isinstance(source, str):
            raise BundleError("B-SCHEMA", f"ioc_set {name!r} source must be a string")
        ioc_sets[name] = IocSet(
            name=name, kind=kind, entries=tuple(entries), source=source
        )

    if not isinstance(raw_rules, list):
        raise BundleError("B-SCHEMA", "rules must be a list")
    rules: list[Rule] = []
    for entry in raw_rules:
        if not isinstance(entry, dict):
            raise BundleError("B-SCHEMA", "rules entries must be objects")
        _unknown_fields(entry, {"rule_id", "match", "severity_floor"}, "rule")
        rule_id = entry.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            raise BundleError("B-SCHEMA", "rule_id must be a non-empty string")
        match = entry.get("match", {})
        if not isinstance(match, dict):
            raise BundleError("B-SCHEMA", "match must be an object")
        _unknown_fields(match, {"direction", "ioc_set", "dest_kind"}, "match")
        direction = match.get("direction", "any")
        if direction not in RULE_DIRECTIONS:
            raise BundleError(
                "B-SCHEMA", f"match direction must be one of {RULE_DIRECTIONS}"
            )
        dest_kind = match.get("dest_kind")
        if dest_kind not in DEST_KINDS:
            raise BundleError(
                "B-SCHEMA", f"match dest_kind must be one of {DEST_KINDS}"
            )
        ioc_set = match.get("ioc_set")
        if not isinstance(ioc_set, str) or ioc_set not in ioc_sets:
            raise BundleError(
                "B-SCHEMA", f"rule {rule_id!r} references unknown ioc_set {ioc_set!r}"
            )
        severity = entry.get("severity_floor")
        if severity not in SEVERITIES:
            raise BundleError(
                "B-SCHEMA",
                f"rule {rule_id!r} severity_floor must be one of {SEVERITIES}",
            )
        rules.append(
            Rule(
                rule_id=rule_id,
                direction=direction,
                dest_kind=dest_kind,
                ioc_set=ioc_set,
                severity_floor=severity,
            )
        )
    return ioc_sets, tuple(rules)


def _parse_revocations(raw: Any) -> tuple[Revocation, ...]:
    if not isinstance(raw, list):
        raise BundleError("B-SCHEMA", "revocations must be a list")
    revocations: list[Revocation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise BundleError("B-SCHEMA", "revocations entries must be objects")
        _unknown_fields(entry, {"bundle_id", "version"}, "revocation")
        bundle_id = entry.get("bundle_id")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise BundleError(
                "B-SCHEMA", "revocation bundle_id must be a non-empty string"
            )
        version = entry.get("version")
        if version is not None:
            version = _positive_int(version, "revocation.version")
        revocations.append(Revocation(bundle_id=bundle_id, version=version))
    return tuple(revocations)


def _parse_scope(raw: Any) -> SegmentScope:
    if not isinstance(raw, dict):
        raise BundleError("B-SCHEMA", "segment_scope must be an object")
    _unknown_fields(raw, _SCOPE_FIELDS, "segment_scope")
    cidrs_raw = raw.get("cidrs", [])
    if not isinstance(cidrs_raw, list) or not all(
        isinstance(c, str) for c in cidrs_raw
    ):
        raise BundleError("B-SCHEMA", "segment_scope cidrs must be a list of strings")
    for cidr in cidrs_raw:
        try:
            ip_network(cidr, strict=False)
        except ValueError as exc:
            raise BundleError("B-SCHEMA", f"segment_scope bad cidr {cidr!r}") from exc
    selector = raw.get("node_selector", {})
    if not isinstance(selector, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in selector.items()
    ):
        raise BundleError("B-SCHEMA", "node_selector must map strings to strings")
    vpc = raw.get("vpc")
    if vpc is not None and not isinstance(vpc, str):
        raise BundleError("B-SCHEMA", "vpc must be a string")
    return SegmentScope(
        vpc=vpc,
        cidrs=tuple(cidrs_raw),
        node_selector=dict(selector),
    )

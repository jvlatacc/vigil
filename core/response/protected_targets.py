"""Never-quarantine invariants: containment targets unattended response may
never touch, whatever the confidence.

An operator declares targets — an address, a range, a hostname pattern or an
infrastructure role — and containment rows naming them wait for a person no
matter what the confidence says. The ``DAEMON_NEVER_QUARANTINE`` environment
floor is read at each decision and can be undercut by nothing in the database
or the Settings UI (the environment-wins pattern the force-approval flag
established); operator rows stored in the ``protected_targets`` table may
tighten it and never loosen it. The daemon writes nothing here: it can only
demote its own autonomy, and only humans promote it.

Like every response decision, a hold renders its rule string (the #917
pattern) so the row records why it waited. Two postures are fail-closed: an
operator-row read that fails, and an env entry that fails to parse, each hold
containment for a person rather than running unattended with safety config
the daemon could not read.

Lives in ``core/`` because ``core`` must not import ``services``; the
Settings surface for the operator rows is ``services/api/routers/config.py``.
"""

import ipaddress
import logging
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable, List, Optional, Sequence, Tuple

from core.response.config import ResponseConfig, decision_rule
from core.storage.models import ProtectedTarget as ProtectedTargetRow

logger = logging.getLogger(__name__)

ORIGIN_ENV = "env"
ORIGIN_OPERATOR = "operator"

PROTECTED_KINDS = ("ip", "cidr", "hostname_glob", "role")

# Action types that change what a host, identity or session can reach — the
# rows an invariant bounds. Decisions that only observe (investigate, monitor,
# a workflow phase's approval) name no containment target and are never held.
CONTAINMENT_ACTION_TYPES = frozenset(
    {
        "isolate_host",
        "block_ip",
        "block_domain",
        "quarantine_file",
        "disable_user",
        "waf_block",
        "gateway_block",
        "access_revoke",
    }
)


@dataclass(frozen=True)
class ProtectedTarget:
    """One never-quarantine entry, from the env floor or an operator row."""

    kind: str  # "ip" | "cidr" | "hostname_glob" | "role"
    value: str  # canonical: "10.0.0.5" | "10.0.0.0/24" | "*.corp.example" | "domain_controller"
    origin: str  # ORIGIN_ENV (immutable floor) | ORIGIN_OPERATOR
    reason: str
    created_by: str


@dataclass(frozen=True)
class ProtectedTargetRules:
    """What a decision is evaluated against: the floor, the rows, the broken bits."""

    floor: Tuple[ProtectedTarget, ...] = ()  # everything origin=env, env entries first
    operator: Tuple[ProtectedTarget, ...] = ()
    unparsed: Tuple[str, ...] = ()  # env entries that failed to parse
    read_failed: bool = False  # the operator-row read failed

    @property
    def ordered(self) -> Tuple[ProtectedTarget, ...]:
        """Env-origin rules first, then operator rows; first match wins."""
        return self.floor + self.operator


def _canonical_ip(value: str) -> Optional[str]:
    """Canonical address text, or None for anything that is not one.

    IPv4-mapped IPv6 is normalised like the responder's target extraction, so
    a rule for ``10.0.0.5`` also covers ``::ffff:10.0.0.5``.
    """
    try:
        addr = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return str(addr)


def parse_entry(
    entry: str,
    origin: str,
    reason: str = "",
    created_by: str = "",
) -> Optional[ProtectedTarget]:
    """One ``kind:value`` entry, or None when it does not parse.

    The value is stored canonical, so a rule compares equal to the same
    address or range written differently. Hostname globs and roles are
    lower-cased: hostnames are case-insensitive.
    """
    text = entry.strip()
    kind, sep, value = text.partition(":")
    kind = kind.strip().lower()
    value = value.strip()
    if not sep or not value:
        return None
    if kind == "ip":
        addr = _canonical_ip(value)
        if addr is None:
            return None
        return ProtectedTarget(kind, addr, origin, reason, created_by)
    if kind == "cidr":
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            return None
        return ProtectedTarget(kind, str(network), origin, reason, created_by)
    if kind == "hostname_glob":
        if any(ch.isspace() for ch in value):
            return None
        return ProtectedTarget(kind, value.lower(), origin, reason, created_by)
    if kind == "role":
        return ProtectedTarget(kind, value.lower(), origin, reason, created_by)
    return None


def parse_entries(
    entries: Iterable[str],
    origin: str,
) -> Tuple[Tuple[ProtectedTarget, ...], Tuple[str, ...]]:
    """Parse ``kind:value`` entries; the ones that fail come back second.

    A caller holds containment while ``unparsed`` is non-empty: an entry the
    daemon could not read must not read as protection the daemon has.
    """
    parsed: List[ProtectedTarget] = []
    unparsed: List[str] = []
    for entry in entries:
        rule = parse_entry(entry, origin)
        if rule is None:
            unparsed.append(entry.strip())
            logger.error(
                "protected_targets: entry %r is not kind:value with kind in %s; "
                "containment is held for a person until it is fixed",
                entry,
                ", ".join(PROTECTED_KINDS),
            )
        else:
            parsed.append(rule)
    return tuple(parsed), tuple(unparsed)


def _matches(rule: ProtectedTarget, target: str) -> bool:
    if rule.kind == "ip":
        return _canonical_ip(target) == rule.value
    if rule.kind == "cidr":
        addr = _canonical_ip(target)
        if addr is None:
            return False
        return ipaddress.ip_address(addr) in ipaddress.ip_network(rule.value)
    if rule.kind == "hostname_glob":
        return fnmatchcase(target.strip().lower(), rule.value)
    # role: a target names the role verbatim; address-level protection for a
    # role comes from listing its addresses as ip or cidr entries.
    return target.strip().lower() == rule.value


def match_target(
    action_type: str,
    target: str,
    rules: Sequence[ProtectedTarget],
) -> Optional[ProtectedTarget]:
    """The first rule that covers this containment target, or None.

    ``rules`` are evaluated in the order given: env-origin rules first, then
    operator rows — first match wins. Only containment action types are ever
    matched.
    """
    if action_type not in CONTAINMENT_ACTION_TYPES or not target:
        return None
    for rule in rules:
        if _matches(rule, target):
            return rule
    return None


def invariant_hold(
    action_type: str,
    target: str,
    rules: ProtectedTargetRules,
) -> Optional[str]:
    """The #917 rule string when this containment must wait for a person.

    The fail-closed postures come before matching: a read that failed or an
    env entry that did not parse holds every containment row until fixed,
    whatever the target.
    """
    if action_type not in CONTAINMENT_ACTION_TYPES:
        return None
    if rules.read_failed:
        return decision_rule("approval.protected_target_read", "failed")
    if rules.unparsed:
        return decision_rule("approval.protected_target_unparsed", len(rules.unparsed))
    matched = match_target(action_type, target, rules.ordered)
    if matched is not None:
        return decision_rule(
            "approval.protected_target",
            f"{matched.origin}:{matched.kind}:{matched.value}",
        )
    return None


def containment_hold(
    action_type: str,
    target: str,
    rules: ProtectedTargetRules,
    parameters: Optional[dict] = None,
) -> Optional[str]:
    """``invariant_hold`` for the row target, then the hostname parameter.

    An IP-less isolation keys its row on a hostname, so a rule written for
    the hostname must hold that row too.
    """
    hold = invariant_hold(action_type, target, rules)
    if hold is None and parameters:
        hostname = parameters.get("hostname")
        if isinstance(hostname, str) and hostname and hostname != target:
            hold = invariant_hold(action_type, hostname, rules)
    return hold


def _row_to_target(row: ProtectedTargetRow) -> ProtectedTarget:
    return ProtectedTarget(
        kind=row.kind,
        value=row.value,
        origin=row.origin,
        reason=row.reason or "",
        created_by=row.created_by or "",
    )


def load_rows() -> Tuple[ProtectedTarget, ...]:
    """Every active row in the ``protected_targets`` table.

    Raises on a failed read; the callers fail closed rather than decide.
    """
    from core.storage.connection import get_db_manager
    from core.storage.protected_target_repository import active_rows

    with get_db_manager().session_scope() as session:
        return tuple(_row_to_target(row) for row in active_rows(session))


def current_rules(config: ResponseConfig) -> ProtectedTargetRules:
    """The env floor plus the operator rows, fail-closed on a failed read."""
    floor, unparsed = parse_entries(config.never_quarantine, ORIGIN_ENV)
    try:
        rows = load_rows()
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Cannot read the protected targets; holding containment for a "
            "person: %s",
            e,
        )
        return ProtectedTargetRules(floor=floor, unparsed=unparsed, read_failed=True)
    db_env = tuple(r for r in rows if r.origin == ORIGIN_ENV)
    operator = tuple(r for r in rows if r.origin != ORIGIN_ENV)
    return ProtectedTargetRules(
        floor=floor + db_env, operator=operator, unparsed=unparsed
    )


def env_floor_rules(config: ResponseConfig) -> ProtectedTargetRules:
    """The floor alone — no database read — for a check made before a row exists."""
    floor, unparsed = parse_entries(config.never_quarantine, ORIGIN_ENV)
    return ProtectedTargetRules(floor=floor, unparsed=unparsed)

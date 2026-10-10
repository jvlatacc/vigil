"""Never-quarantine invariants: assets the Responder may not auto-contain
against (#944).

A protected asset is operator-declared infrastructure — a DNS server, a domain
controller, a gateway — that the auto-approval path must never act on at any
confidence or severity. A hit does not drop the action: it forces human
approval, carrying the invariant's rationale, and a person may still approve
the pending action (the deliberate emergency valve for a domain controller
that genuinely is compromised).

Matching is most-specific-first: an exact IP, then the longest-prefix CIDR the
address falls inside, then a case-insensitive exact hostname. Matching reads a
memory-resident index behind the exclusions cache pattern (short TTL, dropped
on writes through this module; other processes wait out the TTL).

Fail-closed on uncertainty: when the index holds no rules *and* the database
is unreachable, the invariant set cannot be verified — so every target is
treated as protected and machine-speed response waits for a person. A stale
non-empty index is used with a warning: it under-protects at most the rows
added since the read, where a blind allow under-protects everything.

This is execution safety, deliberately separate from
``core.findings.exclusions``: an exclusion hides *findings* from the queue,
this module constrains what *actions* may run. Neither reads the other, and
the exclusions modules are never imported here.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.findings.ip_address import normalize_ip
from core.response.config import decision_rule
from core.storage import protected_asset_repository as repo
from core.storage.models import ProtectedAsset
from core.storage.models.protected_asset import ASSET_CLASSES, MATCH_KINDS
from core.storage.schemas.base import _iso_utc
from core.time import utcnow

__all__ = [
    "ASSET_CLASSES",
    "MATCH_KINDS",
    "ProtectedAssetConflict",
    "ProtectedAssetError",
    "ProtectedAssetIndex",
    "ProtectedHit",
    "ProtectedRule",
    "canonical_match_value",
    "create_protected_asset",
    "invalidate_cache",
    "list_protected_assets",
    "parse_seed_entry",
    "protected_asset_hit",
    "remove_protected_asset",
    "seed_protected_assets",
    "serialize",
]

logger = logging.getLogger(__name__)

MAX_LABEL_LENGTH = 200
MAX_VALUE_LENGTH = 260
MAX_REASON_LENGTH = 2000

# A hostname is letters, digits, dots and hyphens — no scheme, no path, no
# wildcard in v1: an over-broad match protects more than the operator looked at.
_HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])$")


class ProtectedAssetError(ValueError):
    """A request the protected-asset store refuses; the message is user-facing."""


class ProtectedAssetConflict(ProtectedAssetError):
    """The asset is already actively protected."""


def canonical_match_value(match_kind: str, match_value: Any) -> str:
    """Validate ``match_value`` for ``match_kind`` and return its canonical text.

    This is the one spelling the table stores, the index matches with, and the
    seed and the API both validate through, so a row can never disagree with
    the value a caller declared.
    """
    if not isinstance(match_value, str) or not match_value.strip():
        raise ProtectedAssetError(f"{match_kind} value is required")
    value = match_value.strip()
    if len(value) > MAX_VALUE_LENGTH:
        raise ProtectedAssetError(
            f"{match_kind} value must be at most {MAX_VALUE_LENGTH} characters"
        )
    if match_kind == "ip":
        normalized = normalize_ip(value)
        if normalized is None:
            raise ProtectedAssetError(f"{value!r} is not a single IPv4 or IPv6 address")
        return normalized
    if match_kind == "cidr":
        try:
            # strict=False: a bare network address like 10.0.0.53/24 names the
            # 10.0.0.0/24 range, which is what the operator meant.
            return ipaddress.ip_network(value, strict=False).with_prefixlen
        except ValueError:
            raise ProtectedAssetError(
                f"{value!r} is not an IPv4 or IPv6 network in CIDR notation"
            ) from None
    if match_kind == "hostname":
        lowered = value.lower()
        if not _HOSTNAME_RE.match(lowered):
            raise ProtectedAssetError(
                f"{value!r} is not one exact hostname (letters, digits,"
                " dots, hyphens — no wildcard, no path)"
            )
        return lowered
    raise ProtectedAssetError(f"match_kind must be one of {', '.join(MATCH_KINDS)}")


def _validate_asset_class(asset_class: Any) -> str:
    if asset_class not in ASSET_CLASSES:
        raise ProtectedAssetError(
            f"asset_class must be one of {', '.join(ASSET_CLASSES)}"
        )
    return asset_class


def _clean_label(label: Any) -> str:
    if not isinstance(label, str) or not label.strip():
        raise ProtectedAssetError("A label is required")
    text = label.strip()
    if len(text) > MAX_LABEL_LENGTH:
        raise ProtectedAssetError(
            f"Label must be at most {MAX_LABEL_LENGTH} characters"
        )
    return text


def _clean_reason(reason: Any) -> Optional[str]:
    text = reason.strip() if isinstance(reason, str) else ""
    if not text:
        return None
    if len(text) > MAX_REASON_LENGTH:
        raise ProtectedAssetError(
            f"Reason must be at most {MAX_REASON_LENGTH} characters"
        )
    return text


def parse_seed_entry(entry: dict) -> Dict[str, str]:
    """One ``DAEMON_PROTECTED_ASSETS`` or API-create object, validated.

    Returns ``{"match_kind", "match_value", "asset_class", "label"}`` with
    canonical spelling; raises :class:`ProtectedAssetError` on anything a
    reader could not honor.
    """
    if not isinstance(entry, dict):
        raise ProtectedAssetError("a protected asset must be a JSON object")
    match_kind = entry.get("match_kind")
    if match_kind not in MATCH_KINDS:
        raise ProtectedAssetError(f"match_kind must be one of {', '.join(MATCH_KINDS)}")
    return {
        "match_kind": match_kind,
        "match_value": canonical_match_value(match_kind, entry.get("match_value")),
        "asset_class": _validate_asset_class(entry.get("asset_class")),
        "label": _clean_label(entry.get("label")),
    }


@dataclass(frozen=True)
class ProtectedRule:
    """One active invariant row, in the form the index matches with."""

    match_kind: str
    match_value: str
    asset_class: str
    label: str
    # Parsed once at construction so a match is arithmetic, not parsing.
    _network: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def validated(
        cls, *, match_kind: str, match_value: str, asset_class: str, label: str
    ) -> "ProtectedRule":
        canonical = canonical_match_value(match_kind, match_value)
        parsed: Any = None
        if match_kind == "ip":
            parsed = ipaddress.ip_address(canonical)
        elif match_kind == "cidr":
            parsed = ipaddress.ip_network(canonical)
        return cls(
            match_kind=match_kind,
            match_value=canonical,
            asset_class=_validate_asset_class(asset_class),
            label=_clean_label(label),
            _network=parsed,
        )

    @classmethod
    def from_row(cls, row: ProtectedAsset) -> "ProtectedRule":
        # A hand-edit could corrupt a TEXT value behind the CHECK's back (the
        # constraints pin kind and class, not the network's well-formedness).
        # That raises here, the read fails, and the module fails closed: an
        # invariant set that cannot be parsed is not one to act past.
        return cls.validated(
            match_kind=row.match_kind,
            match_value=row.match_value,
            asset_class=row.asset_class,
            label=row.label,
        )


@dataclass(frozen=True)
class ProtectedHit:
    """A target the invariant held — an action on it waits for a person."""

    match_kind: str
    match_value: str
    asset_class: str
    label: str
    # True on the fail-closed path: no verified invariant set and no way to
    # read one, so the specific row is unknown even though the hold is not.
    fail_closed: bool = False

    @classmethod
    def from_rule(cls, rule: ProtectedRule) -> "ProtectedHit":
        return cls(
            match_kind=rule.match_kind,
            match_value=rule.match_value,
            asset_class=rule.asset_class,
            label=rule.label,
        )

    @classmethod
    def unverified(cls, target: Optional[str]) -> "ProtectedHit":
        """The fail-closed hit: the invariant set could not be verified."""
        return cls(
            match_kind="unverified",
            match_value=target or "unknown",
            asset_class="unverified",
            label="",
            fail_closed=True,
        )

    def rule(self) -> str:
        """The rationale the action row records (#917) — e.g.
        ``response.protected_asset=10.0.0.53 (asset_class=dns)``."""
        if self.fail_closed:
            return (
                f"{decision_rule('response.protected_asset', self.match_value)}"
                " (asset_class=unverified; index unavailable, failing closed)"
            )
        return (
            f"{decision_rule('response.protected_asset', self.match_value)}"
            f" (asset_class={self.asset_class})"
        )


class ProtectedAssetIndex:
    """Memory-resident matcher over a snapshot of active invariant rows."""

    def __init__(self, rules: Iterable[ProtectedRule] = ()):
        rules = tuple(rules)
        self._ip_rules = [r for r in rules if r.match_kind == "ip"]
        # Networks sorted deepest-first: the first containing range is the
        # most specific, so "longest prefix wins" needs no max() scan.
        self._cidr_rules = sorted(
            (r for r in rules if r.match_kind == "cidr"),
            key=lambda r: r._network.prefixlen,
            reverse=True,
        )
        self._hostname_rules = {
            r.match_value: r for r in rules if r.match_kind == "hostname"
        }

    def match(
        self, ip_address: Optional[str], hostname: Optional[str]
    ) -> Optional[ProtectedHit]:
        """The invariant holding this target, or ``None`` when none does.

        Order is the spec's: exact IP, then longest-prefix CIDR, then
        case-insensitive exact hostname. An unparseable address matches
        nothing — a target the responder could not parse was never acted on
        anyway.
        """
        address = _as_address(ip_address)
        if address is not None:
            for rule in self._ip_rules:
                if rule._network == address:
                    return ProtectedHit.from_rule(rule)
            for rule in self._cidr_rules:
                if (
                    rule._network.version == address.version
                    and address in rule._network
                ):
                    return ProtectedHit.from_rule(rule)
        host = _as_hostname(hostname)
        if host is not None:
            rule = self._hostname_rules.get(host)
            if rule is not None:
                return ProtectedHit.from_rule(rule)
        return None


def _as_address(value: Any) -> Optional[Any]:
    """The address in ``value``, or None for absent/"unknown"/malformed input."""
    if not isinstance(value, str) or not value.strip() or value == "unknown":
        return None
    normalized = normalize_ip(value)
    return ipaddress.ip_address(normalized) if normalized else None


def _as_hostname(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    return lowered or None


# The index is asked per action; a short TTL keeps that from being a query per
# finding while a change still lands within seconds. Writes made through this
# module drop it at once (in this process; others wait out the TTL).
_CACHE_TTL_SECONDS = 15.0
_cache_lock = threading.Lock()
_cache: Optional[Tuple[ProtectedRule, ...]] = None
_cache_at = 0.0


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _invalidate_on_commit(session: Session) -> None:
    # Now and again after commit: a reader between the two would otherwise
    # cache the pre-commit set for a full TTL.
    invalidate_cache()
    event.listen(session, "after_commit", lambda _s: invalidate_cache(), once=True)


def _read_active_rules() -> Tuple[ProtectedRule, ...]:
    from core.storage.unit_of_work import unit_of_work

    with unit_of_work() as session:
        return tuple(ProtectedRule.from_row(row) for row in repo.active_rows(session))


def _current_rules() -> Tuple[Tuple[ProtectedRule, ...], bool]:
    """``(rules, fresh)`` — the last known invariant set and whether it was
    read from the database on this call.

    A failed read is not cached. With a stale non-empty set that set is used
    (logged); with nothing, the caller fails closed.
    """
    global _cache, _cache_at
    with _cache_lock:
        if _cache is not None and time.monotonic() - _cache_at < _CACHE_TTL_SECONDS:
            return _cache, True
    try:
        value = _read_active_rules()
    except Exception as e:  # noqa: BLE001 — the DB being down is the case, not a bug
        with _cache_lock:
            stale = _cache
        if stale:
            logger.warning(
                "Could not read protected assets; holding the last known set"
                " of %d: %s",
                len(stale),
                e,
            )
            return stale, False
        logger.error(
            "Could not read protected assets and none are known; the invariant"
            " set cannot be verified: %s",
            e,
        )
        return (), False
    with _cache_lock:
        _cache, _cache_at = value, time.monotonic()
    return value, True


def protected_asset_hit(
    ip_address: Optional[str], hostname: Optional[str]
) -> Optional[ProtectedHit]:
    """The never-quarantine invariant holding this target, or ``None``.

    Fail-closed: no known rules *and* an unreachable database means the
    invariant set cannot be verified, so every target reads as protected and
    machine-speed response waits for a person.
    """
    rules, fresh = _current_rules()
    if not rules:
        if fresh:
            # Verified empty: a read succeeded within the TTL and the operator
            # protects nothing (yet) — allowing acts on a verified set.
            return None
        return ProtectedHit.unverified(ip_address or hostname)
    return ProtectedAssetIndex(rules).match(ip_address, hostname)


# ---------------------------------------------------------------------------
# CRUD — a caller-provided session, audit on the caller's transaction
# ---------------------------------------------------------------------------


def serialize(row: ProtectedAsset) -> Dict[str, Any]:
    return {
        "asset_id": str(row.asset_id),
        "match_kind": row.match_kind,
        "match_value": row.match_value,
        "asset_class": row.asset_class,
        "label": row.label,
        "created_by": row.created_by,
        "created_at": _iso_utc(row.created_at) if row.created_at else None,
        "removed_at": _iso_utc(row.removed_at) if row.removed_at else None,
        "removed_by": row.removed_by,
        "removal_reason": row.removal_reason,
        "active": row.removed_at is None,
    }


def list_protected_assets(
    session: Session, *, include_removed: bool = False
) -> List[Dict[str, Any]]:
    """Newest first."""
    return [
        serialize(row)
        for row in repo.list_rows(session, include_removed=include_removed)
    ]


def create_protected_asset(
    session: Session,
    *,
    match_kind: str,
    match_value: str,
    asset_class: str,
    label: str,
    created_by: str,
) -> Dict[str, Any]:
    fields = parse_seed_entry(
        {
            "match_kind": match_kind,
            "match_value": match_value,
            "asset_class": asset_class,
            "label": label,
        }
    )
    if (
        repo.active_row_for(session, fields["match_kind"], fields["match_value"])
        is not None
    ):
        raise ProtectedAssetConflict(
            f"{fields['match_value']} ({fields['match_kind']}) is already protected"
        )
    row = ProtectedAsset(
        asset_id=uuid.uuid4(),
        created_by=created_by,
        created_at=utcnow(),
        **fields,
    )
    # Two operators declaring the same asset at once both pass the check
    # above; the SAVEPOINT keeps the unique index's refusal from poisoning
    # the request.
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as e:
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
        if constraint != "uniq_protected_assets_active":
            raise
        raise ProtectedAssetConflict(
            f"{fields['match_value']} ({fields['match_kind']}) is already protected"
        ) from e
    _invalidate_on_commit(session)
    logger.info(
        "Protected asset %s added (%s %s, %s) by %s",
        row.asset_id,
        row.match_kind,
        row.match_value,
        row.asset_class,
        created_by,
    )
    return serialize(row)


def remove_protected_asset(
    session: Session, asset_id: str, *, removed_by: str, reason: Any = None
) -> Optional[Dict[str, Any]]:
    """Mark an active asset removed; ``None`` when there is no such row.

    Removing an already-removed asset returns it unchanged, so a double click
    is not an error and the first removal's record is kept.
    """
    row = repo.row_by_id(session, asset_id)
    if row is None:
        return None
    if row.removed_at is None:
        row.removed_at = utcnow()
        row.removed_by = removed_by
        row.removal_reason = _clean_reason(reason)
        session.flush()
        _invalidate_on_commit(session)
        logger.info(
            "Protected asset %s (%s %s) removed by %s",
            asset_id,
            row.match_kind,
            row.match_value,
            removed_by,
        )
    return serialize(row)


# ---------------------------------------------------------------------------
# Boot seed — DAEMON_PROTECTED_ASSETS, idempotent by (kind, value)
# ---------------------------------------------------------------------------


def seed_protected_assets(
    session: Session, entries: Iterable[dict], *, created_by: str = "daemon-boot"
) -> List[Dict[str, Any]]:
    """Declare every settings entry as an active row, skipping ones present.

    Every entry is validated before anything is written, and a failure raises:
    a seed the daemon cannot honor must stop the boot, not silently protect
    less than the operator declared (fail closed).
    """
    validated = [parse_seed_entry(entry) for entry in entries]
    created: List[Dict[str, Any]] = []
    for fields in validated:
        if (
            repo.active_row_for(session, fields["match_kind"], fields["match_value"])
            is not None
        ):
            continue
        row = ProtectedAsset(
            asset_id=uuid.uuid4(),
            created_by=created_by,
            created_at=utcnow(),
            **fields,
        )
        session.add(row)
        created.append(serialize(row))
    if created:
        session.flush()
        invalidate_cache()
        logger.info(
            "Seeded %d protected asset(s) from settings (%d already present)",
            len(created),
            len(validated) - len(created),
        )
    return created

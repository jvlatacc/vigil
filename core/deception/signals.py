"""Deterministic recon scoring for the honey-routing posture.

The predicate reads what the evidence says — MITRE recon/lateral TIDs, the
finding's category, and the addresses in ``entity_context`` — never what the
triage model guessed. AI-triage output alone inherits the model's
false-positive profile, and a deception that steers a benign source is worse
than no deception at all.

The source address is canonicalized through the same path the IP-exclusion
feature uses (:data:`~core.storage.ip_exclusion_repository.FINDING_IP_KEYS`),
because the key set of ``entity_context`` varies by data source. Only the
*source-shaped* keys name the attacker here — the dst keys name the victim.
"""

import ipaddress
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.storage.ip_exclusion_repository import FINDING_IP_KEYS  # noqa: F401 —

# the documented canonicalization path; re-exported so callers share one name.
from core.time import utcnow

logger = logging.getLogger(__name__)

# Recon and lateral-movement discovery techniques, plus the sub-techniques
# the pipeline actually emits. ``T1595`` covers its .003+ children via the
# base-id match in :func:`recon_tids`.
RECON_TIDS = frozenset(
    {
        "T1046",  # Network Service Discovery
        "T1018",  # Remote System Discovery
        "T1595",  # Active Scanning
        "T1595.001",  # Active Scanning: Scanning IP Blocks
        "T1595.002",  # Active Scanning: Vulnerability Scanning
        "T1135",  # Network Share Discovery
        "T1016",  # System Network Configuration Discovery
    }
)

# Finding categories that name the phase the posture is for.
RECON_CATEGORIES = frozenset({"recon", "lateral_movement"})

# The source-shaped subset of FINDING_IP_KEYS: the attacker, never the
# victim. Order is extraction preference.
SOURCE_IP_KEYS = ("src_ip", "src_ips", "source_ip", "source_ips", "srcip")

# The victim-shaped subset: where the probes were headed.
DESTINATION_IP_KEYS = (
    "dst_ip",
    "dst_ips",
    "dest_ip",
    "dest_ips",
    "destination_ip",
    "destination_ips",
    "dstip",
)


def routable_ip(value: Any) -> Optional[str]:
    """The host address in ``value``, or None for anything not worth acting on.

    Mirrors ``services.daemon.responder._actionable_ip`` — core cannot import
    services, and the deception predicate needs the same refusal of loopback,
    multicast, link-local, reserved and unspecified addresses, plus
    normalization of IPv4-mapped IPv6. Keep the two in agreement.
    """
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except (ValueError, TypeError):
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_link_local
        or ip.is_reserved
    ):
        return None
    return str(ip)


def _ips_under(context: Dict[str, Any], keys: Tuple[str, ...]) -> List[str]:
    """Validated addresses under any of ``keys`` in ``entity_context``.

    A key's value may be a scalar or a list — the key set is source-dependent
    and so is the value shape.
    """
    found: List[str] = []
    for key in keys:
        value = context.get(key)
        if value is None:
            continue
        candidates = value if isinstance(value, (list, tuple, set)) else [value]
        for candidate in candidates:
            ip = routable_ip(candidate)
            if ip and ip not in found:
                found.append(ip)
    return found


def canonical_source_ip(finding: Dict[str, Any]) -> Optional[str]:
    """The attacker address a lease would steer, canonicalized.

    First source-shaped hit wins — the same convention as the responder's
    ``src_ips[0]`` extraction for isolate/block.
    """
    context = finding.get("entity_context") or {}
    if not isinstance(context, dict):
        return None
    ips = _ips_under(context, SOURCE_IP_KEYS)
    return ips[0] if ips else None


def destination_ips(finding: Dict[str, Any]) -> List[str]:
    """The internal addresses the probes targeted, for the steer scope."""
    context = finding.get("entity_context") or {}
    if not isinstance(context, dict):
        return []
    return _ips_under(context, DESTINATION_IP_KEYS)


def extract_ports(finding: Dict[str, Any]) -> List[int]:
    """The suspicious service ports, scoped to the probe — never wholesale.

    Read from ``entity_context`` then the finding body; anything that is not
    a plausible port number is dropped. An empty result means the finding
    named no ports; the backend decides what that scopes to, and the
    controller driver must treat it conservatively.
    """
    context = finding.get("entity_context") or {}
    raw: Any = None
    if isinstance(context, dict):
        raw = context.get("ports")
    if raw is None:
        raw = finding.get("ports")
    if raw is None:
        return []
    candidates = raw if isinstance(raw, (list, tuple, set)) else [raw]
    ports: List[int] = []
    for candidate in candidates:
        try:
            port = int(candidate)
        except (TypeError, ValueError):
            continue
        if 0 < port < 65536 and port not in ports:
            ports.append(port)
    return ports


def _tid_keys(value: Any) -> List[str]:
    """MITRE technique ids from the shapes the pipeline emits.

    ``mitre_predictions`` reaches the daemon as ``Dict[str, float]``
    (technique -> score, normalized at ingest) but nothing here may trust
    that: accept dict keys, plain strings and lists, and ignore the rest.
    """
    if isinstance(value, dict):
        return [str(k).upper() for k in value.keys()]
    if isinstance(value, str):
        return [value.upper()]
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item.upper())
            elif isinstance(item, dict) and item.get("tid"):
                out.append(str(item["tid"]).upper())
        return out
    return []


def recon_tids(finding: Dict[str, Any]) -> set:
    """The recon-relevant technique ids this finding carries.

    A sub-technique matches via its base id, so ``T1595.003`` counts even
    though only .001/.002 are listed by name.
    """
    tids = set()
    for tid in _tid_keys(finding.get("mitre_predictions")):
        base = tid.split(".")[0]
        if tid in RECON_TIDS or base in RECON_TIDS:
            tids.add(tid)
    return tids


def is_recon_shaped(finding: Dict[str, Any]) -> bool:
    """Whether the finding's own evidence names recon or lateral movement."""
    if recon_tids(finding):
        return True
    category = str(finding.get("category") or "").lower()
    return category in RECON_CATEGORIES


def recon_evidence(finding: Dict[str, Any]) -> Dict[str, Any]:
    """What the predicate saw, for the probe row and the approval reason."""
    return {
        "tids": sorted(recon_tids(finding)),
        "category": finding.get("category"),
        "destination_ips": destination_ips(finding),
        "ports": extract_ports(finding),
    }


class DeceptionSignalService:
    """Per-attacker corroboration over the durable probe log.

    One recon-shaped finding is one observation, not a verdict; the posture
    fires on the *count*. Probes live in Postgres — the daemon and the API
    are separate processes, so anything the console must show cannot live in
    this one's memory.
    """

    def __init__(self, config=None):
        # DeceptionConfig, or a test double's config; None reads Settings.
        if config is None:
            from core.deception.config import DeceptionConfig

            config = DeceptionConfig.from_settings()
        self.config = config

    def record_probe(
        self,
        source_ip: str,
        finding_id: Optional[str],
        evidence: Dict[str, Any],
        now=None,
    ) -> Optional[str]:
        """Log one recon observation for ``source_ip``. Returns the probe id."""
        import uuid

        from core.storage.connection import get_db_manager
        from core.storage.models import DeceptionProbe

        now = now or utcnow()
        probe_id = f"deception-probe-{uuid.uuid4().hex[:16]}"
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                session.add(
                    DeceptionProbe(
                        probe_id=probe_id,
                        source_ip=source_ip,
                        finding_id=finding_id,
                        evidence=evidence,
                        created_at=now,
                    )
                )
            return probe_id
        except Exception as e:  # noqa: BLE001 — a probe-log failure must never
            # break the response evaluation this runs inside.
            logger.error("Failed to record deception probe: %s", e)
            return None

    def is_corroborated(self, source_ip: str, now=None) -> bool:
        """At least ``min_observations`` distinct probes inside the window.

        Distinct by finding id: a re-delivered finding is one observation,
        not two. A failed read answers False — uncertainty never steers.
        """
        from sqlalchemy import func, select

        from core.storage.connection import get_db_manager
        from core.storage.models import DeceptionProbe

        now = now or utcnow()
        since = now - timedelta(seconds=self.config.window_seconds)
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                count = session.execute(
                    select(
                        func.count(
                            func.distinct(
                                func.coalesce(
                                    DeceptionProbe.finding_id, DeceptionProbe.probe_id
                                )
                            )
                        )
                    ).where(
                        DeceptionProbe.source_ip == source_ip,
                        DeceptionProbe.created_at >= since,
                    )
                ).scalar_one()
            return int(count or 0) >= self.config.min_observations
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read deception corroboration: %s", e)
            return False

    def prune(self, now=None) -> int:
        """Drop probes older than twice the corroboration window. Returns count."""
        from core.storage.connection import get_db_manager
        from core.storage.models import DeceptionProbe

        now = now or utcnow()
        cutoff = now - timedelta(seconds=2 * self.config.window_seconds)
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                deleted = (
                    session.query(DeceptionProbe)
                    .filter(DeceptionProbe.created_at < cutoff)
                    .delete(synchronize_session=False)
                )
                return int(deleted or 0)
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to prune deception probes: %s", e)
            return 0

    def kill_switch_active(self, now=None) -> bool:
        """The env override, or the console toggle — either one trips it.

        A failed read of the stored toggle leaves steering refused rather
        than resumed: the switch's whole job is to be the pessimistic answer.
        """
        from core.deception.config import KILL_SWITCH_CONFIG_KEY

        if self.config.kill_switch:
            return True
        try:
            from core.storage.config_service import get_config_service

            value = get_config_service().read_system_config(KILL_SWITCH_CONFIG_KEY)
            return bool(value.get("enabled", False)) if value else False
        except Exception as e:  # noqa: BLE001
            logger.error("Cannot read the deception kill switch; treating as on: %s", e)
            return True


def deception_signal_for_finding(
    finding: Dict[str, Any],
    *,
    signals: DeceptionSignalService,
    allowlist,
    now=None,
) -> bool:
    """The deterministic honey-routing predicate:
    enabled ∧ recon-shaped ∧ not exempt ∧ corroborated.

    Pure in its inputs — the corroboration read and the probe write happen
    through ``signals``, which callers may fake. The processor calls this
    from ``_evaluate_for_response``; the responder trusts the flag it
    receives on the queue item rather than re-deriving it.
    """
    if not signals.config.enabled:
        return False
    if signals.kill_switch_active(now):
        return False
    source_ip = canonical_source_ip(finding)
    if source_ip is None:
        return False
    if not is_recon_shaped(finding):
        return False
    if allowlist.is_exempt(source_ip, now):
        return False
    # A recon-shaped, non-exempt observation counts toward corroboration even
    # when it does not yet reach the floor: the third probe is what makes the
    # fourth actionable.
    signals.record_probe(
        source_ip, finding.get("finding_id"), recon_evidence(finding), now
    )
    return signals.is_corroborated(source_ip, now)

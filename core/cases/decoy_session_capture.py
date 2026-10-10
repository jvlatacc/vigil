"""Capture decoy session events as Finding + case evidence + IOCs.

The capture plane of the MTD spec (plane 04): every decoy session event the
daemon's webhook ingest receives becomes exactly one Finding (the rollup- and
dedupe-facing record), one ``CaseEvidence`` transcript (the sandbox-report
precedent — ``analysis_results`` carries the whole session), and ``CaseIOC``
rows for the attacker address and dropped-file hashes. All three land in one
transaction: a capture that dies halfway must leave nothing behind, because a
half-written session reads as evidence it is not.

Wire contract
-------------
The payload is the contract ``services/decoy/session.py`` renders — one dict
per session with ``finding_id`` pinned to the session id and ``data_source``
naming this plane. The two literals that cross the process boundary are
defined here (core cannot import services) and pinned to the decoy side by
``tests/unit/decoy/test_capture_wire_contract.py`` — the same static-agreement
mechanism the recall contract uses.

Credential invariant
--------------------
``auth_attempts`` entries carry a credential *tag* (``canary`` / ``rejected``),
never a value. If a future decoy ever emits the value an attacker typed, it is
payload: it belongs in this evidence and IOC JSONB — where it is the data —
and must never reach a log line or a telemetry span (the sanitizer scrubs
spans by design; nothing here feeds it). Every log statement in this module
carries ids and counts only.

Entity keys
-----------
The intel pipeline expects keys minted by the one rule
(``core.memory.entity_keys.entity_key``), and it derives a case's subjects
from ``CaseIOC`` rows typed in the ``ENTITY_KEY_TYPES`` vocabulary at close
time. Both halves are honored here: IOC ``ioc_type`` values are vocabulary
members (``ip``, ``hash``), and each row's ``enrichment_data`` records the
canonical key minted at capture.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.memory.entity_keys import entity_key
from core.storage.models import (
    Case,
    CaseEvidence,
    CaseIOC,
    Finding,
    FindingMitrePrediction,
)
from core.storage.unit_of_work import unit_of_work
from core.threat_intel.mitre_lookup import resolve_technique
from core.time import utcnow

logger = logging.getLogger(__name__)

# The data_source stamp every decoy session event carries (the emitter pins
# it; see the wire-contract test). It doubles as the Finding's data_source.
DECOY_SESSION_DATA_SOURCE = "vigil-decoy"

# All decoy-session evidence lands on one standing case: sessions start
# case-less (like feed-indicator hunt proposals), and one addressable case
# beats per-session case spam for a noisy attacker. Deterministic id, so
# replays and every daemon worker converge on the same row.
DECOY_INTEL_CASE_ID = "case-decoy-intel"
DECOY_INTEL_CASE_TITLE = "Decoy session intel"

DECOY_EVIDENCE_TYPE = "decoy_session"
DECOY_IOC_SOURCE = "decoy"
DECOY_CAPTURE_COLLECTED_BY = "decoy-capture"

# findings.finding_id is VARCHAR(50); the emitter's ids are 22 chars. A longer
# id is a malformed event, and the column is the contract that says so.
_FINDING_ID_MAX = 50

# Canonical ATT&CK id shape — technique plus optional sub-technique.
_TECHNIQUE_ID_RE = re.compile(r"^T\d{4}(\.\d{3})?$")

# "Present, no score" — the confidence the webhook's own normalizer and the
# internal producers use for a technique observed without a model score.
_OBSERVED_CONFIDENCE = 1.0


@dataclass(frozen=True)
class DecoySessionEvent:
    """One parsed decoy session event — the wire contract, validated."""

    session_id: str
    decoy_service: str
    attacker_ip: str
    attacker_entity_key: str
    session_start: datetime
    session_end: datetime
    routing_action_id: Optional[str]
    auth_attempts: List[Dict[str, Any]]
    commands: List[str]
    files_dropped: List[Dict[str, Any]]
    mitre_techniques: List[str]
    raw: Dict[str, Any]
    auth_successes: int = 0


def _iso(value: Any, what: str) -> datetime:
    """Parse the contract's ISO-8601 stamps to a naive-UTC datetime.

    Columns are naive ``DateTime`` (core.time's rule): an aware stamp is
    converted to UTC and stripped, so a session timestamp can never TypeError
    against a stored row.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"decoy session event has no {what}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(
            f"decoy session event has a malformed {what}: {value!r}"
        ) from e
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(None)
    return parsed.replace(tzinfo=None)


def _parse_attacker(payload: Mapping[str, Any]) -> Tuple[str, str]:
    """The attacker's canonical (ip, entity_key) from the contract's key.

    The wire contract names the attacker ``ip:<address>``; the address must
    parse, because every consumer downstream (IOC row, entity key,
    enrichment loop) joins on it.
    """
    raw = payload.get("attacker_entity_key") or ""
    if not isinstance(raw, str) or not raw.startswith("ip:"):
        raise ValueError(
            f"decoy session event has a malformed attacker_entity_key: {raw!r}"
        )
    attacker_ip = raw[len("ip:") :].strip()
    try:
        attacker_ip = str(ip_address(attacker_ip))
    except ValueError as e:
        raise ValueError(
            f"decoy session event has an unparseable attacker address: {raw!r}"
        ) from e
    return attacker_ip, entity_key("ip", attacker_ip)


def _require_str_list(value: Any, what: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"decoy session event has a malformed {what}")
    return list(value)


def _require_dict_list(value: Any, what: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"decoy session event has a malformed {what}")
    return list(value)


def parse_session_event(payload: Mapping[str, Any]) -> DecoySessionEvent:
    """Validate one decoy session event against the wire contract.

    Raises ``ValueError`` on anything malformed — the webhook's 400 path,
    never a silent coercion: a session captured wrong is worse than a
    session refused.
    """
    source = payload.get("data_source")
    if source != DECOY_SESSION_DATA_SOURCE:
        raise ValueError(f"not a decoy session event: data_source={source!r}")

    session_id = payload.get("finding_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("decoy session event has no finding_id (the session id)")
    session_id = session_id.strip()
    if len(session_id) > _FINDING_ID_MAX:
        raise ValueError(
            f"decoy session id exceeds the {_FINDING_ID_MAX}-char finding_id column"
        )

    attacker_ip, attacker_key = _parse_attacker(payload)
    routing_action_id = payload.get("routing_action_id")
    if routing_action_id is not None and not isinstance(routing_action_id, str):
        raise ValueError("decoy session event has a malformed routing_action_id")

    raw = payload.get("raw")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("decoy session event has a malformed raw payload")

    auth_attempts = _require_dict_list(payload.get("auth_attempts"), "auth_attempts")
    commands = _require_str_list(payload.get("commands"), "commands")
    files_dropped = _require_dict_list(payload.get("files_dropped"), "files_dropped")
    mitre_techniques = _require_str_list(
        payload.get("mitre_techniques"), "mitre_techniques"
    )

    return DecoySessionEvent(
        session_id=session_id,
        decoy_service=str(payload.get("decoy_service") or "unknown"),
        attacker_ip=attacker_ip,
        attacker_entity_key=attacker_key,
        session_start=_iso(payload.get("session_start"), "session_start"),
        session_end=_iso(payload.get("session_end"), "session_end"),
        routing_action_id=routing_action_id,
        auth_attempts=auth_attempts,
        commands=commands,
        files_dropped=files_dropped,
        mitre_techniques=mitre_techniques,
        raw=raw,
        auth_successes=sum(
            1
            for attempt in auth_attempts
            if attempt.get("result") == "success"  # canary success: the attacker is in
        ),
    )


def mitre_predictions_from_techniques(
    techniques: List[str],
) -> Dict[str, float]:
    """The canonical ``{technique_id: confidence}`` from the session's tags.

    Each candidate is normalized through the shared ATT&CK vocabulary
    (``resolve_technique``) rather than a decoy-local mapping: a tag the
    vocabulary cannot shape is dropped, and the same tag always yields the
    same prediction.
    """
    predictions: Dict[str, float] = {}
    for candidate in techniques or []:
        if not isinstance(candidate, str):
            continue
        tid = candidate.strip().upper()
        if not _TECHNIQUE_ID_RE.match(tid):
            continue
        resolved, _, _ = resolve_technique(tid)
        predictions.setdefault(resolved, _OBSERVED_CONFIDENCE)
    return predictions


def mitre_names_from_techniques(techniques: List[str]) -> Dict[str, str]:
    """Technique id → name via the shared vocabulary, for the transcript."""
    names: Dict[str, str] = {}
    for tid in mitre_predictions_from_techniques(techniques):
        _, name, _ = resolve_technique(tid)
        names[tid] = name
    return names


def iocs_from_event(event: DecoySessionEvent) -> List[Tuple[str, str]]:
    """The (ioc_type, value) pairs the session observed, deduped in order.

    Types are ``ENTITY_KEY_TYPES`` members on purpose — the case distiller
    mints the case's entity keys from exactly these rows at close time.
    """
    pairs: List[Tuple[str, str]] = [("ip", event.attacker_ip)]
    for dropped in event.files_dropped:
        sha256 = dropped.get("sha256")
        if isinstance(sha256, str) and sha256.strip():
            pairs.append(("hash", sha256.strip()))
    seen: set = set()
    deduped: List[Tuple[str, str]] = []
    for ioc_type, value in pairs:
        if (ioc_type, value) in seen:
            continue
        seen.add((ioc_type, value))
        deduped.append((ioc_type, value))
    return deduped


def entity_keys_for_iocs(iocs: List[Tuple[str, str]]) -> List[str]:
    """Canonical entity keys for the session's IOCs, in first-seen order."""
    keys: List[str] = []
    seen: set = set()
    for ioc_type, value in iocs:
        key = entity_key(ioc_type, value)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _severity_for(event: DecoySessionEvent) -> str:
    """A canary success means the attacker believes they are in."""
    return "high" if event.auth_successes else "medium"


def _description_for(event: DecoySessionEvent) -> str:
    """Counts only — the transcript lives in the evidence, never in the
    finding's description, and never in a log line."""
    minutes = max(
        0, int((event.session_end - event.session_start).total_seconds() // 60)
    )
    return (
        f"Attacker {event.attacker_entity_key} spent ~{minutes}m on decoy "
        f"{event.decoy_service}: {len(event.auth_attempts)} auth attempts, "
        f"{len(event.commands)} commands, {len(event.files_dropped)} files dropped."
    )


def _ensure_standing_case(session: Session) -> Case:
    """The one case all decoy sessions land on, created on first capture."""
    case = session.get(Case, DECOY_INTEL_CASE_ID)
    if case is not None:
        return case
    now = utcnow()
    case = Case(
        case_id=DECOY_INTEL_CASE_ID,
        title=DECOY_INTEL_CASE_TITLE,
        description=(
            "Evidence and IOCs captured from decoy sessions (MTD capture plane). "
            "One row per session transcript; the Findings carry the ATT&CK "
            "predictions and dedupe on the session id."
        ),
        status="new",
        priority="medium",
        tags=["decoy", "mtd"],
        timeline=[
            {
                "timestamp": now.isoformat() + "Z",
                "event": "Standing decoy-intel case created by the capture pipeline",
            }
        ],
    )
    session.add(case)
    session.flush()
    return case


def _ensure_ioc(
    session: Session,
    case_id: str,
    ioc_type: str,
    value: str,
    entity_key_value: str,
    observed_at: datetime,
    session_id: str,
) -> bool:
    """Insert or refresh one decoy IOC row; True when a row was added."""
    existing = (
        session.query(CaseIOC)
        .filter(
            CaseIOC.case_id == case_id,
            CaseIOC.ioc_type == ioc_type,
            CaseIOC.value == value,
        )
        .first()
    )
    if existing is not None:
        existing.last_seen = observed_at
        merged = dict(existing.enrichment_data or {})
        sessions = list(merged.get("decoy_sessions") or [])
        sessions.append(session_id)
        merged["decoy_sessions"] = sessions[-10:]
        merged["entity_key"] = entity_key_value
        existing.enrichment_data = merged
        return False

    session.add(
        CaseIOC(
            case_id=case_id,
            ioc_type=ioc_type,
            value=value,
            # The attacker engaged a decoy — hostile by definition. A dropped
            # file is observed payload of unknown provenance.
            threat_level="high" if ioc_type == "ip" else "medium",
            confidence=0.9 if ioc_type == "ip" else 0.8,
            source=DECOY_IOC_SOURCE,
            first_seen=observed_at,
            last_seen=observed_at,
            enrichment_data={
                "decoy_sessions": [session_id],
                "entity_key": entity_key_value,
                "observed_at": observed_at.isoformat(),
            },
            tags=["decoy"],
            is_active=True,
            is_false_positive=False,
        )
    )
    return True


def capture_session_event(
    event: DecoySessionEvent, session: Optional[Session] = None
) -> Dict[str, Any]:
    """Write one decoy session's capture atomically.

    Exactly one Finding (``data_source="vigil-decoy"``, ``external_id`` =
    the session id — the existing unique pair dedupes a replayed event for
    free), one ``CaseEvidence`` transcript, and the session's IOC rows, all
    in one transaction. A replay returns ``{"status": "duplicate"}`` without
    writing.

    Transaction ownership follows the unit_of_work contract: without a
    session the capture commits (the daemon path); with a caller's session
    it joins that transaction and the caller commits — a failure leaves the
    caller's transaction rolled back to a clean state either way.

    The IntegrityError handler covers the concurrent-replay race when the
    caller's transaction can see the winner (duplicate), and re-raises
    anything else: on the daemon path a race conflict surfaces as a store
    failure whose retry then dedupes on the unique pair — never fabricated
    success.
    """
    try:
        with unit_of_work(session) as s:
            existing = s.get(Finding, event.session_id)
            if existing is not None:
                # The common replay path: already captured, nothing to do.
                return {"status": "duplicate", "finding_id": event.session_id}

            case = _ensure_standing_case(s)
            now = utcnow()

            predictions = mitre_predictions_from_techniques(event.mitre_techniques)
            finding = Finding(
                finding_id=event.session_id,
                external_id=event.session_id,
                data_source=DECOY_SESSION_DATA_SOURCE,
                title=f"Decoy session on {event.decoy_service}",
                description=_description_for(event),
                severity=_severity_for(event),
                # No model scored this session — an absent score is the
                # honest value, and it keeps the response bands inert.
                anomaly_score=None,
                timestamp=event.session_start,
                entity_context={
                    "src_ip": event.attacker_ip,
                    "src_ips": [event.attacker_ip],
                    "entity_keys": entity_keys_for_iocs(iocs_from_event(event)),
                    "decoy_service": event.decoy_service,
                },
                source_metadata={
                    "decoy_service": event.decoy_service,
                    "attacker_entity_key": event.attacker_entity_key,
                    "session_start": event.session_start.isoformat() + "Z",
                    "session_end": event.session_end.isoformat() + "Z",
                    "routing_action_id": event.routing_action_id,
                },
            )
            for technique_id, confidence in predictions.items():
                finding.mitre_prediction_rows.append(
                    FindingMitrePrediction(
                        technique_id=technique_id, confidence=confidence
                    )
                )
            s.add(finding)
            case.findings.append(finding)

            evidence = CaseEvidence(
                case_id=case.case_id,
                evidence_type=DECOY_EVIDENCE_TYPE,
                name=f"decoy {event.decoy_service} session {event.session_id}",
                description=_description_for(event),
                source=DECOY_SESSION_DATA_SOURCE,
                collected_by=DECOY_CAPTURE_COLLECTED_BY,
                collected_at=now,
                chain_of_custody=[
                    {
                        "timestamp": now.isoformat(),
                        "action": "collected",
                        "user": DECOY_CAPTURE_COLLECTED_BY,
                        "notes": (
                            f"Decoy session {event.session_id} received from the "
                            "decoy session event stream"
                        ),
                    }
                ],
                analysis_results={
                    "decoy_service": event.decoy_service,
                    "attacker_entity_key": event.attacker_entity_key,
                    "session_start": event.session_start.isoformat() + "Z",
                    "session_end": event.session_end.isoformat() + "Z",
                    "routing_action_id": event.routing_action_id,
                    "auth_attempts": event.auth_attempts,
                    "commands": event.commands,
                    "files_dropped": event.files_dropped,
                    "mitre_techniques": event.mitre_techniques,
                    "mitre_names": mitre_names_from_techniques(event.mitre_techniques),
                    "raw": event.raw,
                },
                tags=["decoy", DECOY_EVIDENCE_TYPE],
            )
            s.add(evidence)

            iocs_added = 0
            for ioc_type, value in iocs_from_event(event):
                if _ensure_ioc(
                    session=s,
                    case_id=case.case_id,
                    ioc_type=ioc_type,
                    value=value,
                    entity_key_value=entity_key(ioc_type, value),
                    observed_at=event.session_end,
                    session_id=event.session_id,
                ):
                    iocs_added += 1

            # The standing case's technique union: what an analyst skims.
            techniques = set(case.mitre_techniques or []) | set(predictions)
            case.mitre_techniques = sorted(techniques)

            return {
                "status": "created",
                "finding_id": event.session_id,
                "case_id": case.case_id,
                "evidence_id": evidence.evidence_id,
                "iocs_added": iocs_added,
            }
    except IntegrityError:
        # A concurrent capture of the same replayed event won the race (or
        # the pre-check missed it): the winner owns the rows. Roll back to a
        # clean transaction and report the honest outcome — unless the
        # conflict is something else, which is a real failure, not dedupe.
        if session is not None:
            session.rollback()
            if session.get(Finding, event.session_id) is not None:
                return {"status": "duplicate", "finding_id": event.session_id}
        raise

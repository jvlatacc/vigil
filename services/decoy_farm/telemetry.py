"""Normalize decoy session logs into Vigil finding payloads.

Pure functions only — no I/O, no environment reads, no clock. The shipper
(see shipper.py) applies them to each tail line and posts the result to
Vigil's generic ingest webhook, so decoy sessions become ordinary findings:
triage and enrichment run on them exactly as they do for any other source
(spec AC10).

Formats consumed, one JSON object per line:

- Cowrie (SSH/Telnet): ``output_jsonlog`` events — ``eventid``/``src_ip``/
  ``timestamp``/``message``. That output plugin ships enabled by default
  upstream, writing ``cowrie.json``.
- OpenCanary (SMB/HTTP): alert JSON from ``CanaryLogger.log`` — ``logtype``
  (int), ``logdata``, ``src_host``, ``src_port``, ``dst_host``, ``dst_port``,
  ``node_id``, ``local_time``.
- HTTP decoy (this repo): request events from services/decoy_farm/http_decoy.py.

Parsing is deliberately lenient. An unparseable line or an unknown eventid is
skipped (the caller counts it) rather than raised: a decoy's log is untrusted
input, and one bad line must not cost the rest of the batch.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Optional

DATA_SOURCE = "decoy-farm"
DECOY_SEVERITY = "high"

# eventid -> (technique, confidence). Kept small and defensible: a decoy
# session maps to the technique that interaction most directly is.
_COWRIE_TECHNIQUES: Dict[str, tuple] = {
    "cowrie.session.connect": ("T1595.001", 0.7),
    "cowrie.login.success": ("T1021.004", 0.95),
    "cowrie.login.failed": ("T1021.004", 0.9),
    "cowrie.command.input": ("T1059.004", 0.8),
    "cowrie.session.file_download": ("T1105", 0.8),
}

_COWRIE_TITLES: Dict[str, str] = {
    "cowrie.session.connect": "connection opened",
    "cowrie.login.failed": "login failed",
    "cowrie.login.success": "login succeeded",
    "cowrie.command.input": "command entered",
    "cowrie.session.file_download": "payload downloaded",
    "cowrie.session.closed": "session closed",
}

# OpenCanary logtype integers, verified from the opencanary 0.9.10 wheel
# (opencanary/logger.py): LOG_HTTP_GET, LOG_HTTP_POST_LOGIN_ATTEMPT,
# LOG_SMB_FILE_OPEN.
_OPENCANARY_TECHNIQUES: Dict[int, tuple] = {
    5000: ("T1021.002", 0.9),  # LOG_SMB_FILE_OPEN
    3001: ("T1110.001", 0.8),  # LOG_HTTP_POST_LOGIN_ATTEMPT
    3000: ("T1595.002", 0.7),  # LOG_HTTP_GET
}

_OPENCANARY_TITLES: Dict[int, str] = {
    5000: "SMB file open",
    3001: "HTTP login attempt",
    3000: "HTTP probe",
}

FALLBACK_HTTP_DECOY_NAME = "fileportal-01"


def finding_id_for(farm_id: str, kind: str, raw_line: str) -> str:
    """Content-addressed and stable: reposting an event cannot double-ingest.

    Vigil dedups by ``finding_id``; a crash between read and POST, or an
    operator replaying a log file, therefore re-derives the same id.
    """
    digest = hashlib.sha256(f"{farm_id}|{kind}|{raw_line}".encode()).hexdigest()
    return f"decoy-{kind}-{digest[:16]}"


def _pick(record: Dict[str, Any], *keys: str) -> str:
    """First non-empty value among keys, as a string. '' when absent."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _as_score_map(mapped: Optional[tuple]) -> Dict[str, float]:
    if not mapped:
        return {}
    technique, confidence = mapped
    return {technique: float(confidence)}


def _payload(
    *,
    kind: str,
    farm_id: str,
    raw_line: str,
    timestamp: str,
    title: str,
    description: str,
    entity_context: Dict[str, Any],
    mitre: Dict[str, float],
) -> Dict[str, Any]:
    return {
        "finding_id": finding_id_for(farm_id, kind, raw_line),
        "data_source": DATA_SOURCE,
        "title": title,
        "description": description,
        "severity": DECOY_SEVERITY,
        "status": "new",
        "timestamp": timestamp,
        "entity_context": entity_context,
        "mitre_predictions": mitre,
    }


def cowrie_finding(
    record: Dict[str, Any], *, farm_id: str, raw_line: str, fallback_ts: str
) -> Dict[str, Any]:
    """One cowrie.json event -> a shell-decoy finding payload."""
    eventid = _pick(record, "eventid")
    mapped = _COWRIE_TECHNIQUES.get(eventid)
    src_ip = _pick(record, "src_ip", "source_ip")
    username = _pick(record, "username", "user")
    password = _pick(record, "password")
    message = _pick(record, "message")
    session = _pick(record, "session")

    label = _COWRIE_TITLES.get(eventid, eventid or "session event")
    description = message or "Decoy shell session event."
    if username:
        creds = f"{username}" + (f" / {password}" if password else "")
        description += f" (login attempted: {creds})"
    if not src_ip:
        description += " [no source address in the event]"

    entity_context: Dict[str, Any] = {
        "decoy": "cowrie",
        "event_type": eventid,
        "session": session,
    }
    if src_ip:
        entity_context["src_ip"] = src_ip

    return _payload(
        kind="cowrie",
        farm_id=farm_id,
        raw_line=raw_line,
        timestamp=_pick(record, "timestamp") or fallback_ts,
        title=f"Decoy SSH/Telnet: {label}",
        description=description,
        entity_context=entity_context,
        mitre=_as_score_map(mapped),
    )


def opencanary_finding(
    record: Dict[str, Any], *, farm_id: str, raw_line: str, fallback_ts: str
) -> Dict[str, Any]:
    """One OpenCanary alert -> a low-interaction-decoy finding payload."""
    raw_logtype = record.get("logtype")
    if raw_logtype is None:
        logtype = 0
    else:
        try:
            logtype = int(raw_logtype)
        except ValueError:
            logtype = 0
    logdata = record.get("logdata") if isinstance(record.get("logdata"), dict) else {}
    mapped = _OPENCANARY_TECHNIQUES.get(logtype)

    src_ip = _pick(record, "src_host", "src_ip")
    dst_ip = _pick(record, "dst_host")
    dst_port = _pick(record, "dst_port")
    node = _pick(record, "node_id") or "opencanary"
    label = _OPENCANARY_TITLES.get(logtype, f"logtype {logtype or 'unknown'}")

    entity_context: Dict[str, Any] = {
        "decoy": "opencanary",
        "node_id": node,
        "logtype": logtype,
    }
    if src_ip:
        entity_context["src_ip"] = src_ip
    if dst_ip:
        entity_context["dst_ip"] = dst_ip
    if dst_port:
        entity_context["dst_port"] = dst_port

    description = "Low-interaction decoy interaction."
    if logdata:
        description = json.dumps(logdata, sort_keys=True)
    if not src_ip:
        description += " [no source address in the alert]"

    return _payload(
        kind="opencanary",
        farm_id=farm_id,
        raw_line=raw_line,
        timestamp=_pick(record, "local_time", "timestamp", "time") or fallback_ts,
        title=f"Decoy SMB/HTTP: {label}",
        description=description,
        entity_context=entity_context,
        mitre=_as_score_map(mapped),
    )


def http_decoy_finding(
    record: Dict[str, Any], *, farm_id: str, raw_line: str, fallback_ts: str
) -> Dict[str, Any]:
    """One http_decoy.py request event -> an app-decoy finding payload."""
    method = _pick(record, "method") or "GET"
    path = _pick(record, "path") or "/"
    src_ip = _pick(record, "src_ip")
    decoy = _pick(record, "decoy") or FALLBACK_HTTP_DECOY_NAME
    user_agent = _pick(record, "user_agent")
    username = _pick(record, "username")

    mapped: Optional[tuple] = ("T1595.002", 0.7)  # probing the fake app
    if method == "POST" and "login" in path:
        mapped = ("T1110.001", 0.8)  # credential attempts on the fake portal

    description = f"{method} {path}"
    if user_agent:
        description += f" (user-agent: {user_agent})"
    if username:
        description += f" (login attempted: {username})"
    if not src_ip:
        description += " [no source address in the event]"

    entity_context: Dict[str, Any] = {"decoy": decoy, "method": method, "path": path}
    if src_ip:
        entity_context["src_ip"] = src_ip

    return _payload(
        kind="http-decoy",
        farm_id=farm_id,
        raw_line=raw_line,
        timestamp=_pick(record, "ts", "timestamp", "time") or fallback_ts,
        title=f"Decoy HTTP: {method} {path}",
        description=description,
        entity_context=entity_context,
        mitre=_as_score_map(mapped),
    )


Builder = Callable[..., Optional[Dict[str, Any]]]

_BUILDERS: Dict[str, Builder] = {
    "cowrie": cowrie_finding,
    "opencanary": opencanary_finding,
    "http-decoy": http_decoy_finding,
}


def build_finding(
    kind: str, raw_line: str, *, farm_id: str, fallback_ts: str
) -> Optional[Dict[str, Any]]:
    """One tail line -> one finding payload dict. None when the line is unusable."""
    builder = _BUILDERS.get(kind)
    if builder is None:
        return None
    try:
        record = json.loads(raw_line)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    return builder(record, farm_id=farm_id, raw_line=raw_line, fallback_ts=fallback_ts)

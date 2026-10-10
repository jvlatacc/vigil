"""Decoy session capture and the webhook event contract.

One session (one SSH connection; one HTTP client window) becomes one event
POSTed to the daemon's webhook ingest. The payload shape is the spec's JSON
contract — ``decoy_service``, ``attacker_entity_key``, ``session_start``,
``session_end``, ``routing_action_id`` (nullable), ``auth_attempts``,
``commands``, ``files_dropped``, ``mitre_techniques``, ``raw`` — plus the two
keys the ingest path needs to attribute and dedupe it (``finding_id`` pinned
to the session id, ``data_source`` set so the daemon can tell decoy traffic
from other webhook pushes).

The ATT&CK mapping here is deliberately small and static: it tags what the
decoy observed (brute force, a shell, discovery commands, valid-account
success). Richer mapping belongs to the capture/intel plane, which reads
these payloads.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# The data source stamped on decoy findings, per the spec's capture plane
# ("one Finding per decoy session, data_source='vigil-decoy'").
DATA_SOURCE = "vigil-decoy"

# Credential tags used in auth_attempts — "canary" marks a canary success or
# canary credential being tried; "rejected" marks a non-canary attempt.
CREDENTIAL_CANARY = "canary"
CREDENTIAL_REJECTED = "rejected"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AuthAttempt:
    user: str
    result: str  # "success" | "failure"
    credential: str  # CREDENTIAL_CANARY | CREDENTIAL_REJECTED

    def to_dict(self) -> Dict[str, str]:
        return {"user": self.user, "result": self.result, "credential": self.credential}


@dataclass
class DroppedFile:
    name: str
    sha256: str
    source: str  # "simulated-download" | "request-body"
    simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "source": self.source,
            "simulated": self.simulated,
        }


# Ordered discovery table: the decoy tags only what it can actually see.
# A map grows by adding rows, not branches.
_DISCOVERY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bwhoami\b|\bid\b", "T1033"),  # System Owner/User Discovery
    (
        r"\buname\b|\bhostname\b|\bps\b|\blsblk\b",
        "T1082",
    ),  # System Information Discovery
    (
        r"\bcat\b\s+/etc/(passwd|shadow)\b",
        "T1087",
    ),  # Account Discovery
    (
        r"\bip\s+(a|addr)|\bifconfig\b|\bnetstat\b|\bss\s+-",
        "T1016",
    ),  # System Network Config
    (r"\bping\b|\bnmap\b|\bnc\b", "T1018"),  # Remote System Discovery
    (r"\bls\b|\bfind\b|\bdir\b", "T1083"),  # File and Directory Discovery
    (
        r"\bcrontab\b|\bchmod\b|\bchown\b|\buseradd\b",
        "T1053",
    ),  # Scheduled Task (coarse)
)


def mitre_from_activity(
    auth_attempts: List[AuthAttempt], commands: List[str]
) -> List[str]:
    """Map observed decoy activity to ATT&CK technique ids. Pure and ordered:
    the same activity always yields the same list, so tests and analysts can
    rely on it."""
    techniques: List[str] = []
    if any(c.result == "success" for c in auth_attempts):
        techniques.append("T1078")  # Valid Accounts
    failures = sum(1 for c in auth_attempts if c.result == "failure")
    if failures >= 3:
        techniques.append("T1110.001")  # Password Guessing
    if commands:
        techniques.append("T1059.004")  # Unix Shell
        joined = "\n".join(commands)
        for pattern, technique in _DISCOVERY_PATTERNS:
            if re.search(pattern, joined) and technique not in techniques:
                techniques.append(technique)
    return techniques


class DecoySession:
    """Accumulates one attacker session's activity and renders it to the
    wire contract. Recording never raises — a capture bug must not become a
    decoy crash (the error-resilience invariant)."""

    def __init__(
        self,
        decoy_service: str,
        attacker_ip: str,
        ttl_seconds: int,
        routing_action_id: Optional[str] = None,
        started: Optional[datetime] = None,
    ):
        self.session_id = f"decoy-{uuid.uuid4().hex[:16]}"
        self.decoy_service = decoy_service
        self.attacker_ip = attacker_ip
        self.ttl_seconds = ttl_seconds
        self.routing_action_id = routing_action_id
        self.started = started or datetime.now(timezone.utc)
        self.last_activity = self.started
        self.auth_attempts: List[AuthAttempt] = []
        self.commands: List[str] = []
        self.files_dropped: List[DroppedFile] = []
        self.raw: Dict[str, Any] = {}

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def expired(self, now: Optional[datetime] = None) -> bool:
        """A session is over at its TTL, or after five idle minutes — an
        abandoned HTTP client window must not hold its capture forever."""
        now = now or datetime.now(timezone.utc)
        age = (now - self.started).total_seconds()
        idle = (now - self.last_activity).total_seconds()
        return age >= self.ttl_seconds or idle >= 300

    def record_auth(self, user: str, success: bool, credential: str) -> None:
        self.touch()
        self.auth_attempts.append(
            AuthAttempt(
                user=user,
                result="success" if success else "failure",
                credential=credential,
            )
        )

    def record_command(self, command: str) -> None:
        self.touch()
        # Bound what one session can accumulate — a flood is data, not a
        # lever against the decoy's memory.
        if len(self.commands) < 5000:
            self.commands.append(command)

    def record_file(self, dropped: DroppedFile) -> None:
        self.touch()
        if len(self.files_dropped) < 1000:
            self.files_dropped.append(dropped)

    def build_payload(self, ended: Optional[datetime] = None) -> Dict[str, Any]:
        """Render the spec's event contract. Pure over recorded state: same
        session, same payload."""
        ended = ended or datetime.now(timezone.utc)
        return {
            "finding_id": self.session_id,
            "data_source": DATA_SOURCE,
            "decoy_service": self.decoy_service,
            "attacker_entity_key": f"ip:{self.attacker_ip}",
            "session_start": _iso(self.started),
            "session_end": _iso(ended),
            "routing_action_id": self.routing_action_id,
            "auth_attempts": [c.to_dict() for c in self.auth_attempts],
            "commands": list(self.commands),
            "files_dropped": [f.to_dict() for f in self.files_dropped],
            "mitre_techniques": mitre_from_activity(self.auth_attempts, self.commands),
            "raw": dict(self.raw),
        }

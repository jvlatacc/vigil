"""Decoy service configuration.

Every knob flows through ``core.config`` (the no-raw-env ratchet); canary
credentials and the ingest bearer flow through ``core.secrets`` and are
resolved in ``canary.py`` / ``emitter.py``, never here — a config object can
be logged or dumped, a credential cannot.
"""

from dataclasses import dataclass
from typing import Optional

from core.config import Settings, get_settings

# Implementation constants, not operator knobs: the ports are part of the
# compose / Helm wiring (Services and NetworkPolicies name them), and the
# canary username set is part of the decoy's plausibility design — brute-force
# tooling cycles through exactly these first.
SSH_PORT = 2222
HTTP_PORT = 8080

# Usernames the SSH decoy authenticates with the canary password. Any username
# is recorded; these are the ones decoy artifacts (fake passwd, motd) mention,
# so an attacker who reads first then logs in as what they saw stays engaged.
CANARY_USERNAMES = ("root", "ubuntu", "admin", "deploy", "service")

# Embedded in every canary value the decoy generates and every credential
# artifact it serves, so a canary that escapes into a production alert,
# breach dump, or credential-stuffing list is identifiable as fake on sight.
CANARY_MARKER = "vigil-canary"


@dataclass(frozen=True)
class DecoyConfig:
    """Runtime configuration for one decoy process.

    ``enabled`` is the in-code master switch: the compose profile / Helm
    values decide whether the process is started, and this decides whether a
    started process serves. Both gates default off — enabling MTD is a human
    configuration act (spec, Locked).
    """

    enabled: bool = False
    # Where session events are POSTed. Empty means emission is disabled: the
    # decoy still runs and captures (its stats say so), it just cannot hand
    # anything to the daemon.
    ingest_url: str = ""
    # Maximum session length; long sessions are closed and emitted at the TTL
    # so a held-open session cannot defer its capture indefinitely.
    session_ttl_seconds: int = 3600
    emit_timeout_seconds: float = 10.0

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DecoyConfig":
        s = settings or get_settings()
        return cls(
            enabled=s.decoy_enabled,
            ingest_url=s.decoy_ingest_url,
            session_ttl_seconds=s.decoy_session_ttl_seconds,
        )

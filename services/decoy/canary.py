"""Canary credentials — the only credentials any decoy will ever hold.

Design (spec plane 03, Locked: "canary-only credentials"):
- A canary always authenticates. The attacker's tooling keeps cycling
  (a lockout would end the session), and every success is captured.
- A canary is marked so a leak is identifiable as fake: generated values
  embed ``vigil-canary`` by construction, and a configured value that lacks
  the marker is logged loudly at startup.
- When no canary is configured through the secret plumbing, each decoy
  generates an ephemeral one for its own lifetime — sessions keep working,
  and nothing durable or shared exists to leak.
"""

import hmac
import logging
import secrets as _secrets
from typing import Optional

from core.secrets import get_secret
from services.decoy.config import CANARY_MARKER

logger = logging.getLogger(__name__)

# Read through the secret plumbing (env fallback included), like the daemon's
# webhook token — never a Settings field, so it cannot leak via config dumps.
CANARY_SECRET_KEY = "DECOY_CANARY_PASSWORD"


class CanaryCredentials:
    """The credential pair a decoy accepts. Deliberately not a Settings
    field: the only operation anyone needs is the match."""

    def __init__(self, password: str, ephemeral: bool):
        self._password = password
        self.ephemeral = ephemeral

    def matches(self, presented: str) -> bool:
        """Constant-time compare — a decoy is a timing oracle for nothing."""
        return hmac.compare_digest(
            presented.encode("utf-8"), self._password.encode("utf-8")
        )

    @property
    def marked(self) -> str:
        """The exact string planted in fake credential files and emitted
        payloads. Ephemeral values carry the marker by construction; a
        configured value is the operator's own string."""
        if self.ephemeral:
            return f"{CANARY_MARKER}:{self._password}"
        return self._password

    @property
    def value(self) -> str:
        """The credential the decoy accepts. For the auth path and tests —
        never logged, never planted, never emitted."""
        return self._password


def resolve_canary(configured: Optional[str] = None) -> CanaryCredentials:
    """Resolve the canary from the secret plumbing, or generate an ephemeral
    one. ``configured`` is injectable for tests; production callers omit it
    and the value comes from ``get_secret`` (env fallback included)."""
    value = configured if configured is not None else get_secret(CANARY_SECRET_KEY)
    if value:
        if CANARY_MARKER not in value:
            logger.warning(
                "Configured %s does not contain the marker %r — a leak of this "
                "credential will not be identifiable as a decoy value",
                CANARY_SECRET_KEY,
                CANARY_MARKER,
            )
        return CanaryCredentials(password=value, ephemeral=False)
    generated = f"{CANARY_MARKER}-{_secrets.token_hex(16)}"
    return CanaryCredentials(password=generated, ephemeral=True)

"""One-time state for the authorization-code dance.

A federated sign-in spans two requests: the redirect out to the IdP and
the callback back. Between them Vigil must remember — for one attempt
only — the ``state``, the ``nonce``, the PKCE verifier and the redirect
URI it sent. The store is deliberately single-use and short-lived: a
replayed ``state`` finds nothing, an expired attempt finds nothing, and a
deployment without Redis holds no state at all, so no federated sign-in
can start (fail closed — the same posture token revocation takes).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from core.auth.federation.errors import OidcUnavailableError
from core.redis_client import get_async_redis

logger = logging.getLogger(__name__)

#: How long an attempted sign-in may sit between redirect and callback.
#: Ten minutes covers a slow human; the IdP's own code lifetime is usually
#: shorter, and it enforces its half independently.
STATE_TTL_SECONDS = 600

_KEY_PREFIX = "vigil:oidc:login:"


@dataclass(frozen=True)
class PendingLogin:
    """What must survive between the redirect out and the callback back."""

    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str


class OidcStateStore(Protocol):
    async def put(self, pending: PendingLogin) -> None:
        """Persist one attempted sign-in for ``STATE_TTL_SECONDS``."""
        ...

    async def pop(self, state: str) -> PendingLogin | None:
        """Remove and return the attempt named ``state``, or None.

        Removal is the point: a second callback carrying the same state
        finds nothing, which is what makes replay a dead end.
        """
        ...


class RedisStateStore:
    """The Redis-backed store. Every failure mode is a refusal."""

    def __init__(self, ttl_seconds: int = STATE_TTL_SECONDS):
        self._ttl = ttl_seconds

    async def put(self, pending: PendingLogin) -> None:
        client = self._client("write")
        try:
            await client.set(
                _KEY_PREFIX + pending.state,
                json.dumps(
                    {
                        "nonce": pending.nonce,
                        "code_verifier": pending.code_verifier,
                        "redirect_uri": pending.redirect_uri,
                    }
                ),
                ex=self._ttl,
            )
        except Exception as exc:
            raise OidcUnavailableError(
                f"could not store OIDC login state: {exc}"
            ) from exc

    async def pop(self, state: str) -> PendingLogin | None:
        client = self._client("read")
        try:
            # GETDEL is one round trip and one mutation: the attempt is
            # consumed whether or not what follows succeeds.
            raw = await client.getdel(_KEY_PREFIX + state)
        except Exception as exc:
            raise OidcUnavailableError(
                f"could not read OIDC login state: {exc}"
            ) from exc
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return PendingLogin(
                state=state,
                nonce=data["nonce"],
                code_verifier=data["code_verifier"],
                redirect_uri=data["redirect_uri"],
            )
        except (KeyError, TypeError, ValueError):
            # A value we cannot parse is worse than a missing one — it may
            # be corruption. Treat as absent and let the sign-in die.
            logger.warning("Discarding unparseable OIDC login state %s", state[:8])
            return None

    @staticmethod
    def _client(purpose: str):
        client = get_async_redis(f"OIDC state {purpose}")
        if client is None:
            raise OidcUnavailableError(
                "Redis unavailable — cannot hold OIDC login state"
            )
        return client

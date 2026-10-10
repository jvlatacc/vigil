"""Session event emitter — best-effort POST to the daemon webhook ingest.

The daemon's ingest (``services/daemon/poller.py``) requires a bearer token
and fails closed when it has none. The emitter is its client side: a failed
emission is logged and counted, never raised — a decoy must not die because
its SOC is unreachable (the error-resilience invariant). Capture continues
regardless; only the handoff is lost.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from core.secrets import get_secret

logger = logging.getLogger(__name__)

# Same channel as the daemon's own token (compose aliases DAEMON_WEBHOOK_TOKEN
# into this name; Helm sets secrets.decoyIngestToken to the same value).
INGEST_TOKEN_SECRET_KEY = "DECOY_INGEST_TOKEN"


class SessionEventEmitter:
    """Posts decoy session payloads to the daemon webhook ingest."""

    def __init__(
        self,
        ingest_url: str,
        token: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ):
        self._ingest_url = ingest_url
        self._token = (
            token if token is not None else get_secret(INGEST_TOKEN_SECRET_KEY) or ""
        )
        self._timeout_seconds = timeout_seconds
        # Counters are the decoy's honest ledger: what was handed over, and
        # what was captured but could not be.
        self.emitted = 0
        self.dropped = 0

    @property
    def enabled(self) -> bool:
        return bool(self._ingest_url)

    async def emit(self, payload: Dict[str, Any]) -> bool:
        """Deliver one session payload. Two attempts, then give up: the
        daemon's dedup set keys on ``finding_id`` (pinned to the session id),
        so a retry can never produce two findings for one session."""
        if not self.enabled:
            self.dropped += 1
            if self.dropped == 1:
                logger.warning(
                    "DECOY_INGEST_URL is not set — decoy sessions are captured "
                    "in logs but not handed to the daemon"
                )
            return False

        last_error: Optional[str] = None
        for attempt in (1, 2):
            try:
                timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self._ingest_url,
                        json=payload,
                        headers={"Authorization": f"Bearer {self._token}"},
                    ) as response:
                        body = await response.text()
                        if response.status == 200:
                            self.emitted += 1
                            return True
                        last_error = f"HTTP {response.status}: {body[:200]}"
            except (
                Exception
            ) as exc:  # noqa: BLE001 — every failure is data, none is fatal
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                await asyncio.sleep(2)
        self.dropped += 1
        logger.error(
            "Could not hand decoy session %s to the daemon ingest: %s",
            payload.get("finding_id", "<no id>"),
            last_error,
        )
        return False

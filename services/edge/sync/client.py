"""The authenticated sync client: one place owns the wire.

Every call is one attempt — retry policy lives in the loop, which owns the
backoff schedule and the state machine. Failures are survivable by design:
a failed call never raises past the loop, and a 401 is never mistaken for a
network hiccup. 401 means the credential is wrong or the node was revoked —
and by registry design the two are indistinguishable, so either way the node
stops acting (revocation beats allowance, design spec conflict precedence).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0

_CREDENTIAL_SCHEME = "Bearer "


class SyncError(Exception):
    """A sync call failed — transport, timeout, or 5xx. Survivable."""


class UnauthorizedError(SyncError):
    """401 from a node route: bad credential or revoked node."""


class EnrollError(SyncError):
    """Enrollment refused: bad or expired token (401), a deployment with the
    enrollment secret unset (503), or a malformed node id (400)."""


class SyncSurface(Protocol):
    """What the daemon and reconciler need from a control-plane client.

    The real ``SyncClient`` and test fakes conform structurally — the
    daemon's dependencies stay swappable without any runtime indirection.
    """

    @property
    def credential(self) -> str | None: ...

    def load_credential(self) -> bool: ...

    async def enroll(self, enrollment_token: str, segment_scope: dict) -> None: ...

    async def heartbeat(
        self,
        *,
        boot_id: str,
        bundle_version: int | None,
        autonomy_tier: str,
        lease_state: str,
        acked_upto: int | None,
    ) -> dict: ...

    async def pull_policy(self, cursor: int | None) -> dict: ...

    async def post_events(self, events: list[dict]) -> dict: ...

    async def aclose(self) -> None: ...


class SyncClient:
    """Authenticated calls to ``/internal/edge/*``. One instance per daemon.

    The credential is held in memory and mirrored to ``credential_file``
    (mode 0600) so an enrolled node survives its own restart without
    re-enrolling; the one-time enrollment token is never persisted.
    """

    def __init__(
        self,
        *,
        control_url: str,
        node_id: str,
        credential_file: Path,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.node_id = node_id
        self.credential_file = Path(credential_file)
        self._base_url = control_url.rstrip("/")
        self._credential: str | None = None
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    @property
    def credential(self) -> str | None:
        return self._credential

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- credential lifecycle -------------------------------------------

    def load_credential(self) -> bool:
        """Adopt a persisted credential. False = none stored yet."""
        try:
            credential = self.credential_file.read_text().strip()
        except OSError:
            return False
        if not credential:
            return False
        self._credential = credential
        return True

    async def enroll(self, enrollment_token: str, segment_scope: dict) -> None:
        """Exchange the one-time token for a per-node credential.

        Re-enrolling rotates the credential server-side, so this overwrite
        is exactly the revocation of whatever the node held before.
        """
        response = await self._request(
            "POST",
            "/internal/edge/enroll",
            json={
                "node_id": self.node_id,
                "enrollment_token": enrollment_token,
                "segment_scope": segment_scope,
            },
            authenticate=False,
        )
        if response.status_code == 503:
            raise EnrollError("control plane has no enrollment secret configured (503)")
        if response.status_code == 401:
            raise EnrollError("enrollment token invalid, expired, or spent (401)")
        if response.status_code != 201:
            raise EnrollError(
                f"enrollment failed ({response.status_code}): {response.text[:200]}"
            )
        body = _json_of(response)
        credential = str(body.get("credential") or "")
        if not credential:
            raise EnrollError("enrollment returned no credential")
        self._credential = credential
        self._persist_credential(credential)
        logger.info(
            "enrolled node %s; credential stored at %s",
            self.node_id,
            self.credential_file,
        )

    def _persist_credential(self, credential: str) -> None:
        self.credential_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.credential_file,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(credential)

    # -- the four sync calls ---------------------------------------------

    async def pull_policy(self, cursor: int | None) -> dict:
        """Cursor-keyed bundle pull. ``cursor`` is the version the node
        already holds; a cold start passes None (server serves newest only —
        never a history backfill)."""
        params: dict[str, Any] = {} if cursor is None else {"cursor": cursor}
        response = await self._request(
            "GET", f"/internal/edge/{self.node_id}/policy", params=params
        )
        return _json_of(response)

    async def post_events(self, events: list[dict]) -> dict:
        """Upload one bounded journal batch; returns the server's durable
        result: {acked, duplicates, rejected, commit_watermark}."""
        response = await self._request(
            "POST", f"/internal/edge/{self.node_id}/events", json={"events": events}
        )
        return _json_of(response)

    async def heartbeat(
        self,
        *,
        boot_id: str,
        bundle_version: int | None,
        autonomy_tier: str,
        lease_state: str,
        acked_upto: int | None,
    ) -> dict:
        """Liveness plus the drift signal; the response carries the bundle
        version the node should adopt next and the server's commit watermark
        — the reconciliation exchange (acked_upto out, watermark back)."""
        response = await self._request(
            "POST",
            f"/internal/edge/{self.node_id}/heartbeat",
            json={
                "boot_id": boot_id,
                "bundle_version": bundle_version,
                "autonomy_tier": autonomy_tier,
                "lease_state": lease_state,
                "acked_upto": acked_upto,
            },
        )
        return _json_of(response)

    # -- transport ---------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        authenticate: bool = True,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if authenticate:
            if not self._credential:
                raise SyncError("no credential: call enroll()/load_credential() first")
            headers["Authorization"] = _CREDENTIAL_SCHEME + self._credential
        try:
            response = await self._http.request(
                method, path, json=json, params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            raise SyncError(f"{method} {path} failed: {exc}") from exc
        if response.status_code == 401 and authenticate:
            raise UnauthorizedError(f"{path} refused the node credential (401)")
        return response


def _json_of(response: httpx.Response) -> dict:
    if response.is_error:
        raise SyncError(
            f"{response.request.method} {response.request.url.path} -> "
            f"{response.status_code}: {response.text[:200]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SyncError(f"{response.request.url.path}: non-JSON body") from exc
    if not isinstance(payload, dict):
        raise SyncError(f"{response.request.url.path}: unexpected body shape")
    return payload

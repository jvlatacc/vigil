"""Cloudflare Cloudy webhook receiver (scaffolded, gated off by default).

Accepts pushed events from Cloudflare with attached Cloudy natural-language
summaries. The exact Cloudflare webhook contract is not publicly stable as
of the partnership scaffolding; everything here is conservative and gated
behind ``CLOUDY_INGESTION_ENABLED``. Flip the env var (or system_config
``cloudflare.cloudy.enabled``) on once the partnership confirms the wire
format.

Endpoints (only mounted when the flag is on):
    POST /api/webhooks/cloudflare/cloudy
    GET  /api/webhooks/cloudflare/cloudy/health

Signature header: ``X-Cloudflare-Signature`` (hex HMAC-SHA256 of raw body).
The body must carry ``timestamp`` (unix seconds) inside the signed payload;
it is accepted only within ±5 minutes of the receiver's clock, and a
verified signature is remembered past that window so the same signed body
posted twice is rejected as a replay. The cache is in-process — a
multi-replica deployment needs a shared store, and the receiver stays off
by default.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import time
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.config import get_settings
from core.routing import Auth, RouterMeta
from core.secrets import get_secret
from core.webhook_rejections import (
    BAD_SIGNATURE,
    BAD_TIMESTAMP,
    DISABLED,
    MISSING_SIGNATURE,
    NO_SECRET,
    REPLAY,
    SECRET_LOOKUP_FAILED,
    STALE_TIMESTAMP,
    record_rejection,
    rejection_counts,
)

logger = logging.getLogger(__name__)

ENDPOINT = "cloudflare/cloudy"

router = APIRouter()

# The signed-payload timestamp may sit this far from the receiver's clock.
_TIMESTAMP_SKEW_SECONDS = 300
# A verified signature is remembered a little past the skew window: any
# replay of it is stale-rejected by then anyway, so the entry is dead weight.
_REPLAY_TTL_SECONDS = _TIMESTAMP_SKEW_SECONDS + 60

# (verified signature hex) -> monotonic time of first acceptance.
_seen_signatures: Dict[str, float] = {}
_seen_lock = threading.Lock()


# Off unless explicitly enabled. system_config wins so the Settings UI can flip
# the receiver without a restart; env is the fallback.
def cloudy_ingestion_enabled() -> bool:
    try:
        from core.storage.config_service import get_config_service

        cfg = get_config_service().get_system_config("cloudflare.cloudy.enabled")
        if isinstance(cfg, dict):
            if cfg.get("enabled") is True:
                return True
            if cfg.get("enabled") is False:
                return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("system_config read for cloudflare.cloudy.enabled failed: %s", exc)
    return get_settings().cloudy_ingestion_enabled


ROUTER_META = RouterMeta(
    prefix="/api/webhooks/cloudflare",
    tags=["cloudflare"],
    auth=Auth.PUBLIC_WEBHOOK,
    reason=(
        "Inbound receiver for Cloudflare Cloudy pushes — the caller is a "
        "machine, so there is no session to authenticate. The endpoints "
        "verify an HMAC shared secret and re-check the enable flag at request "
        "time, so even a misconfigured mount fails closed."
    ),
    # Hard-off by default: the upstream API contract is not yet stable. Flip
    # CLOUDY_INGESTION_ENABLED=true (or system_config cloudflare.cloudy.enabled)
    # once the partnership confirms the wire format.
    enabled=cloudy_ingestion_enabled,
)


def _get_secret() -> Optional[str]:
    return get_secret("CLOUDY_WEBHOOK_SECRET") or None


def _get_max_body_bytes() -> int:
    return max(1, get_settings().cloudy_webhook_max_body_kb) * 1024


def _verified_signature(raw_body: bytes, provided: str, secret: str) -> Optional[str]:
    """The HMAC hex when ``provided`` matches, else None.

    The verified hex is the replay-cache key: it is canonical (an attacker
    cannot poison the cache with a differently-formatted signature) and is
    only returned for a genuine match.
    """
    expected = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    clean = provided.split("=", 1)[-1].strip()
    if hmac.compare_digest(expected, clean):
        return expected
    return None


def _seen_before(sig_hex: str, now: Optional[float] = None) -> bool:
    """True when this verified signature was already accepted.

    Entries expire just past the timestamp window — a signature older than
    that is rejected as stale before this check runs, so the cache only ever
    answers for signatures that could otherwise be ingested twice. Single
    process: multi-replica deployments need a shared cache.
    """
    now = time.monotonic() if now is None else now
    with _seen_lock:
        for key, seen_at in list(_seen_signatures.items()):
            if now - seen_at > _REPLAY_TTL_SECONDS:
                del _seen_signatures[key]
        if sig_hex in _seen_signatures:
            return True
        _seen_signatures[sig_hex] = now
        return False


def _timestamp_error(payload: Dict[str, Any]) -> Optional[str]:
    """Rejection reason for the signed payload's timestamp, or None.

    The timestamp lives inside the signed body, so a client cannot refresh it
    without re-signing — an attacker replaying a captured body cannot move it
    out of the window.
    """
    ts = payload.get("timestamp")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return BAD_TIMESTAMP
    if abs(time.time() - float(ts)) > _TIMESTAMP_SKEW_SECONDS:
        return STALE_TIMESTAMP
    return None


def _reject(
    request: Request,
    reason: str,
    status_code: int,
    detail: str,
    exc: Optional[BaseException] = None,
) -> HTTPException:
    record_rejection(
        ENDPOINT, reason, request.client.host if request.client else None, exc=exc
    )
    return HTTPException(status_code=status_code, detail=detail)


def _require_enabled(request: Request) -> None:
    if not cloudy_ingestion_enabled():
        raise _reject(
            request,
            DISABLED,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cloudy ingestion is disabled. Set CLOUDY_INGESTION_ENABLED=true to enable.",
        )


async def _read_and_verify(
    request: Request, signature: Optional[str]
) -> Tuple[bytes, str]:
    # Fetch the secret once per request: a second lookup would double-count.
    try:
        secret = _get_secret()
    except Exception as exc:  # noqa: BLE001
        raise _reject(
            request,
            SECRET_LOOKUP_FAILED,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cloudy webhook secret lookup failed",
            exc,
        )
    if not secret:
        raise _reject(
            request,
            NO_SECRET,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cloudy webhook receiver not configured (CLOUDY_WEBHOOK_SECRET missing)",
        )
    raw = await request.body()
    if len(raw) > _get_max_body_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Body exceeds {_get_max_body_bytes()} bytes",
        )
    sig_hex = _verified_signature(raw, signature, secret) if signature else None
    if not signature or sig_hex is None:
        raise _reject(
            request,
            BAD_SIGNATURE if signature else MISSING_SIGNATURE,
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing X-Cloudflare-Signature",
        )
    return raw, sig_hex


def _parse_json(raw: bytes) -> Dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid JSON body",
        )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook payload must be a JSON object",
        )
    return payload


def _ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    from core.integrations.cloudflare.ingestion import CloudyIngestionService

    service = CloudyIngestionService()
    finding = service.transform_event(payload)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to transform Cloudy event payload",
        )
    ok = service.ingestion_service.ingest_finding(finding)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Finding was not persisted",
        )
    logger.info(
        "Cloudy event ingested: finding_id=%s data_source=%s",
        finding.get("finding_id"),
        finding.get("data_source"),
    )
    return {"accepted": True, "finding_id": finding["finding_id"]}


@router.get("/cloudy/health")
async def health() -> Dict[str, Any]:
    """Liveness probe. Returns enabled-flag and secret-configured-flag."""
    try:
        secret_configured = _get_secret() is not None
    except Exception:  # noqa: BLE001
        secret_configured = False
    return {
        "status": "ok",
        "receiver": "cloudflare-cloudy",
        "enabled": cloudy_ingestion_enabled(),
        "secret_configured": secret_configured,
        "rejections": rejection_counts(ENDPOINT),
    }


@router.post("/cloudy", status_code=status.HTTP_202_ACCEPTED)
async def cloudy_event(
    request: Request,
    x_cloudflare_signature: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _require_enabled(request)
    raw, sig_hex = await _read_and_verify(request, x_cloudflare_signature)
    payload = _parse_json(raw)
    ts_error = _timestamp_error(payload)
    if ts_error == BAD_TIMESTAMP:
        raise _reject(
            request,
            BAD_TIMESTAMP,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Webhook payload must carry a numeric 'timestamp' (unix seconds) "
            "inside the signed body",
        )
    if ts_error == STALE_TIMESTAMP:
        raise _reject(
            request,
            STALE_TIMESTAMP,
            status.HTTP_401_UNAUTHORIZED,
            "Webhook timestamp is outside the accepted window (±5 minutes)",
        )
    if _seen_before(sig_hex):
        raise _reject(
            request,
            REPLAY,
            status.HTTP_401_UNAUTHORIZED,
            "Replayed webhook rejected (signature already used)",
        )
    return await asyncio.to_thread(_ingest, payload)

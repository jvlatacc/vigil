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
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.config import get_settings
from core.ingestion.webhook_origin import read_and_verify_webhook
from core.routing import Auth, RouterMeta
from core.secrets import get_secret
from core.storage.origin_trust import ORIGIN_SIGNED
from core.webhook_rejections import DISABLED, record_rejection, rejection_counts

logger = logging.getLogger(__name__)

ENDPOINT = "cloudflare/cloudy"

router = APIRouter()


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


async def _read_and_verify(request: Request, signature: Optional[str]) -> bytes:
    # The shared fail-closed ritual: secret lookup, body cap, constant-time
    # HMAC over the raw bytes, rejection telemetry on every refusal.
    return await read_and_verify_webhook(
        request,
        endpoint=ENDPOINT,
        secret_lookup=_get_secret,
        signature_header="X-Cloudflare-Signature",
        provided_signature=signature,
        max_body_bytes=_get_max_body_bytes,
    )


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
    # _read_and_verify proved the sender holds the shared secret: this row
    # is signed, and the only path here runs after it.
    finding["origin_trust"] = ORIGIN_SIGNED
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
    raw = await _read_and_verify(request, x_cloudflare_signature)
    payload = _parse_json(raw)
    return await asyncio.to_thread(_ingest, payload)

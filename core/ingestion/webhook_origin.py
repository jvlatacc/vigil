"""Shared, fail-closed verification for signed webhook receivers.

The Darktrace and Cloudflare receivers verified their payloads with the same
ritual — resolve the per-source shared secret, fail closed when it is
missing or unresolvable, cap the body, then compare an HMAC-SHA256 over the
raw bytes in constant time — differing only in the header name, the endpoint
label for rejection telemetry, and the secret lookup. This module owns that
ritual once, so the next receiver inherits it instead of a fourth copy.

What a receiver does with the verified body is its own business. What it
stamps on the finding it builds is standardized in core/response/origin.py:
a receiver that verified the signature stamps ``signed``; a receiver that
opts into accepting payloads with no configured secret stamps
``unverified`` — accepted, never trusted. (Darktrace and Cloudflare keep
failing closed when their secret is missing, as before this helper.)
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Callable, Optional

from fastapi import HTTPException, Request, status

from core.storage.origin_trust import ORIGIN_SIGNED, ORIGIN_UNVERIFIED
from core.webhook_rejections import (
    BAD_SIGNATURE,
    MISSING_SIGNATURE,
    NO_SECRET,
    SECRET_LOOKUP_FAILED,
    record_rejection,
)

# Resolves the receiver's shared secret at request time — never import time,
# so a secret saved through the UI takes effect without a restart. Raises
# when the lookup itself fails; the caller tells that apart from "not set".
SecretLookup = Callable[[], Optional[str]]


def verify_hmac_signature(
    raw_body: bytes, provided: Optional[str], secret: str
) -> bool:
    """Constant-time HMAC-SHA256 compare over the raw request bytes.

    Accepts the common ``sha256=<hex>`` prefix some vendors wrap the digest
    in; anything else must be the bare hex digest.
    """
    expected = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    clean = (provided or "").split("=", 1)[-1].strip()
    return hmac.compare_digest(expected, clean)


def origin_stamp(verified: bool) -> str:
    """The tier a receiver stamps: signed when it verified, never otherwise."""
    return ORIGIN_SIGNED if verified else ORIGIN_UNVERIFIED


async def read_and_verify_webhook(
    request: Request,
    *,
    endpoint: str,
    secret_lookup: SecretLookup,
    signature_header: str,
    provided_signature: Optional[str],
    max_body_bytes: Callable[[], int],
) -> bytes:
    """The shared fail-closed ritual: raw body or HTTPException.

    A secret lookup that raises is a 503 (the receiver is broken, not the
    caller); a missing secret is a 503 fail-closed; an oversized body a 413;
    a bad or missing signature a 401. Every refusal is recorded in the
    rejection telemetry with the caller's address before it raises. The body
    limit resolves after the secret check, so a receiver whose cap reads the
    database cannot log before the secret verdict does.
    """
    client = request.client.host if request.client else None
    try:
        secret = secret_lookup()
    except Exception as exc:  # noqa: BLE001
        record_rejection(endpoint, SECRET_LOOKUP_FAILED, client, exc=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{endpoint} webhook secret lookup failed",
        ) from exc
    if not secret:
        # Fail closed: without a configured secret we cannot authenticate.
        record_rejection(endpoint, NO_SECRET, client)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{endpoint} webhook receiver not configured",
        )
    limit = max_body_bytes()
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Body exceeds {limit} bytes",
        )
    if not provided_signature or not verify_hmac_signature(
        raw, provided_signature, secret
    ):
        record_rejection(
            endpoint,
            BAD_SIGNATURE if provided_signature else MISSING_SIGNATURE,
            client,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing {signature_header}",
        )
    return raw

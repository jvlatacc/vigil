"""Canary-credential rotation for the decoy registry (MTD plane 03).

Containment invariant from the spec: decoys hold canary credentials only,
rotated on a schedule. The daemon scheduler's ``mtd_canary_rotation`` tick
calls :func:`rotate_active_canaries`, which rotates each distinct credential
referenced by an active ``MtdDecoyRegistry`` row — a fresh, marked canary
written through the credential store at the row's ``canary_credential_ref`` —
and stamps ``rotated_at``.

Ordering is deliberate: the store write happens first, the stamp second. A
stamp failure after a successful write leaves the credential fresh and the
record lagging — the next tick re-rotates and converges. Stamping first
would record a rotation that did not happen, which is the one direction a
hygiene column must never lie in.

The generated value embeds ``CANARY_MARKER`` by construction (the same rule
``services/decoy/canary.py`` applies to its ephemeral values), so a rotated
canary that escapes is identifiable as fake. The literal is defined here —
core cannot import services — and pinned to the decoy side by
``tests/unit/decoy/test_capture_wire_contract.py``.

A running decoy resolves its canary when it starts, so a rotated credential
takes effect on the decoy's next resolve; rotation keeps the store
authoritative and the registry's history true regardless.
"""

from __future__ import annotations

import asyncio
import logging
import secrets as _secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.secrets import set_secret
from core.storage.models import MtdDecoyRegistry
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow

logger = logging.getLogger(__name__)

# The marker every generated canary carries — the leak-identification
# contract shared with the decoy plane (services/decoy/config.py, which the
# wire-contract test pins to this value).
CANARY_MARKER = "vigil-canary"

# Generated canaries: marker + 16 random bytes. Identical recipe to the
# decoy's own ephemeral values, so a rotated value is indistinguishable in
# form from any canary the decoys mint.
_CANARY_RANDOM_BYTES = 16


def generate_canary_value() -> str:
    """One fresh marked canary value."""
    return f"{CANARY_MARKER}-{_secrets.token_hex(_CANARY_RANDOM_BYTES)}"


def rotate_active_canaries(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Rotate every distinct canary credential the active registry references.

    One credential per distinct ``canary_credential_ref``: rows sharing a ref
    share a credential, so they rotate together and stamp together. Returns
    the tally for the scheduler stats; a ``set_secret`` failure counts the
    rows it would have covered and leaves their ``rotated_at`` untouched —
    a rotation that did not happen is never recorded as one.
    """
    now = now or utcnow()
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        rows: List[MtdDecoyRegistry] = (
            session.query(MtdDecoyRegistry)
            .filter(MtdDecoyRegistry.status == "active")
            .order_by(MtdDecoyRegistry.decoy_id)
            .all()
        )
        # (ref, decoy_ids) in decoy_id order — the registry's determinism.
        by_ref: Dict[str, List[str]] = {}
        for row in rows:
            by_ref.setdefault(row.canary_credential_ref, []).append(row.decoy_id)

    rotated = failed = 0
    for ref, decoy_ids in by_ref.items():
        if not set_secret(ref, generate_canary_value()):
            failed += len(decoy_ids)
            logger.error(
                "Canary rotation for %s (%d decoy(s)) could not write the "
                "credential store — rotated_at left untouched; retried next tick",
                ref,
                len(decoy_ids),
            )
            continue
        _stamp_rotated(decoy_ids, now)
        rotated += len(decoy_ids)
    return {"scanned": len(rows), "rotated": rotated, "failed": failed}


def _stamp_rotated(decoy_ids: List[str], when: datetime) -> None:
    """Stamp ``rotated_at`` on the named active rows, in one transaction."""
    with unit_of_work() as session:
        rows = (
            session.query(MtdDecoyRegistry)
            .filter(MtdDecoyRegistry.decoy_id.in_(decoy_ids))
            .all()
        )
        for row in rows:
            row.rotated_at = when


async def rotate_active_canaries_async(
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Off-thread entry point for the scheduler tick (the route-sweep shape:
    the store write and the DB stamps are sync, the event loop is not)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, rotate_active_canaries, now or utcnow())

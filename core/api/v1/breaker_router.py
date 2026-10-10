"""Containment breaker admin surface: status and audited manual reset (#944).

The breaker itself lives in ``core/response/breaker.py`` and is shared state
in Redis; this router gives operators eyes (GET) and a hand (POST reset).
The reset is written to ``config_audit_log`` like every other safety-config
change, naming the signed-in analyst who pulled the plug.

Auth posture is ``Auth.REQUIRED``: reading the breaker state needs a login;
resetting it additionally needs the ``ai_decisions.approve`` permission —
the same humans who decide containment decide when machine-speed response
comes back.
"""

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.auth.current_user import get_current_user
from core.auth.permissions import permission_gate
from core.response.breaker import BreakerStatus, ContainmentBreaker
from core.routing import Auth, RouterMeta
from core.storage.config_service import ConfigService
from core.storage.models import User

router = APIRouter()

_RESET = [permission_gate("ai_decisions.approve")]

ROUTER_META = RouterMeta(
    prefix="/api/v1/response",
    legacy_prefixes=("/api/response",),
    tags=["breaker"],
    auth=Auth.REQUIRED,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def provide_breaker(request: Request) -> ContainmentBreaker:
    """The process's breaker handle; the state is shared through Redis."""
    breaker = getattr(request.app.state, "containment_breaker", None)
    if breaker is None:
        breaker = ContainmentBreaker()
        request.app.state.containment_breaker = breaker
    return breaker


AuditWriter = Callable[[Optional[Dict[str, Any]], Dict[str, Any], str, str], None]


def provide_audit_writer(request: Request) -> AuditWriter:
    """Writes the reset to ``config_audit_log`` (overridable in tests)."""

    def write(
        old_value: Optional[Dict[str, Any]],
        new_value: Dict[str, Any],
        changed_by: str,
        change_reason: str,
    ) -> None:
        ConfigService(user_id=changed_by).record_audit(
            config_type="response",
            config_key="response.breaker",
            action="update",
            old_value=old_value,
            new_value=new_value,
            change_reason=change_reason,
        )

    return write


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BreakerStatusResponse(BaseModel):
    """Frozen shape of one breaker observation (mirrors ``BreakerStatus``)."""

    state: str  # "closed" | "open"
    reason: Optional[str] = None
    rule: Optional[str] = None
    opened_at: Optional[float] = None
    seconds_left: Optional[int] = None
    escalation_fired: bool = False
    store: str = "redis"  # "redis" | "memory"
    counters: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class BreakerResetRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        description="Why the breaker is being manually reset; recorded in"
        " the config audit log.",
    )


class BreakerResetResponse(BaseModel):
    before: BreakerStatusResponse
    after: BreakerStatusResponse
    rule: str = "response.breaker_reset=manual"


def _status_model(status: BreakerStatus) -> BreakerStatusResponse:
    return BreakerStatusResponse(**status.as_dict())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/breaker", response_model=BreakerStatusResponse)
async def breaker_status(
    breaker: ContainmentBreaker = Depends(provide_breaker),
) -> BreakerStatusResponse:
    """Current breaker state, trip counters, and cooldown remaining."""
    return _status_model(await breaker.status())


@router.post(
    "/breaker/reset",
    dependencies=_RESET,
    response_model=BreakerResetResponse,
)
async def breaker_reset(
    request: BreakerResetRequest,
    breaker: ContainmentBreaker = Depends(provide_breaker),
    audit: AuditWriter = Depends(provide_audit_writer),
    current_user: User = Depends(get_current_user),
) -> BreakerResetResponse:
    """Manually close the breaker and clear the trip counters. Audited.

    The audit entry joins no transaction — the breaker resets first, then
    the write happens; a failed audit surfaces as a failed request with the
    reset already applied (a retry records it; the reset itself is
    idempotent). Swallowing the audit failure would let a safety reset
    commit with no record.
    """
    before = await breaker.reset()
    after = await breaker.status()
    audit(
        before.as_dict(),
        after.as_dict(),
        current_user.username,
        request.reason,
    )
    logger.info(
        "containment breaker reset by %s: %s", current_user.username, request.reason
    )
    return BreakerResetResponse(
        before=_status_model(before), after=_status_model(after)
    )

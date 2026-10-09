"""Classified error surfaces for vendor-slice MCP tool servers.

Raw exception text must never reach the agent channel: an httpx error message
carries the upstream URL, and a vendor SDK error can carry response bodies or
internal hostnames. ``classified_error`` logs the full exception on the
privileged server-side log and returns a fixed string from a small vocabulary
— the log channel is privileged, the agent channel is not (finding E11).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Ordered: the most specific family first. Anything unmapped falls through to
# the generic reason — fail closed, no exception text however harmless it
# looks. The HTTPStatusError entry is special-cased in ``_reason_for``: the
# vendor's status code is classification (an int — reconfigure on 4xx, back
# off on 5xx), while its reason phrase and body are detail.
_REASONS: tuple[tuple[type[BaseException], Optional[str]], ...] = (
    (httpx.TimeoutException, "the integration service did not respond in time"),
    (httpx.ConnectError, "the integration service could not be reached"),
    (httpx.HTTPStatusError, None),
    (httpx.HTTPError, "the integration request failed"),
    (TimeoutError, "the request timed out"),
)
_GENERIC_REASON = "the tool call failed"


def _reason_for(exc: BaseException) -> str:
    for cls, reason in _REASONS:
        if not isinstance(exc, cls):
            continue
        if reason is not None:
            return reason
        status = getattr(exc, "response", None)
        code = getattr(status, "status_code", None)
        if isinstance(code, int):
            return f"the integration service returned HTTP {code}"
        return "the integration request failed"
    return _GENERIC_REASON


def classified_error(server: str, tool: str, exc: BaseException) -> str:
    """Log ``exc`` in full server-side; return a fixed string for the agent.

    The returned string is built from a fixed vocabulary plus, at most, the
    vendor's HTTP status code — never exception text, URLs, or upstream
    response bodies.
    """
    logger.warning(
        "%s tool '%s' failed: %s: %s",
        server,
        tool,
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    return f"tool '{tool}' failed: {_reason_for(exc)}"

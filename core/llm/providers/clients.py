"""Single source of truth for Anthropic SDK client construction.

All LLM traffic in Vigil routes through one gateway — Cloudflare AI Gateway
(spec workstream A), which replaced Bifrost as the inference path. The SDK
client is pointed at the gateway's Anthropic endpoint, which speaks the
Anthropic API verbatim, so extended thinking, native prompt caching, and
tool-use round-trip unchanged while the gateway layers in caching, rate
limits, and analytics.

Call sites that need an Anthropic client should import
``create_anthropic_client`` / ``create_async_anthropic_client`` from
this module instead of instantiating ``Anthropic()`` directly. This
keeps the gateway-routing decision in one place and makes it trivial to
audit (grep for ``Anthropic(``).

Key-validation endpoints that deliberately hit the upstream provider to
verify a user-supplied credential (e.g. ``services/api/routers/llm_providers.py``)
are the only exception and must still call ``Anthropic()`` directly.
"""

from __future__ import annotations

from core.config import get_settings
from core.llm.ai_gateway import gateway_base_url

_DEFAULT_TIMEOUT = 1800.0


def _anthropic_base_url() -> str:
    """Return the endpoint Anthropic traffic should hit.

    Normally this is AI Gateway's Anthropic endpoint —
    ``https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/anthropic`` —
    composed from settings by ``core.llm.ai_gateway``. The SDK appends
    ``/v1/messages`` and ``/v1/messages/count_tokens`` to it, and the gateway
    passes the Anthropic request body through untouched, which is what keeps
    ``cache_control`` blocks and the cache-token usage counters intact.

    ``ANTHROPIC_BASE_URL`` still wins when set, unchanged from the Bifrost era:
    dev and local runs point the SDK straight at Anthropic or at an internal
    Anthropic-compatible proxy (LiteLLM, etc.), bypassing the gateway. That is
    the documented escape hatch for a deployment where the gateway cannot be
    reached or is not wanted.
    """
    override = get_settings().anthropic_base_url.strip()
    if override:
        return override.rstrip("/")
    return gateway_base_url("anthropic")


def create_anthropic_client(api_key: str, *, timeout: float = _DEFAULT_TIMEOUT):
    """Synchronous Anthropic client routed through AI Gateway."""
    from anthropic import \
        Anthropic  # lazy so tests without the SDK still import

    return Anthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
        timeout=timeout,
    )


def create_async_anthropic_client(api_key: str, *, timeout: float = _DEFAULT_TIMEOUT):
    """Async Anthropic client routed through AI Gateway."""
    from anthropic import AsyncAnthropic  # lazy

    return AsyncAnthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
        timeout=timeout,
    )

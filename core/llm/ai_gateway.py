"""Cloudflare AI Gateway endpoint composition — one place that knows the shape.

Bifrost took every provider on one URL and routed by a prefixed model string
(``"openai/gpt-4o"``). AI Gateway routes by URL *path*: the provider is a
segment of the endpoint, so the model string is the provider's own model id and
nothing else. That single difference is why swapping the base URL alone was
never enough (spec workstream A).

    https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}

Resolution order for a provider's endpoint, most specific first:

1. The per-provider setting (``AI_GATEWAY_ANTHROPIC_BASE_URL`` /
   ``AI_GATEWAY_OPENAI_BASE_URL``) — a mock gateway in tests, or a compatible
   endpoint in dev.
2. The composed gateway URL, when the account and gateway ids are configured
   and the provider has an AI Gateway slug.
3. The provider row's own ``base_url``, for upstreams AI Gateway cannot reach
   because they are not on the internet — a local Ollama is the case that
   matters. Nothing here dials a provider host directly; the caller still
   constructs its client in the one sanctioned egress.

Only the composition lives here: no client is built and no request is sent, so
this module stays importable from anywhere without dragging in an SDK.
"""

from __future__ import annotations

from typing import Dict, Optional

from core.config import get_settings

# The public gateway root. Named once, here, so the one-egress ratchet can hold
# the line on where a gateway host may appear.
AI_GATEWAY_ROOT = "https://gateway.ai.cloudflare.com/v1"

# Vigil's ``provider_type`` (the value stored in ``llm_provider_configs``) to the
# AI Gateway path segment for that provider. A type absent from this map has no
# gateway route and falls back to its row's own base_url.
PROVIDER_SLUGS: Dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "azure-openai": "azure-openai",
    "google": "google-ai-studio",
    "gemini": "google-ai-studio",
    "groq": "groq",
    "mistral": "mistral",
    "deepseek": "deepseek",
    "perplexity": "perplexity-ai",
    "grok": "grok",
}

# Per-provider endpoint overrides, by provider_type. Two providers have a
# dedicated setting because two are the shapes Vigil dispatches: Anthropic's
# native surface and everything OpenAI-shaped.
_OVERRIDE_FIELDS: Dict[str, str] = {
    "anthropic": "ai_gateway_anthropic_base_url",
    "openai": "ai_gateway_openai_base_url",
}


class AIGatewayNotConfigured(RuntimeError):
    """No endpoint could be resolved for a provider.

    Raised rather than falling back to a provider host: a misconfigured gateway
    should fail loudly at dispatch, not quietly start billing the upstream
    directly and skip caching, limits, and analytics.
    """


def provider_slug(provider_type: str) -> Optional[str]:
    """AI Gateway path segment for *provider_type*, or ``None`` if it has none."""
    return PROVIDER_SLUGS.get((provider_type or "").strip().lower())


def _override(provider_type: str) -> str:
    field = _OVERRIDE_FIELDS.get((provider_type or "").strip().lower())
    if not field:
        return ""
    return (getattr(get_settings(), field, "") or "").strip().rstrip("/")


def _composed(provider_type: str) -> str:
    settings = get_settings()
    account = (settings.ai_gateway_account_id or "").strip()
    gateway = (settings.ai_gateway_id or "").strip()
    slug = provider_slug(provider_type)
    if not (account and gateway and slug):
        return ""
    return f"{AI_GATEWAY_ROOT}/{account}/{gateway}/{slug}"


def gateway_base_url(provider_type: str) -> str:
    """Endpoint for *provider_type*, override first, then the composed gateway.

    Raises ``AIGatewayNotConfigured`` when neither is available — callers that
    have a usable row-level fallback should use ``openai_shape_base_url``.
    """
    resolved = _override(provider_type) or _composed(provider_type)
    if resolved:
        return resolved
    raise AIGatewayNotConfigured(
        f"No AI Gateway endpoint for provider {provider_type!r}: set "
        "AI_GATEWAY_ACCOUNT_ID and AI_GATEWAY_ID, or the per-provider "
        "AI_GATEWAY_*_BASE_URL override."
    )


def openai_shape_base_url(provider_type: str, row_base_url: Optional[str]) -> str:
    """Endpoint for an OpenAI-shaped dispatch.

    Adds one step to ``gateway_base_url``: a provider with no gateway slug (a
    local Ollama) falls back to the endpoint stored on its own row. The OpenAI
    SDK appends ``/chat/completions``, and every OpenAI-compatible local server
    serves that under ``/v1``, so the suffix is added when it is missing.
    """
    resolved = _override(provider_type) or _composed(provider_type)
    if resolved:
        return resolved

    row = (row_base_url or "").strip().rstrip("/")
    if row:
        return row if row.endswith("/v1") else f"{row}/v1"

    raise AIGatewayNotConfigured(
        f"No endpoint for provider {provider_type!r}: set AI_GATEWAY_ACCOUNT_ID "
        "and AI_GATEWAY_ID, the per-provider AI_GATEWAY_*_BASE_URL override, or "
        "a base_url on the provider row."
    )

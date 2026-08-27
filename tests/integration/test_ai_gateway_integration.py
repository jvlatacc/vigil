"""Cloudflare AI Gateway smoke test.

Skipped by default. Runs only when the gateway is configured and a provider
credential is present, i.e. against real infrastructure:

    AI_GATEWAY_ACCOUNT_ID=... AI_GATEWAY_ID=... OPENAI_API_KEY=sk-... \\
        pytest -m integration tests/integration/test_ai_gateway_integration.py -v

Replaces the Bifrost gateway smoke test this file used to hold: the router no
longer has a single gateway URL to health-check, because AI Gateway routes by
URL path and the endpoint is resolved per provider at dispatch time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.getenv("AI_GATEWAY_ACCOUNT_ID") and os.getenv("AI_GATEWAY_ID")),
        reason="AI_GATEWAY_ACCOUNT_ID / AI_GATEWAY_ID not set — no gateway to hit",
    ),
]


def test_gateway_endpoint_is_provider_scoped():
    """The endpoint carries the provider as a path segment.

    Cheap half of the smoke test: it needs no credential, and it is the
    invariant a base-URL-only migration silently breaks.
    """
    from core.llm.ai_gateway import openai_shape_base_url

    endpoint = openai_shape_base_url("openai", "https://api.openai.com/v1")
    assert endpoint.startswith("https://gateway.ai.cloudflare.com/v1/")
    assert endpoint.endswith("/openai")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — no credential for the gateway to forward",
)
async def test_chat_completion_through_the_gateway():
    """A real dispatch: unprefixed model, provider-scoped endpoint, live tokens."""
    from unittest.mock import patch

    from core.llm.router.router import LLMRouter, ProviderSpec

    model = os.getenv("OPENAI_SMOKE_MODEL", "gpt-4o-mini")
    spec = ProviderSpec(
        provider_id="openai-smoke",
        provider_type="openai",
        base_url=None,
        api_key_ref="OPENAI_API_KEY",
        default_model=model,
        config={},
    )
    # The key comes from the environment here rather than the encrypted store,
    # so the secret lookup is the one thing stubbed.
    with patch(
        "core.llm.router.router.get_secret",
        return_value=os.environ["OPENAI_API_KEY"],
    ):
        result = await LLMRouter().dispatch(
            provider=spec,
            messages=[{"role": "user", "content": "Say the single word 'ping'."}],
            max_tokens=16,
        )

    assert result["path"] == "ai_gateway"
    assert result["provider"] == "openai"
    assert isinstance(result.get("content"), str) and result["content"].strip(), (
        "AI Gateway→OpenAI returned empty content"
    )

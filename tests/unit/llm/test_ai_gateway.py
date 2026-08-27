"""AI Gateway endpoint composition, and the Anthropic client that uses it.

The point these tests hold: the provider is a *path segment* of the endpoint,
never a prefix on the model string, and ``ANTHROPIC_BASE_URL`` still bypasses
the gateway for dev/local direct access.
"""

from __future__ import annotations

import pytest

from core.config import get_settings
from core.llm import ai_gateway
from core.llm.ai_gateway import AIGatewayNotConfigured
from core.llm.providers import clients

pytestmark = pytest.mark.unit


def _configure_gateway(monkeypatch, account="acct123", gateway="vigil-gw"):
    monkeypatch.setenv("AI_GATEWAY_ACCOUNT_ID", account)
    monkeypatch.setenv("AI_GATEWAY_ID", gateway)
    monkeypatch.delenv("AI_GATEWAY_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("AI_GATEWAY_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    get_settings.cache_clear()


def _unconfigure_gateway(monkeypatch):
    for key in (
        "AI_GATEWAY_ACCOUNT_ID",
        "AI_GATEWAY_ID",
        "AI_GATEWAY_ANTHROPIC_BASE_URL",
        "AI_GATEWAY_OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_type,expected_slug",
    [
        ("anthropic", "anthropic"),
        ("openai", "openai"),
        ("gemini", "google-ai-studio"),
        ("groq", "groq"),
        ("ANTHROPIC", "anthropic"),
    ],
)
def test_gateway_url_puts_the_provider_in_the_path(
    monkeypatch, provider_type, expected_slug
):
    _configure_gateway(monkeypatch)
    assert ai_gateway.gateway_base_url(provider_type) == (
        f"https://gateway.ai.cloudflare.com/v1/acct123/vigil-gw/{expected_slug}"
    )


def test_per_provider_override_wins_over_the_composed_url(monkeypatch):
    _configure_gateway(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_OPENAI_BASE_URL", "http://mock-gateway:9999/openai/")
    get_settings.cache_clear()

    # Trailing slash is normalized away: the SDK appends its own path.
    assert (
        ai_gateway.openai_shape_base_url("openai", None)
        == "http://mock-gateway:9999/openai"
    )
    # A different provider still composes from account + gateway id.
    assert ai_gateway.openai_shape_base_url("groq", None).endswith("/groq")


def test_unconfigured_gateway_fails_loudly(monkeypatch):
    _unconfigure_gateway(monkeypatch)
    with pytest.raises(AIGatewayNotConfigured):
        ai_gateway.gateway_base_url("anthropic")
    with pytest.raises(AIGatewayNotConfigured):
        ai_gateway.openai_shape_base_url("openai", None)


def test_a_provider_with_no_gateway_route_uses_its_own_row_url(monkeypatch):
    # Ollama runs on the host; AI Gateway cannot reach it, and the row is the
    # only place that knows where it listens. /v1 is where every
    # OpenAI-compatible local server serves chat/completions.
    _configure_gateway(monkeypatch)
    assert (
        ai_gateway.openai_shape_base_url("ollama", "http://localhost:11434")
        == "http://localhost:11434/v1"
    )
    # Already-suffixed URLs are left alone rather than doubled.
    assert (
        ai_gateway.openai_shape_base_url("ollama", "http://localhost:11434/v1/")
        == "http://localhost:11434/v1"
    )


def test_unconfigured_gateway_never_falls_back_to_a_provider_host(monkeypatch):
    # The row for a hosted provider carries the provider's own API host. Falling
    # back to it would turn a missing account id into silent direct egress —
    # billed direct, uncached, unlogged — which is precisely what the
    # one-egress ratchet claims cannot happen.
    _unconfigure_gateway(monkeypatch)
    with pytest.raises(AIGatewayNotConfigured):
        ai_gateway.openai_shape_base_url("openai", "https://api.openai.com/v1")


def test_gateway_route_beats_a_row_url_for_a_hosted_provider(monkeypatch):
    # One egress: an OpenAI row carrying api.openai.com must not win over the
    # gateway, or caching/limits/analytics silently stop applying.
    _configure_gateway(monkeypatch)
    resolved = ai_gateway.openai_shape_base_url("openai", "https://example-upstream/v1")
    assert resolved.endswith("/acct123/vigil-gw/openai")


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


def test_anthropic_client_targets_the_gateway_anthropic_endpoint(monkeypatch):
    _configure_gateway(monkeypatch)
    assert clients._anthropic_base_url() == (
        "https://gateway.ai.cloudflare.com/v1/acct123/vigil-gw/anthropic"
    )


def test_anthropic_base_url_override_still_bypasses_the_gateway(monkeypatch):
    # The dev/local escape hatch, preserved verbatim from the Bifrost era.
    _configure_gateway(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:4000/")
    get_settings.cache_clear()
    assert clients._anthropic_base_url() == "http://localhost:4000"


def test_anthropic_gateway_override_is_honoured(monkeypatch):
    _configure_gateway(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_ANTHROPIC_BASE_URL", "http://mock-gateway:9999/anthropic")
    get_settings.cache_clear()
    assert clients._anthropic_base_url() == "http://mock-gateway:9999/anthropic"

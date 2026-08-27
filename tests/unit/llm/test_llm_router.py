"""Unit tests for core.llm.router.router (GH #88).

Exercises the pure-logic path-selection rules and the dispatch wiring
with mocked openai / anthropic clients.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO))

from core.config import get_settings
from core.llm.ai_gateway import AIGatewayNotConfigured
from core.llm.router.router import (LLMRouter, ProviderSpec,
                                    provider_spec_from_row)

pytestmark = pytest.mark.unit

# A gateway-shaped endpoint: AI Gateway's provider path, pinned on the router so
# these tests exercise dispatch rather than endpoint composition (that is
# tests/unit/llm/test_ai_gateway.py).
MOCK_GATEWAY = "https://gateway.example/v1/acct123/vigil-gw/openai"


def _anthropic_spec() -> ProviderSpec:
    return ProviderSpec(
        provider_id="anthropic-default",
        provider_type="anthropic",
        base_url=None,
        api_key_ref="CLAUDE_API_KEY",
        default_model="claude-sonnet-4-5-20250929",
        config={},
    )


def _ollama_spec() -> ProviderSpec:
    return ProviderSpec(
        provider_id="ollama-local",
        provider_type="ollama",
        base_url="http://localhost:11434",
        api_key_ref=None,
        default_model="llama3.1:8b",
        config={},
    )


def _openai_spec() -> ProviderSpec:
    return ProviderSpec(
        provider_id="openai-prod",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key_ref="llm_provider_openai-prod_api_key",
        default_model="gpt-4o-mini",
        config={},
    )


# ---------------------------------------------------------------------------
# Path selection (pure logic)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dispatch — AI Gateway branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_through_gateway_for_ollama():
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="hello", tool_calls=None))
        ],
        model="ollama/llama3.1:8b",
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client) as oai_ctor:
        out = await router.dispatch(
            provider=_ollama_spec(),
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="be terse",
        )
    oai_ctor.assert_called_once()
    # base_url must be the gateway endpoint the router was constructed with
    assert oai_ctor.call_args.kwargs["base_url"] == MOCK_GATEWAY

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    # Unprefixed: the provider is in the URL path, not the model string. A
    # "ollama/" prefix here reaches the upstream as a model it does not have.
    assert kwargs["model"] == "llama3.1:8b"
    assert kwargs["messages"][0] == {"role": "system", "content": "be terse"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hi"}

    assert out["path"] == "ai_gateway"
    assert out["provider"] == "ollama"
    assert out["content"] == "hello"
    assert out["input_tokens"] == 5
    assert out["output_tokens"] == 7
    # The OpenAI-format dispatcher must close its client (no httpx pool leak).
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_translates_anthropic_tools_and_messages():
    """The daemon builds tools/messages in Anthropic shape. The OpenAI-shape
    dispatch must translate both (input_schema->parameters, tool_use->tool_calls,
    tool_result->role:tool) and normalize the response tool_calls back to
    {id,name,input} dicts, or the daemon's multi-turn tool loop breaks on
    non-Anthropic providers.
    """
    router = LLMRouter(base_url=MOCK_GATEWAY)
    returned_tc = SimpleNamespace(
        id="call_9",
        function=SimpleNamespace(name="get_case", arguments='{"case_id": "C1"}'),
    )
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[returned_tc])
            )
        ],
        model="ollama/llama3.1:8b",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    anthropic_tools = [
        {"name": "get_case", "description": "d", "input_schema": {"type": "object"}}
    ]
    anthropic_messages = [
        {"role": "user", "content": "investigate"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "call_9", "name": "get_case", "input": {}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_9", "content": "case data"}
            ],
        },
    ]

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        out = await router.dispatch(
            provider=_ollama_spec(),
            messages=anthropic_messages,
            tools=anthropic_tools,
        )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    # Tools translated to OpenAI function shape.
    assert kwargs["tools"][0]["type"] == "function"
    assert kwargs["tools"][0]["function"]["name"] == "get_case"
    assert kwargs["tools"][0]["function"]["parameters"] == {"type": "object"}
    # Messages translated: user text, assistant tool_calls, tool result message.
    roles = [m["role"] for m in kwargs["messages"]]
    assert roles == ["user", "assistant", "tool"]
    assert kwargs["messages"][1]["tool_calls"][0]["id"] == "call_9"
    assert kwargs["messages"][2]["tool_call_id"] == "call_9"
    # Response tool_calls normalized to {id,name,input} dicts.
    assert out["tool_calls"] == [
        {"id": "call_9", "name": "get_case", "input": {"case_id": "C1"}}
    ]


# ---------------------------------------------------------------------------
# Dispatch — Anthropic direct branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_openai_shape_extracts_cache_read_tokens():
    """#184 acceptance #2: OpenAI prompt-cache tokens were dropped on the floor
    by the dispatch layer, leaving cache hits billed at full input rate. Verify
    `usage.prompt_tokens_details.cached_tokens` is now read into
    `cache_read_tokens` (and `cache_creation_tokens` stays 0 — OpenAI doesn't
    bill cache creation as a separate tier the way Anthropic does).
    """
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="cached!", tool_calls=None))
        ],
        model="openai/gpt-4o",
        usage=SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=200,
            prompt_tokens_details=SimpleNamespace(cached_tokens=750),
        ),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        out = await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )
    assert out["input_tokens"] == 1000
    assert out["output_tokens"] == 200
    assert out["cache_read_tokens"] == 750
    assert out["cache_creation_tokens"] == 0


@pytest.mark.asyncio
async def test_dispatch_openai_shape_no_cache_details_safe():
    """When prompt_tokens_details is missing (older OpenAI responses or models
    without cache support), cache_read_tokens defaults to 0 — must not raise.
    """
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="x", tool_calls=None))
        ],
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        # no prompt_tokens_details attribute
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        out = await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )
    assert out["cache_read_tokens"] == 0
    assert out["cache_creation_tokens"] == 0


@pytest.mark.asyncio
async def test_dispatch_propagates_interaction_id_as_gateway_metadata():
    """#185: each LLM call carries the interaction UUID so the gateway's log
    entry can be correlated back to Vigil's local LLMInteractionLog row. AI
    Gateway's equivalent of Bifrost's `x-bf-lh-*` convention is a single
    `cf-aig-metadata` JSON object."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ],
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    interaction_id = "uuid-aaaa-1111"
    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
            interaction_id=interaction_id,
        )

    headers = mock_client.chat.completions.create.call_args.kwargs.get("extra_headers")
    assert headers is not None
    assert json.loads(headers["cf-aig-metadata"])["vigil_interaction_id"] == (
        interaction_id
    )


@pytest.mark.asyncio
async def test_dispatch_omits_extra_headers_when_no_interaction_id():
    """No interaction_id passed → no extra_headers kwarg, so we don't
    accidentally inject empty headers into every call."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ],
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "extra_headers" not in kwargs


@pytest.mark.asyncio
async def test_dispatch_attaches_budget_key_metadata_when_enforce_active():
    """#186: when budget_service.should_enforce() is True and a key is
    configured, dispatch carries it in `cf-aig-metadata` for attribution.
    Bifrost's virtual keys enforced the budget at the gateway; AI Gateway has
    no equivalent, so this is a log attribution, not enforcement."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ],
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
        "core.llm.cost.budget.should_enforce", return_value=True
    ), patch("core.llm.cost.budget.get_active_vk", return_value="sk-bf-test-vk"):
        await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )

    headers = mock_client.chat.completions.create.call_args.kwargs.get("extra_headers")
    assert headers is not None
    assert json.loads(headers["cf-aig-metadata"])["vigil_budget_key"] == "sk-bf-test-vk"


@pytest.mark.asyncio
async def test_dispatch_omits_budget_key_metadata_when_enforcement_off():
    """DEV_MODE / LLM_BUDGET_UNLIMITED → should_enforce() is False → the key
    is not logged to the gateway at all."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ],
        model="openai/gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
        "core.llm.cost.budget.should_enforce", return_value=False
    ), patch("core.llm.cost.budget.get_active_vk", return_value="sk-bf-test-vk"):
        await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    # No interaction_id and no enforcement → no extra_headers at all.
    assert "extra_headers" not in kwargs


@pytest.mark.asyncio
async def test_dispatch_translates_402_into_budget_exceeded():
    """A 402 from the gateway or the upstream provider means the spend cap is
    hit. The router must translate it into the typed BudgetExceeded so the chat
    UI renders a banner instead of a 500 toast."""
    from core.llm.cost.budget import BudgetExceeded

    router = LLMRouter(base_url=MOCK_GATEWAY)
    err = SimpleNamespace(status_code=402, message="$5 of $5 spent")
    raise_err = type("FakeAPIErr", (Exception,), {})("budget hit")
    raise_err.status_code = 402  # type: ignore[attr-defined]
    raise_err.message = "$5 of $5 spent"  # type: ignore[attr-defined]

    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=raise_err)

    with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
        "core.llm.cost.budget.should_enforce", return_value=True
    ), patch("core.llm.cost.budget.get_active_vk", return_value="sk-bf-test"):
        with pytest.raises(BudgetExceeded) as excinfo:
            await router.dispatch(
                provider=_openai_spec(),
                messages=[{"role": "user", "content": "hi"}],
            )

    assert excinfo.value.status_code == 402
    assert excinfo.value.tier == "virtual_key"
    # Even on the error path the client must be closed (finally block).
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_retries_a_429_rather_than_failing_the_run():
    """A rate limit is not a budget failure.

    This asserted the opposite until the two halves were unified: 429 raised
    BudgetExceeded(tier="rate_limit") and nothing caught it, so a two-second
    wait failed the run and was reported as being out of credit. The agent
    worker had always retried the same response.
    """
    router = LLMRouter(base_url=MOCK_GATEWAY)
    limited = type("FakeAPIErr", (Exception,), {})("rate limited")
    limited.status_code = 429  # type: ignore[attr-defined]

    answered = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="hello", tool_calls=None))
        ],
        model="gpt-4o",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[limited, answered])

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        with patch("core.llm.gateway_retry.asyncio.sleep", new=AsyncMock()):
            out = await router.dispatch(
                provider=_openai_spec(),
                messages=[{"role": "user", "content": "hi"}],
            )

    assert out["content"] == "hello"
    assert mock_client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_dispatch_does_not_swallow_non_budget_errors():
    """Only 402/429 map to BudgetExceeded. A 500 should propagate as-is
    so the caller sees the real error and doesn't think it's a budget
    issue."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    raise_err = type("FakeAPIErr", (Exception,), {})("upstream blew up")
    raise_err.status_code = 500  # type: ignore[attr-defined]

    mock_client = MagicMock()
    # Dispatchers close the client in a finally block to avoid leaking the
    # httpx pool; make .close() awaitable so the real cleanup path runs.
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=raise_err)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(Exception) as excinfo:
            await router.dispatch(
                provider=_openai_spec(),
                messages=[{"role": "user", "content": "hi"}],
            )
    assert getattr(excinfo.value, "status_code", None) == 500
    # Must not have been wrapped into BudgetExceeded.
    from core.llm.cost.budget import BudgetExceeded

    assert not isinstance(excinfo.value, BudgetExceeded)


# ---------------------------------------------------------------------------
# provider_spec_from_row
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Non-default Anthropic providers must route through the router so the
# per-provider api_key_ref is resolved (regression for PR #103 review).
# ---------------------------------------------------------------------------


def test_provider_spec_from_row_copies_fields():
    row = SimpleNamespace(
        provider_id="p",
        provider_type="openai",
        base_url="https://example.com",
        api_key_ref="ref",
        default_model="gpt-4o",
        config={"organization": "o"},
    )
    spec = provider_spec_from_row(row)
    assert spec.provider_id == "p"
    assert spec.provider_type == "openai"
    assert spec.base_url == "https://example.com"
    assert spec.api_key_ref == "ref"
    assert spec.default_model == "gpt-4o"
    assert spec.config == {"organization": "o"}
    assert spec.config == {"organization": "o"}


# ---------------------------------------------------------------------------
# discover_anthropic_api_key — fallback path so the chat drawer works for
# users who only configured Anthropic through the Settings UI (#292).
# ---------------------------------------------------------------------------


def _stub_session(rows):
    """Build a fake SQLAlchemy session that returns *rows* from .query(...).all()."""
    session = MagicMock()
    chain = session.query.return_value.filter.return_value.order_by.return_value
    chain.all.return_value = rows
    return session


def test_discover_anthropic_api_key_returns_secret_for_default_row():
    from core.llm.router import router as llm_router

    default_row = SimpleNamespace(
        provider_id="anthropic-default",
        api_key_ref="llm_provider_anthropic-default_api_key",
    )
    session = _stub_session([default_row])

    with patch.object(llm_router, "get_secret", return_value="sk-ant-ui-saved"), patch(
        "core.storage.connection.get_db_session", return_value=session
    ):
        assert llm_router.discover_anthropic_api_key() == "sk-ant-ui-saved"


def test_discover_anthropic_api_key_falls_through_to_active_row():
    """If the default row's secret is missing, the next active row wins."""
    from core.llm.router import router as llm_router

    default_row = SimpleNamespace(
        provider_id="anthropic-default",
        api_key_ref="llm_provider_anthropic-default_api_key",
    )
    other_row = SimpleNamespace(
        provider_id="anthropic-team",
        api_key_ref="llm_provider_anthropic-team_api_key",
    )
    session = _stub_session([default_row, other_row])

    def fake_get_secret(ref):
        # Default row's secret missing; team's secret resolves.
        return None if "default" in ref else "sk-ant-team-key"

    with patch.object(llm_router, "get_secret", side_effect=fake_get_secret), patch(
        "core.storage.connection.get_db_session", return_value=session
    ):
        assert llm_router.discover_anthropic_api_key() == "sk-ant-team-key"


def test_discover_anthropic_api_key_returns_none_when_no_rows():
    from core.llm.router import router as llm_router

    session = _stub_session([])
    with patch.object(llm_router, "get_secret", return_value=None), patch(
        "core.storage.connection.get_db_session", return_value=session
    ):
        assert llm_router.discover_anthropic_api_key() is None


def test_discover_anthropic_api_key_returns_none_when_db_unavailable():
    """DB import error => silent None, so the legacy chain stays usable
    in environments where core.storage.connection can't import."""
    # Patch ``get_db_session`` to raise on import. Easiest: make the
    # entire ``core.storage.connection`` import fail by patching builtins.
    import builtins

    from core.llm.router import router as llm_router

    real_import = builtins.__import__

    def boom_import(name, *args, **kwargs):
        if name == "core.storage.connection":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=boom_import):
        assert llm_router.discover_anthropic_api_key() is None


# ---------------------------------------------------------------------------
# Streaming — dispatch_openai_stream / stream_openai_raw (GH #325, #436)
# ---------------------------------------------------------------------------


def _delta_chunk(content):
    """A minimal OpenAI streaming chunk carrying a content delta."""
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


async def _achunks(chunks):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_dispatch_openai_stream_yields_text_and_skips_empty():
    """The chat SSE path streams every provider through its AI Gateway
    OpenAI-shaped endpoint. Text deltas must surface as
    {"type": "text", "content": ...}; frames with no choices or no content
    (e.g. role/usage-only frames) must be skipped."""
    router = LLMRouter(base_url=MOCK_GATEWAY)
    chunks = [
        _delta_chunk("Hello"),
        SimpleNamespace(choices=[]),  # no choices -> skipped
        _delta_chunk(None),  # no content -> skipped
        _delta_chunk(", world"),
    ]
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_achunks(chunks))

    with patch("openai.AsyncOpenAI", return_value=mock_client) as oai_ctor:
        out = [
            ev
            async for ev in router.dispatch_openai_stream(
                provider=_ollama_spec(),
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="be terse",
            )
        ]

    assert out == [
        {"type": "text", "content": "Hello"},
        {"type": "text", "content": ", world"},
    ]
    # base_url must be the gateway endpoint, not a provider host
    assert oai_ctor.call_args.kwargs["base_url"] == MOCK_GATEWAY
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    # Unprefixed on the streaming path too: the provider is in the URL.
    assert kwargs["model"] == "llama3.1:8b"
    assert kwargs["messages"][0] == {"role": "system", "content": "be terse"}
    # client is closed on normal completion (no httpx pool leak)
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_openai_raw_include_usage_sets_stream_options():
    router = LLMRouter(base_url=MOCK_GATEWAY)
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_achunks([]))

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        _ = [
            c
            async for c in router.stream_openai_raw(
                provider=_ollama_spec(),
                messages=[{"role": "user", "content": "hi"}],
                include_usage=True,
            )
        ]

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_openai_raw_closes_client_on_early_disconnect():
    """If the SSE consumer goes away mid-stream, GeneratorExit propagates into
    stream_openai_raw's yield and the finally must still close the client so
    the httpx pool doesn't leak under load."""
    router = LLMRouter(base_url=MOCK_GATEWAY)

    async def _endless():
        for i in range(100):  # far more than the consumer will read
            yield _delta_chunk(f"tok{i}")

    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_endless())

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        agen = router.stream_openai_raw(
            provider=_ollama_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )
        first = await agen.__anext__()
        assert getattr(first.choices[0].delta, "content", None) == "tok0"
        await agen.aclose()  # simulate consumer disconnect mid-stream

    mock_client.close.assert_awaited_once()


# Dropped with the second schema (#644). Every one asserted something about
# choosing between two egress paths, and there is one:
#
#   test_path_* and test_router_class_method_matches_free_function — select_path
#     returned the constant "bifrost" for every provider before it was deleted.
#     What it was really pinning is now a ratchet:
#     tests/unit/_ratchets/test_one_egress.py.
#
#   test_dispatch_anthropic_*, test_anthropic_dispatch_raises_when_no_key,
#   test_dispatch_propagates_interaction_id_anthropic — _dispatch_anthropic took
#     Bifrost's /anthropic passthrough to keep extended thinking and
#     cache_control. ADR 0011 traded both away and by #632 nothing requested
#     either, so the passthrough preserved features with no caller. The OpenAI
#     equivalents of these cases are kept above.
#
#   test_*_anthropic_with_thinking_* and test_is_default_anthropic_recognizes_
#   legacy_refs — the fallback they described handed default-Anthropic thinking
#     calls to ClaudeService for its tool loop. That loop went in #631.


# ---------------------------------------------------------------------------
# Endpoint resolution — router with no pinned base_url (the deployed case)
# ---------------------------------------------------------------------------


def _configure_gateway(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("AI_GATEWAY_ID", "vigil-gw")
    monkeypatch.delenv("AI_GATEWAY_OPENAI_BASE_URL", raising=False)
    get_settings.cache_clear()


def _stub_openai_client():
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ],
        model="gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    return mock_client


@pytest.mark.asyncio
async def test_dispatch_resolves_the_provider_scoped_gateway_endpoint(monkeypatch):
    """Unpinned, dispatch composes the endpoint for the provider it was handed.

    The provider is a path segment, so a hosted provider's own base_url must not
    win over the gateway — that would leave the one-egress ratchet true on paper
    and false at runtime. The stored provider key travels on the request,
    because AI Gateway forwards Authorization rather than holding credentials.
    """
    _configure_gateway(monkeypatch)
    router = LLMRouter()
    mock_client = _stub_openai_client()

    with patch("openai.AsyncOpenAI", return_value=mock_client) as oai_ctor, patch(
        "core.llm.router.router.get_secret", return_value="sk-openai-real"
    ):
        out = await router.dispatch(
            provider=_openai_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )

    assert oai_ctor.call_args.kwargs["base_url"] == (
        "https://gateway.ai.cloudflare.com/v1/acct123/vigil-gw/openai"
    )
    assert oai_ctor.call_args.kwargs["api_key"] == "sk-openai-real"
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == (
        "gpt-4o-mini"
    )
    assert out["path"] == "ai_gateway"


@pytest.mark.asyncio
async def test_dispatch_keeps_a_local_provider_on_its_own_endpoint(monkeypatch):
    """Ollama runs on the host and AI Gateway cannot reach it, so the row's
    base_url stays authoritative and the key stays a placeholder."""
    _configure_gateway(monkeypatch)
    router = LLMRouter()
    mock_client = _stub_openai_client()

    with patch("openai.AsyncOpenAI", return_value=mock_client) as oai_ctor:
        await router.dispatch(
            provider=_ollama_spec(),
            messages=[{"role": "user", "content": "hi"}],
        )

    assert oai_ctor.call_args.kwargs["base_url"] == "http://localhost:11434/v1"
    assert oai_ctor.call_args.kwargs["api_key"] == "unused"


@pytest.mark.asyncio
async def test_stream_resolves_the_provider_scoped_gateway_endpoint(monkeypatch):
    """Streaming resolves the same way as non-streaming — one seam, not two."""
    _configure_gateway(monkeypatch)
    router = LLMRouter()
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_achunks([_delta_chunk("Hello")])
    )

    with patch("openai.AsyncOpenAI", return_value=mock_client) as oai_ctor, patch(
        "core.llm.router.router.get_secret", return_value="sk-openai-real"
    ):
        out = [
            ev
            async for ev in router.dispatch_openai_stream(
                provider=_openai_spec(),
                messages=[{"role": "user", "content": "hi"}],
                interaction_id="uuid-bbbb-2222",
            )
        ]

    assert out == [{"type": "text", "content": "Hello"}]
    assert oai_ctor.call_args.kwargs["base_url"] == (
        "https://gateway.ai.cloudflare.com/v1/acct123/vigil-gw/openai"
    )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    metadata = json.loads(kwargs["extra_headers"]["cf-aig-metadata"])
    assert metadata["vigil_interaction_id"] == "uuid-bbbb-2222"


@pytest.mark.asyncio
async def test_dispatch_fails_loudly_when_the_gateway_is_unconfigured(monkeypatch):
    """No account/gateway id and no override: raise rather than silently fall
    back to the provider host, which would bill direct and drop caching, rate
    limits and analytics."""
    for key in (
        "AI_GATEWAY_ACCOUNT_ID",
        "AI_GATEWAY_ID",
        "AI_GATEWAY_OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    # AsyncOpenAI is patched so a regression here fails the assertion instead of
    # actually dialling the provider from CI.
    with patch("openai.AsyncOpenAI", return_value=_stub_openai_client()), patch(
        "core.llm.router.router.get_secret", return_value="sk-openai-real"
    ):
        with pytest.raises(AIGatewayNotConfigured):
            await LLMRouter().dispatch(
                provider=_openai_spec(),
                messages=[{"role": "user", "content": "hi"}],
            )

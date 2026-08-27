# Chat left the queue: a turn is now handed to the conversation's Durable Object
# over HTTP. What matters is that the caller can tell admitted from refused, since
# a refusal reported as dispatched leaves the console reading an empty stream.

from __future__ import annotations

import httpx
import pytest
import respx

from core.agents.queue import (
    RUN_KINDS,
    ChatDispatch,
    ChatDispatchError,
    chat_identity,
    dispatch_chat_turn,
)

pytestmark = pytest.mark.unit

EDGE = "http://edge.test"
ROUTE = f"{EDGE}/chat/conv-1"

RECEIPT = {
    "submissionId": "sub-7",
    "streamUrl": "/chat/conv-1/stream?offset=0",
    "offset": "0",
}


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(
        "core.agents.internal_token.get_secret",
        lambda name: "s3cret",
    )
    settings = type("S", (), {"edge_url": EDGE})()
    monkeypatch.setattr("core.agents.queue.get_settings", lambda: settings)


def identity():
    return chat_identity(
        user_id="u-1",
        model="claude-sonnet-4-6",
        scopes=["findings:read"],
        tenant_id="t-1",
    )


# The backend has no chat job to enqueue, and a kind left in the tuple is one a
# worker will eventually be asked to run.
def test_chat_is_not_an_enqueueable_kind():
    assert "chat" not in RUN_KINDS


def test_declarations_carry_their_schema_under_the_edge_field_name():
    built = chat_identity(
        user_id="u-1",
        model="m",
        scopes=[],
        tools=[
            {
                "id": "search_findings",
                "description": "Search findings",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                },
            },
            {"id": "bare", "description": "No schema", "parameters": None},
        ],
    )
    assert [tool["name"] for tool in built["tools"]] == ["search_findings", "bare"]
    assert built["tools"][0]["parameters"]["properties"] == {"q": {"type": "string"}}
    # A declaration with no schema still names an object: Valibot needs a shape to
    # validate against, and "no arguments" is one.
    assert built["tools"][1]["parameters"] == {"type": "object"}


def test_the_identity_names_the_scope_the_turn_runs_under():
    built = identity()
    assert built["userId"] == "u-1"
    assert built["scopes"] == ["findings:read"]
    assert built["tenantId"] == "t-1"


@pytest.mark.asyncio
@respx.mock
async def test_an_admitted_turn_answers_with_the_stream_to_read(configured):
    route = respx.post(ROUTE).mock(
        return_value=httpx.Response(202, json=RECEIPT),
    )

    dispatched = await dispatch_chat_turn("conv-1", "what changed?", identity())

    assert dispatched == ChatDispatch(
        submission_id="sub-7",
        stream_url="/chat/conv-1/stream?offset=0",
        offset="0",
    )
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer s3cret"
    body = httpx.Response(200, content=request.content).json()
    assert body["message"] == "what changed?"
    # Identity travels with the delivery. The agent reads it from the record it was
    # created with, never from a request that arrives later.
    assert body["initialData"]["userId"] == "u-1"


@pytest.mark.asyncio
@respx.mock
async def test_a_conversation_id_with_a_slash_addresses_one_conversation(configured):
    route = respx.post(f"{EDGE}/chat/a%2Fb").mock(
        return_value=httpx.Response(202, json=RECEIPT),
    )

    await dispatch_chat_turn("a/b", "hello", identity())

    assert route.called


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("status", [400, 401, 429, 500])
async def test_anything_but_202_is_a_refusal(configured, status):
    respx.post(ROUTE).mock(return_value=httpx.Response(status, text="nope"))

    with pytest.raises(ChatDispatchError, match=str(status)):
        await dispatch_chat_turn("conv-1", "hello", identity())


@pytest.mark.asyncio
@respx.mock
async def test_a_receipt_naming_no_stream_is_a_refusal(configured):
    respx.post(ROUTE).mock(return_value=httpx.Response(202, json={"submissionId": "s"}))

    with pytest.raises(ChatDispatchError, match="named no stream"):
        await dispatch_chat_turn("conv-1", "hello", identity())


@pytest.mark.asyncio
@respx.mock
async def test_an_unreachable_edge_is_a_refusal_rather_than_a_transport_error(
    configured,
):
    respx.post(ROUTE).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ChatDispatchError, match="did not answer"):
        await dispatch_chat_turn("conv-1", "hello", identity())


@pytest.mark.asyncio
async def test_a_deployment_with_no_token_refuses_before_it_calls(
    configured, monkeypatch
):
    monkeypatch.setattr("core.agents.internal_token.get_secret", lambda name: None)

    with pytest.raises(RuntimeError, match="AGENT_INTERNAL_TOKEN"):
        await dispatch_chat_turn("conv-1", "hello", identity())

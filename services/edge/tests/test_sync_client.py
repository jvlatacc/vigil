"""Sync client wire behavior: auth header, fail-closed credentials, error
mapping. The transport is httpx's MockTransport — no network, no DNS."""

from __future__ import annotations

import asyncio
import json
import os
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from services.edge.sync.client import (
    EnrollError,
    SyncClient,
    SyncError,
    UnauthorizedError,
)

CREDENTIAL = "edge-cred-abc123"


def handler_map(
    calls: list[httpx.Request],
    *,
    status_by_path: dict[str, HTTPStatus] | None = None,
    body_by_path: dict[str, object] | None = None,
):
    status_by_path = status_by_path or {}
    body_by_path = body_by_path or {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        status = status_by_path.get(path, HTTPStatus.OK)
        body = body_by_path.get(path)
        if isinstance(body, ValueError):  # force a non-JSON body
            return httpx.Response(status, text="not-json")
        return httpx.Response(status, json=body if body is not None else {})

    return handler


def make_client(
    tmp_path: Path, handler, *, credential: str | None = CREDENTIAL
) -> SyncClient:
    client = SyncClient(
        control_url="http://control.test",
        node_id="gw-test",
        credential_file=tmp_path / "credential",
        transport=httpx.MockTransport(handler),
    )
    if credential is not None:
        client._credential = credential
    return client


def test_enroll_success_persists_credential(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = make_client(
        tmp_path,
        handler_map(
            calls,
            status_by_path={"/internal/edge/enroll": HTTPStatus.CREATED},
            body_by_path={
                "/internal/edge/enroll": {
                    "node_id": "gw-test",
                    "credential": CREDENTIAL,
                }
            },
        ),
        credential=None,
    )

    async def scenario() -> None:
        await client.enroll("one-time-token", {"vpc": "vpc-1"})

    asyncio.run(scenario())
    assert client.credential == CREDENTIAL
    assert client.credential_file.read_text() == CREDENTIAL
    assert os.stat(client.credential_file).st_mode & 0o777 == 0o600
    enroll = calls[0]
    body = json.loads(enroll.read())
    assert enroll.url.path == "/internal/edge/enroll"
    assert body["enrollment_token"] == "one-time-token"
    assert "Authorization" not in enroll.headers  # enrollment is pre-credential


def test_enroll_failures_raise_enroll_error(tmp_path: Path) -> None:
    for status, expected in (
        (HTTPStatus.UNAUTHORIZED, "401"),
        (HTTPStatus.SERVICE_UNAVAILABLE, "503"),
        (HTTPStatus.BAD_REQUEST, "400"),
    ):
        client = make_client(
            tmp_path / f"c{status.value}",
            handler_map([], status_by_path={"/internal/edge/enroll": status}),
            credential=None,
        )

        async def scenario() -> None:
            await client.enroll("token", {})

        with pytest.raises(EnrollError, match=expected):
            asyncio.run(scenario())
        assert client.credential is None


def test_authenticated_calls_carry_the_bearer_header(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = make_client(
        tmp_path,
        handler_map(
            calls,
            body_by_path={
                "/internal/edge/gw-test/heartbeat": {"ok": True, "revoked": False}
            },
        ),
    )

    async def scenario() -> None:
        await client.heartbeat(
            boot_id="boot-1",
            bundle_version=7,
            autonomy_tier="tier2",
            lease_state="blocks:0",
            acked_upto=4,
        )

    asyncio.run(scenario())
    assert calls[0].headers["Authorization"] == f"Bearer {CREDENTIAL}"
    body = json.loads(calls[0].read())
    assert body == {
        "boot_id": "boot-1",
        "bundle_version": 7,
        "autonomy_tier": "tier2",
        "lease_state": "blocks:0",
        "acked_upto": 4,
    }


def test_pull_policy_sends_the_cursor(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = make_client(
        tmp_path,
        handler_map(
            calls,
            body_by_path={
                "/internal/edge/gw-test/policy": {
                    "bundle": None,
                    "current_version": 7,
                }
            },
        ),
    )

    async def scenario() -> None:
        await client.pull_policy(None)
        await client.pull_policy(7)

    asyncio.run(scenario())
    assert "cursor" not in calls[0].url.params  # cold start: no backfill
    assert calls[1].url.params["cursor"] == "7"


def test_post_events_returns_the_durable_result(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        handler_map(
            [],
            body_by_path={
                "/internal/edge/gw-test/events": {
                    "acked": ["k1"],
                    "duplicates": [],
                    "rejected": [],
                }
            },
        ),
    )

    async def scenario() -> dict:
        return await client.post_events([{"event_id": "k1", "kind": "revert"}])

    result = asyncio.run(scenario())
    assert result["acked"] == ["k1"]


def test_no_credential_fails_closed_without_a_request(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = make_client(tmp_path, handler_map(calls), credential=None)

    async def scenario() -> None:
        await client.heartbeat(
            boot_id="b",
            bundle_version=None,
            autonomy_tier="tier0",
            lease_state="blocks:0",
            acked_upto=None,
        )

    with pytest.raises(SyncError, match="no credential"):
        asyncio.run(scenario())
    assert calls == []  # nothing left the process


def test_transport_failure_is_a_survivable_sync_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cable pulled")

    client = make_client(tmp_path, handler)

    async def scenario() -> None:
        await client.pull_policy(None)

    with pytest.raises(SyncError, match="failed"):
        asyncio.run(scenario())


def test_401_is_unauthorized_not_a_generic_failure(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        handler_map(
            [],
            status_by_path={"/internal/edge/gw-test/policy": HTTPStatus.UNAUTHORIZED},
        ),
    )

    async def scenario() -> None:
        await client.pull_policy(None)

    with pytest.raises(UnauthorizedError):
        asyncio.run(scenario())


def test_error_body_and_non_json_body_raise_sync_errors(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        handler_map(
            [],
            status_by_path={
                "/internal/edge/gw-test/events": HTTPStatus.INSUFFICIENT_STORAGE
            },
        ),
    )

    async def scenario() -> None:
        await client.post_events([])

    with pytest.raises(SyncError, match="507"):
        asyncio.run(scenario())

    client = make_client(
        tmp_path / "b",
        handler_map([], body_by_path={"/internal/edge/gw-test/policy": ValueError()}),
    )

    async def scenario2() -> None:
        await client.pull_policy(None)

    with pytest.raises(SyncError, match="non-JSON"):
        asyncio.run(scenario2())


def test_load_credential_adopts_the_persisted_secret(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = SyncClient(
        control_url="http://control.test",
        node_id="gw-test",
        credential_file=tmp_path / "credential",
        transport=transport,
    )
    assert client.load_credential() is False  # nothing stored yet
    client._persist_credential(CREDENTIAL)
    fresh = SyncClient(
        control_url="http://control.test",
        node_id="gw-test",
        credential_file=tmp_path / "credential",
        transport=transport,
    )
    assert fresh.load_credential() is True  # an enrolled node survives restart
    assert fresh.credential == CREDENTIAL

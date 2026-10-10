"""Sentinel intake: fail-closed auth, bounded queue, dedup, body limits."""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import ClientSession

from services.warden.metrics import WardenMetrics
from services.warden.sentinel import Sentinel


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@asynccontextmanager
async def running_sentinel(
    *, token: str | None = "good", max_queue: int = 1000
) -> AsyncIterator[tuple[Sentinel, str]]:
    """A live Sentinel on a free port; yields (sentinel, base_url)."""
    sentinel = Sentinel(
        bind_host="127.0.0.1",
        port=free_port(),
        token=token,
        max_queue=max_queue,
        metrics=WardenMetrics(),
    )
    shutdown = asyncio.Event()
    task = asyncio.create_task(sentinel.run(shutdown))
    try:
        yield sentinel, f"http://127.0.0.1:{sentinel._port}"
    finally:
        shutdown.set()
        await task


async def post(
    session: ClientSession,
    base: str,
    body: object,
    *,
    token: str | None = "good",
) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for _ in range(50):
        try:
            async with session.post(
                f"{base}/alert", json=body, headers=headers
            ) as response:
                return response.status, await response.json()
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("sentinel server did not start")


def alert(target: str = "198.51.100.7", **extra: object) -> dict:
    return {"id": f"a-{target}", "indicator": "ip", "value": target, **extra}


class TestFailClosedAuth:
    async def test_unset_token_rejects_everything_with_503(self) -> None:
        async with running_sentinel(token=None) as (sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, alert(), token="anything")
        assert status == 503
        assert payload["reason"] == "no_secret"
        assert sentinel.queue.empty()

    async def test_wrong_token_is_401(self) -> None:
        async with running_sentinel() as (_sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, alert(), token="bad")
        assert status == 401
        assert payload["reason"] == "bad_token"

    async def test_missing_token_is_401(self) -> None:
        async with running_sentinel() as (_sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, alert(), token=None)
        assert status == 401
        assert payload["reason"] == "bad_token"

    async def test_prefix_token_is_401(self) -> None:
        # The whole Authorization header is compared, so a credential that
        # merely prefixes the real one cannot slide through.
        async with running_sentinel(token="good") as (_sentinel, base):
            async with ClientSession() as session:
                status, _ = await post(session, base, alert(), token="good-extra")
        assert status == 401


class TestIntake:
    async def test_single_alert_is_accepted_and_queued(self) -> None:
        async with running_sentinel() as (sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, alert())
        assert status == 202
        assert payload["accepted"] == 1
        queued = sentinel.drain(10)
        assert len(queued) == 1
        assert queued[0]["value"] == "198.51.100.7"

    async def test_batch_push_is_accepted(self) -> None:
        batch = {"alerts": [alert(f"198.51.100.{n}") for n in range(3)]}
        async with running_sentinel() as (sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, batch)
        assert status == 202
        assert payload["accepted"] == 3
        assert len(sentinel.drain(10)) == 3

    async def test_duplicate_ids_are_counted_not_queued(self) -> None:
        async with running_sentinel() as (sentinel, base):
            async with ClientSession() as session:
                first = await post(session, base, alert())
                second = await post(session, base, alert())
        assert first[0] == second[0] == 202
        assert second[1]["duplicates"] == 1
        assert second[1]["accepted"] == 0
        assert len(sentinel.drain(10)) == 1  # the original only

    async def test_non_json_body_is_400(self) -> None:
        async with running_sentinel() as (_sentinel, base):
            async with ClientSession() as session:
                for _ in range(50):
                    try:
                        async with session.post(
                            f"{base}/alert",
                            data=b"not json",
                            headers={"Authorization": "Bearer good"},
                        ) as response:
                            status = response.status
                            payload = await response.json()
                        break
                    except OSError:
                        await asyncio.sleep(0.05)
                else:
                    raise RuntimeError("sentinel server did not start")
        assert status == 400
        assert payload["reason"] == "bad_body"

    async def test_alert_without_id_is_400(self) -> None:
        async with running_sentinel() as (_sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, {"value": "1.2.3.4"})
        assert status == 400
        assert payload["reason"] == "bad_body"

    async def test_bare_list_payload_is_rejected(self) -> None:
        # A bare list has no per-alert identity contract; require an
        # object or an {"alerts": [...]} envelope.
        async with running_sentinel() as (_sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, [alert()])
        assert status == 400
        assert payload["reason"] == "bad_body"

    async def test_oversized_batch_is_rejected(self) -> None:
        batch = {"alerts": [alert(f"198.51.100.{n}") for n in range(101)]}
        async with running_sentinel() as (sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, batch)
        assert status == 400
        assert payload["reason"] == "bad_body"
        assert sentinel.queue.empty()


class TestBoundedQueue:
    async def test_full_queue_returns_503_and_keeps_nothing(self) -> None:
        async with running_sentinel(max_queue=1) as (sentinel, base):
            async with ClientSession() as session:
                ok = await post(session, base, alert("198.51.100.7"))
                full = await post(session, base, alert("198.51.100.8"))
        assert ok[0] == 202
        assert full[0] == 503
        assert full[1]["reason"] == "queue_full"
        assert len(sentinel.drain(10)) == 1  # the first push only

    async def test_partial_batch_fit_is_acknowledged(self) -> None:
        batch = {"alerts": [alert(f"198.51.100.{n}") for n in range(5)]}
        async with running_sentinel(max_queue=2) as (sentinel, base):
            async with ClientSession() as session:
                status, payload = await post(session, base, batch)
        assert status == 202
        assert payload["accepted"] == 2
        assert len(sentinel.drain(10)) == 2

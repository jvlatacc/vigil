"""Decoy telemetry through the daemon's generic ingest webhook (spec AC10).

The loop under test is the farm's whole reason to exist: a decoy session log
line is normalized by the shipper, posted to the daemon webhook the way the
decoy-shipper container posts it, and arrives on the daemon's processing
queue as an ordinary finding — triage and enrichment run on it exactly as
they would for any other source. No decoy-specific daemon changes are
involved: if this passes, the loop works on today's daemon.
"""

import asyncio
import json
import socket
from unittest.mock import patch

import pytest
from aiohttp import ClientSession

from services.daemon.config import PollingConfig
from services.daemon.poller import DataPoller
from services.decoy_farm import telemetry

pytestmark = pytest.mark.integration

TOKEN = "decoy-test-token"


class _Config:
    def get_disabled_integration_ids(self):
        return set()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _post(session, port, body, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(50):
        try:
            async with session.post(
                f"http://127.0.0.1:{port}/ingest", json=body, headers=headers
            ) as resp:
                return resp.status, await resp.json()
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("webhook server did not start")


def _ship(kind, record, farm_id="decoy-farm"):
    """Exactly what the shipper does per tailed line before posting."""
    raw = json.dumps(record)
    return telemetry.build_finding(
        kind, raw, farm_id=farm_id, fallback_ts="2026-10-10T10:00:03+00:00"
    )


@pytest.mark.asyncio
async def test_cowrie_decoy_session_becomes_findings():
    port = _free_port()
    poller = DataPoller(PollingConfig(webhook_token=TOKEN, webhook_port=port))
    queue = asyncio.Queue()
    poller.set_output_queue(queue)

    # One attacker session across three cowrie events, shaped as the
    # output_jsonlog plugin writes them.
    batch = [
        _ship(
            "cowrie",
            {
                "eventid": "cowrie.session.connect",
                "src_ip": "203.0.113.7",
                "session": "sess-1",
                "message": "connection opened",
                "timestamp": "2026-10-10T10:00:00Z",
            },
        ),
        _ship(
            "cowrie",
            {
                "eventid": "cowrie.login.failed",
                "src_ip": "203.0.113.7",
                "username": "root",
                "password": "toor",
                "session": "sess-1",
                "message": "login failed",
                "timestamp": "2026-10-10T10:00:01Z",
            },
        ),
        _ship(
            "cowrie",
            {
                "eventid": "cowrie.command.input",
                "src_ip": "203.0.113.7",
                "session": "sess-1",
                "message": "uname -a",
                "timestamp": "2026-10-10T10:00:02Z",
            },
        ),
    ]
    assert all(finding is not None for finding in batch)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            async with ClientSession() as session:
                status, body = await _post(session, port, batch)
                assert status == 200, body
                assert body["ingested"] == 3

        enqueued = []
        while not queue.empty():
            enqueued.append(queue.get_nowait())

        assert len(enqueued) == 3
        for item in enqueued:
            assert item["type"] == "finding"
            assert item["source"] == "webhook"
            finding = item["data"]
            assert finding["data_source"] == "decoy-farm"
            assert finding["severity"] == "high"
            assert finding["entity_context"]["src_ip"] == "203.0.113.7"
            assert finding["entity_context"]["decoy"] == "cowrie"

        # Each session stage carries its own technique hint: probe, guess,
        # execute — the chain triage escalates on.
        techniques = [set(item["data"]["mitre_predictions"]) for item in enqueued]
        assert {"T1595.001"} in techniques
        assert {"T1021.004"} in techniques
        assert {"T1059.004"} in techniques
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_smb_and_http_decoy_telemetry_become_findings():
    port = _free_port()
    poller = DataPoller(PollingConfig(webhook_token=TOKEN, webhook_port=port))
    queue = asyncio.Queue()
    poller.set_output_queue(queue)

    batch = [
        _ship(
            "opencanary",
            {
                "logtype": 5000,
                "src_host": "203.0.113.7",
                "dst_host": "10.0.5.12",
                "dst_port": 445,
                "node_id": "opencanary-node",
                "local_time": "2026-10-10 10:00:00",
                "logdata": {"SHARE": "FAKESHARE"},
            },
        ),
        _ship(
            "http-decoy",
            {
                "method": "POST",
                "path": "/login",
                "src_ip": "203.0.113.7",
                "username": "admin",
                "ts": "2026-10-10T10:00:02Z",
            },
        ),
    ]

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            async with ClientSession() as session:
                status, body = await _post(session, port, batch)
                assert status == 200, body
                assert body["ingested"] == 2

        enqueued = []
        while not queue.empty():
            enqueued.append(queue.get_nowait())

        by_kind = {
            item["data"]["entity_context"]["decoy"]: item["data"] for item in enqueued
        }
        assert set(by_kind) == {"opencanary", "fileportal-01"}
        assert by_kind["opencanary"]["mitre_predictions"] == {"T1021.002": 0.9}
        assert by_kind["fileportal-01"]["entity_context"]["path"] == "/login"
        assert by_kind["opencanary"]["data_source"] == "decoy-farm"
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_replayed_decoy_lines_ingest_once():
    """A crash between read and POST means a replay of the same log lines:
    the content-addressed finding ids must dedupe them on the daemon side."""
    port = _free_port()
    poller = DataPoller(PollingConfig(webhook_token=TOKEN, webhook_port=port))
    queue = asyncio.Queue()
    poller.set_output_queue(queue)

    record = {
        "eventid": "cowrie.session.connect",
        "src_ip": "203.0.113.7",
        "session": "sess-1",
        "timestamp": "2026-10-10T10:00:00Z",
    }
    batch = [_ship("cowrie", record), _ship("cowrie", record)]  # same line twice

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            async with ClientSession() as session:
                status, body = await _post(session, port, batch)
                assert status == 200, body
                assert body["ingested"] == 1
    finally:
        shutdown.set()
        await server

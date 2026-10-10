"""The webhook stamps findings with the origin-attestation verdict (#944).

Mirrors test_webhook_rejections.py: a real server on an ephemeral port, the
poller's own verification path, and a capture at the enqueue boundary — no
mock between the HTTP request and the finding that reaches the pipeline.
"""

import asyncio
import logging
import socket
import time
from unittest.mock import patch

import pytest
from aiohttp import ClientSession

from core import webhook_rejections as wr
from core.response.origin import OriginTrustIndex
from services.daemon.config import PollingConfig
from services.daemon.poller import DataPoller
from tests.security._origin_factory import Signer


class _Config:
    def get_disabled_integration_ids(self):
        return set()


class _FloodRecorder:
    """Stands in for the breaker's origin-flood face: one event per rejected
    request, matching ``ContainmentBreaker.note_origin_unverified``."""

    def __init__(self):
        self.calls = 0

    async def note_origin_unverified(self):
        self.calls += 1


async def _post(session, port, body, token="good", attestation=None):
    headers = {"Authorization": f"Bearer {token}"}
    if attestation is not None:
        headers["X-Vigil-Origin-Attestation"] = attestation
    for _ in range(50):
        try:
            async with session.post(
                f"http://127.0.0.1:{port}/ingest",
                json=body,
                headers=headers,
            ) as resp:
                return resp.status, await resp.json()
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("webhook server did not start")


def _make_poller(port, signer: Signer) -> tuple[DataPoller, _FloodRecorder, list]:
    poller = DataPoller(PollingConfig(webhook_token="good", webhook_port=port))
    # Inject the trust roots directly: the settings seed path is covered by
    # the verifier tests; here the poller under test gets a known root.
    poller._origin_index = OriginTrustIndex.from_entries([signer.trust_entry()])
    flood = _FloodRecorder()
    poller._origin_flood_sink = flood
    captured: list = []

    async def _capture(finding_data, source, dedup, finding_id):
        captured.append(dict(finding_data))
        return True

    poller._enqueue_finding = _capture
    return poller, flood, captured


@pytest.mark.asyncio
async def test_unsigned_finding_ingests_unverified(monkeypatch, caplog):
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    poller, flood, captured = _make_poller(port, Signer())
    caplog.set_level(logging.WARNING)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            async with ClientSession() as session:
                status, body = await _post(session, port, {"finding_id": "f-unsigned"})
                assert status == 200
                assert body["origin_verified"] is False
                assert captured[0]["origin_verified"] is False
                assert captured[0]["origin_id"] is None
                # An absent header is not an attack signal: no breaker feed,
                # no security log.
                assert flood.calls == 0
                assert not any(
                    "origin attestation rejected" in r.getMessage()
                    for r in caplog.records
                )
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_signed_finding_ingests_verified():
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            body = {
                "finding_id": "f-signed",
                "data_source": "webhook",
                "severity": "critical",
                "title": "attested",
            }
            header = signer.sign_finding(body)
            async with ClientSession() as session:
                status, resp = await _post(session, port, body, attestation=header)
                assert status == 200
                assert resp["origin_verified"] is True
                assert len(captured) == 1
                assert captured[0]["origin_verified"] is True
                assert captured[0]["origin_id"] == "sensor-edge-01"
                assert flood.calls == 0
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_batch_stamps_every_finding():
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            body = [{"finding_id": f"f-{i}"} for i in range(3)]
            header = signer.sign_finding(body)
            async with ClientSession() as session:
                status, resp = await _post(session, port, body, attestation=header)
                assert status == 200
                assert resp["origin_verified"] is True
                assert [c["origin_id"] for c in captured] == ["sensor-edge-01"] * 3
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_tampered_body_ingests_unverified_and_feeds_breaker(caplog):
    """The signature-transplant case: a valid header over a different body."""
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)
    caplog.set_level(logging.WARNING)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            # Signed over one body, posted with another: the attestation was
            # transplanted and must not verify.
            header = signer.sign_finding({"finding_id": "f-victim"})
            async with ClientSession() as session:
                status, resp = await _post(
                    session, port, {"finding_id": "f-forged"}, attestation=header
                )
                assert status == 200  # stored, not dropped
                assert resp["origin_verified"] is False
                assert captured[0]["origin_verified"] is False
                assert captured[0]["origin_id"] is None
                assert flood.calls == 1
                assert poller.stats["webhook_origin_unverified"] == 1
                assert any(
                    "origin attestation rejected" in r.getMessage()
                    for r in caplog.records
                )
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_unknown_key_ingests_unverified_and_feeds_breaker(caplog):
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)
    caplog.set_level(logging.WARNING)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            # A key the daemon never registered: the attacker's own.
            stranger = Signer(origin_id="stranger")
            header = stranger.sign_finding({"finding_id": "f-forged"})
            async with ClientSession() as session:
                status, resp = await _post(
                    session, port, {"finding_id": "f-forged"}, attestation=header
                )
                assert status == 200
                assert resp["origin_verified"] is False
                assert flood.calls == 1
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_stale_iat_ingests_unverified_and_feeds_breaker():
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            body = {"finding_id": "f-stale"}
            # Signed an hour ago: past the 300-second freshness window.
            header = signer.sign_finding(body, iat=int(time.time()) - 3600)
            async with ClientSession() as session:
                status, resp = await _post(session, port, body, attestation=header)
                assert status == 200
                assert resp["origin_verified"] is False
                assert flood.calls == 1
    finally:
        shutdown.set()
        await server


@pytest.mark.asyncio
async def test_replayed_jti_verifies_once_then_fails():
    wr._counts.clear()
    wr._log_state.clear()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    signer = Signer()
    poller, flood, captured = _make_poller(port, signer)

    shutdown = asyncio.Event()
    server = asyncio.create_task(poller._run_webhook_server(shutdown))
    try:
        with patch(
            "core.storage.config_service.get_config_service", return_value=_Config()
        ):
            body = {"finding_id": "f-replay"}
            header = signer.sign_finding(body)
            async with ClientSession() as session:
                status, first = await _post(session, port, body, attestation=header)
                assert first["origin_verified"] is True
                # Second delivery of the same bytes: the nonce is spent.
                status, second = await _post(session, port, body, attestation=header)
                assert status == 200
                assert second["origin_verified"] is False
                assert second["ingested"] == 0  # the finding dedup holds it
                # The replay fed the breaker before the dedup layer saw it.
                assert captured[0]["origin_verified"] is True
                assert flood.calls == 1
    finally:
        shutdown.set()
        await server

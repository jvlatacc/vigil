"""Health endpoint: one JSON line on VIGIL_EDGE_HEALTH_PORT."""

from __future__ import annotations

import asyncio
import json

from services.edge.app.health import HealthServer


def test_health_reports_state_and_tier(tmp_path) -> None:
    async def scenario() -> dict:
        server = HealthServer(
            port=0,  # ephemeral
            state_fn=lambda: "partitioned",
            tier_fn=lambda: "tier2",
            node_id="gw-test-01",
            data_dir=tmp_path,
        )
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]
        serve_task = asyncio.get_running_loop().create_task(server.serve())
        try:
            await asyncio.sleep(0.05)  # let serve_forever take the server
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            payload = await reader.read(65536)
            writer.close()
            return json.loads(payload.split(b"\r\n\r\n", 1)[1])
        finally:
            serve_task.cancel()
            await asyncio.gather(serve_task, return_exceptions=True)
            await server.stop()

    status = asyncio.run(scenario())
    assert status["service"] == "vigil-edge"
    assert status["node"] == "gw-test-01"
    assert status["state"] == "partitioned"
    assert status["tier"] == "tier2"


def test_unknown_path_is_404(tmp_path) -> None:
    async def scenario() -> int:
        server = HealthServer(
            port=0,
            state_fn=lambda: "synced",
            tier_fn=lambda: "tier2",
            node_id="gw-test-01",
            data_dir=tmp_path,
        )
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]
        serve_task = asyncio.get_running_loop().create_task(server.serve())
        try:
            await asyncio.sleep(0.05)
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /metrics HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            payload = await reader.read(65536)
            writer.close()
            return int(payload.split(b"\r\n")[0].split(b" ")[1])
        finally:
            serve_task.cancel()
            await asyncio.gather(serve_task, return_exceptions=True)
            await server.stop()

    assert asyncio.run(scenario()) == 404

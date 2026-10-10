"""Minimal health endpoint: ``GET /health`` on ``VIGIL_EDGE_HEALTH_PORT``.

Hand-rolled on ``asyncio.start_server`` rather than pulling a web framework
into the edge lockfile: the response is one JSON line, and the daemon must
stay schedulable on constrained nodes. Metrics exposure follows the central
daemon's pattern when the observability deliverable lands; state and tier are
what an operator curling a partitioned node needs first.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(
        self,
        *,
        port: int,
        state_fn: Callable[[], str],
        tier_fn: Callable[[], str],
        node_id: str,
        data_dir: Path,
    ) -> None:
        """``state_fn``/``tier_fn`` are 0-arg callables returning the current
        operating state and effective tier labels, read at request time."""
        self.port = port
        self._state_fn = state_fn
        self._tier_fn = tier_fn
        self._node_id = node_id
        self._data_dir = data_dir
        self._started_at = time.monotonic()
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, host="0.0.0.0", port=self.port
        )
        bound = (
            self._server.sockets[0].getsockname()[1]
            if self._server.sockets
            else self.port
        )
        logger.info("Edge health endpoint on :%s", bound)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def serve(self) -> None:
        """Run until cancelled; start() must have been called."""
        if self._server is None:
            await self.start()
        assert self._server is not None  # narrow for mypy
        async with self._server:
            await self._server.serve_forever()

    def status(self) -> dict[str, str | int]:
        return {
            "service": "vigil-edge",
            "node": self._node_id,
            "state": str(self._state_fn()),
            "tier": str(self._tier_fn()),
            "uptime_s": int(time.monotonic() - self._started_at),
            "data_dir": str(self._data_dir),
        }

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            # Drain request headers; the health endpoint reads nothing else.
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in (b"\r\n", b"\n", b""):
                    break
            path = (
                request_line.split(b" ")[1].decode(errors="replace")
                if request_line
                else ""
            )
            if path.startswith("/health"):
                body = json.dumps(self.status()).encode()
                await self._respond(writer, "200 OK", body)
            else:
                await self._respond(writer, "404 Not Found", b'{"error": "not found"}')
        except (TimeoutError, ConnectionError) as exc:
            logger.debug("Health probe ended: %s", exc)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, BrokenPipeError):
                pass

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, status: str, body: bytes) -> None:
        writer.write(
            b"HTTP/1.1 " + status.encode() + b"\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()

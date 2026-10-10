"""The JSON-lines observation tail (Suricata EVE and similar), the v1
pluggable input.

Passive by construction: the tail reads whatever flow/DNS/HTTP/TLS records a
sensor on the segment already writes — no agent is installed on monitored
hosts. Each complete JSON line normalizes to the gate's Observation; the raw
line stays in its file and the decision record cites its digest and
``file:offset`` reference.

Cold start follows the federation house rule: no backfill. The first sighting
of a file starts at EOF unless a saved offset from a previous boot matches
the same inode — a restart resumes where the previous boot left off, it does
not replay history (the server dedups replays, but not re-reading the whole
file is cheaper). Rotation (logrotate rename + recreate) reopens from the
start of the new file; any lines the old file had not flushed in the poll
gap are a telemetry gap, never an audit gap — the journal is the audit
record, the tail is only its input.

Malformed lines are counted and skipped, never fatal: a garbage line in a
log stream must not stop the defense loop.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
from datetime import UTC, datetime
from io import TextIOBase
from ipaddress import IPv4Network, IPv6Network, ip_address
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.edge.observations.base import Observation, digest_raw

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

Network = IPv4Network | IPv6Network


def _extract_domain(record: dict[str, Any]) -> str | None:
    """Domain candidates by event type: dns queries (rrname), http hostnames,
    tls SNI. A trailing dot from fully-qualified DNS names is stripped."""
    dns = record.get("dns")
    if isinstance(dns, dict) and isinstance(dns.get("rrname"), str):
        return dns["rrname"].rstrip(".") or None
    http = record.get("http")
    if isinstance(http, dict) and isinstance(http.get("hostname"), str):
        return http["hostname"].rstrip(".") or None
    tls = record.get("tls")
    if isinstance(tls, dict) and isinstance(tls.get("sni"), str):
        return tls["sni"].rstrip(".") or None
    return None


def infer_direction(src_ip: Any, dest_ip: Any, home_cidrs: tuple[Network, ...]) -> str:
    """Egress when the source is home and the destination is not; ingress
    the reverse; unknown otherwise — including when no home CIDRs are
    configured, which leaves the direction honest instead of guessed."""
    if not home_cidrs or not isinstance(src_ip, str) or not isinstance(dest_ip, str):
        return "unknown"
    try:
        src = ip_address(src_ip)
        dest = ip_address(dest_ip)
    except ValueError:
        return "unknown"
    src_home = any(src in net for net in home_cidrs)
    dest_home = any(dest in net for net in home_cidrs)
    if src_home and not dest_home:
        return "egress"
    if dest_home and not src_home:
        return "ingress"
    return "unknown"


def parse_eve_line(
    line: str, *, raw_ref: str, home_cidrs: tuple[Network, ...] = ()
) -> Observation | None:
    """One EVE JSON line -> Observation, or None when the line is not a
    usable record (unparseable JSON, missing timestamp or event_type)."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    event_type = record.get("event_type")
    timestamp_raw = record.get("timestamp")
    if not isinstance(event_type, str) or not isinstance(timestamp_raw, str):
        return None
    try:
        timestamp = datetime.fromisoformat(timestamp_raw)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    src_ip = record.get("src_ip")
    dest_ip = record.get("dest_ip")
    proto = record.get("proto")
    return Observation(
        timestamp=timestamp.astimezone(UTC),
        direction=infer_direction(src_ip, dest_ip, home_cidrs),
        src_ip=src_ip if isinstance(src_ip, str) else None,
        dest_ip=dest_ip if isinstance(dest_ip, str) else None,
        dest_domain=_extract_domain(record),
        proto=proto if isinstance(proto, str) else None,
        event_type=event_type,
        raw_digest=digest_raw(line.encode()),
        raw_ref=raw_ref,
    )


class FileTail:
    """JSON-lines file tail implementing ObservationInput: poll, normalize
    complete lines, pump to the handler, survive rotation and garbage."""

    name = "eve-file-tail"

    def __init__(
        self,
        path: Path,
        *,
        poll_seconds: float = 1.0,
        home_cidrs: Sequence[str] = (),
        state_dir: Path | None = None,
    ) -> None:
        self.path = path
        self.poll_seconds = poll_seconds
        self._home: tuple[Network, ...] = tuple(
            ipaddress.ip_network(cidr, strict=False)
            for cidr in home_cidrs
            if isinstance(cidr, str) and cidr.strip()
        )
        self.state_dir = state_dir
        self._handle: TextIOBase | None = None
        self._file_identity: tuple[int, int] | None = None
        self._offset = 0
        self._buffer = ""
        self._buffer_start = 0
        self._opened = False
        self.malformed_lines = 0

    # -- ObservationInput ---------------------------------------------------

    async def run(self, handler: Callable[[Observation], Awaitable[None]]) -> None:
        try:
            while True:
                for observation in self.poll_once():
                    await handler(observation)
                await asyncio.sleep(self.poll_seconds)
        finally:
            await self.close()

    async def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None
                self._file_identity = None

    # -- polling ------------------------------------------------------------

    def poll_once(self) -> list[Observation]:
        """Read newly arrived complete lines. Pure-I/O errors (the file
        existing but being unreadable) surface — they mean a real problem
        with the sensor feed, not with the data."""
        if not self._open_current():
            return []
        assert self._handle is not None
        chunk = self._handle.read()
        if not chunk and not self._buffer:
            return []
        chunk_start = self._offset
        self._offset += len(chunk.encode("utf-8"))
        data = self._buffer + chunk
        data_start = self._buffer_start if self._buffer else chunk_start

        lines = data.split("\n")
        self._buffer = lines.pop()
        consumed = sum(len(line.encode("utf-8")) + 1 for line in lines)
        self._buffer_start = data_start + consumed

        observations: list[Observation] = []
        position = data_start
        for line in lines:
            line_start = position
            position += len(line.encode("utf-8")) + 1
            if not line.strip():
                continue
            observation = parse_eve_line(
                line, raw_ref=f"{self.path}:{line_start}", home_cidrs=self._home
            )
            if observation is None:
                self.malformed_lines += 1
                logger.debug(
                    "tail skipping malformed line at %s:%d", self.path, line_start
                )
                continue
            observations.append(observation)
        if self._offset != chunk_start and self.state_dir is not None:
            self._save_state()
        return observations

    def _open_current(self) -> bool:
        """Track the file across rotation and truncation. First-ever open
        starts at EOF (no backfill) or at the saved offset for the same
        inode; a rotated file starts from its beginning."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return False
        identity = (stat.st_dev, stat.st_ino)
        rotated = False
        if self._handle is not None and identity != self._file_identity:
            logger.info("observation file rotated, following: %s", self.path)
            self._handle.close()
            self._handle = None
            rotated = True
        if self._handle is None:
            cold = not self._opened
            saved = self._load_state() if cold else None
            # The handle outlives this call by design (a tail, not a read).
            self._handle = open(self.path, "r", encoding="utf-8")  # noqa: SIM115
            self._file_identity = identity
            if cold:
                if (
                    saved is not None
                    and saved.get("dev") == stat.st_dev
                    and saved.get("inode") == stat.st_ino
                    and isinstance(saved.get("offset"), int)
                    and saved["offset"] <= stat.st_size
                ):
                    self._offset = saved["offset"]
                else:
                    self._offset = stat.st_size
                self._buffer = ""
                self._buffer_start = self._offset
                self._opened = True
            elif rotated:
                # A new inode is a new file: read it from the start, even when
                # it is larger than the old file's EOF offset. Lines the
                # previous file never flushed are a telemetry gap, never an
                # audit gap — the journal is the audit record.
                self._offset = 0
                self._buffer = ""
                self._buffer_start = 0
            if self._offset > stat.st_size:  # truncated in place
                logger.warning(
                    "observation file truncated, restarting at 0: %s", self.path
                )
                self._offset = 0
                self._buffer = ""
                self._buffer_start = 0
            self._handle.seek(self._offset)
        return True

    # -- offset persistence -------------------------------------------------

    def _state_path(self) -> Path | None:
        if self.state_dir is None:
            return None
        return self.state_dir / f"{self.path.name}.tail-offset.json"

    def _save_state(self) -> None:
        path = self._state_path()
        if path is None or self._file_identity is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "dev": self._file_identity[0],
                "inode": self._file_identity[1],
                "offset": self._offset,
            }
        )
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload)
        os.replace(tmp, path)

    def _load_state(self) -> dict[str, Any] | None:
        path = self._state_path()
        if path is None or not path.exists():
            return None
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            logger.warning("tail offset state unreadable (%s): %s", path, exc)
            return None
        return saved if isinstance(saved, dict) else None

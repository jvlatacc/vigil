#!/usr/bin/env python3
"""Seed the digital twin with a demo topology.

The twin's read API has no real feed behind it yet: until a host sensor or
an EDR/SIEM adapter posts to ``/api/v1/digital-twin/ingest``, the graph has
nothing to draw. This script loads the demo dataset — five devices, the
processes on them, and the connections they held — telling one
lateral-movement story an analyst can walk end to end:

    analyst-ws (SSH) ──► web-01  (nginx, internet-facing — compromised)
                              │  ssh client running as www-data
                              ▼
                             app-01  (pivot through the app tier)
                              │  ssh client running as www-data
                              ▼
                             db-01  (customer database)

The lobby camera and the analyst's browser add texture the story needs to
be readable: the camera's RTSP session back to the NVR, the browser session
into the DMZ box. Connections span all three ``connection_type`` values —
listening sockets, established streams, long-lived sessions — and one
unattributed outbound flow from db-01 shows a device-level connection (no
owning process).

The batch is built in the ingest API's payload shape — ``{source, devices[],
processes[], connections[]}``, processes referencing their device and
connections referencing their process by natural key. A connection the
sensor could not attribute to a process carries its ``device`` hostname
instead — a device-level observation.

Idempotency: every row carries the natural key the ingest upserts against
(``device_key`` / ``process_key`` / ``connection_key``), so running the
script again finds every row it wrote, updates the observed attributes, and
bumps ``last_seen`` — row counts never change. ``first_seen`` is written
once and never touched again, which is what makes the observation bookkeeping
survive re-seeding.

Key derivation (``host:<hostname>``, ``mac:<normalized>``, ``serial:<serial>``;
``{device_key}:{pid}:{name}``; ``{device_key}:{type}:{proto}:{lip}:{lport}:{rip}:{rport}``)
mirrors the format the models' tests use. The ingest service owns the same
derivation; if the two ever diverge, this file is the one to reconcile.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select  # noqa: E402

from core.storage.connection import init_database  # noqa: E402
from core.storage.models import (  # noqa: E402
    TwinConnection,
    TwinDevice,
    TwinProcess,
)
from core.storage.unit_of_work import unit_of_work  # noqa: E402
from core.time import utcnow  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("seed_digital_twin_demo")

DEMO_SOURCE = "seed"


# --- pure helpers: payload in, natural keys out --------------------------------


def normalize_mac(mac: Optional[str]) -> Optional[str]:
    """Normalize a MAC to the lower-case colon form ``aa:bb:cc:dd:ee:ff``.

    Accepts the common spellings (colons, dashes, dot-pairs, bare hex).
    Returns ``None`` for ``None``; unparseable input passes back lower-cased
    so a source's odd value is never silently dropped.
    """
    if mac is None:
        return None
    compact = mac.lower().replace(":", "").replace("-", "").replace(".", "")
    if len(compact) == 12 and all(c in "0123456789abcdef" for c in compact):
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    return mac.lower()


def device_key_for(device: Dict[str, Any]) -> str:
    """The natural key a device upserts against.

    The identity the source provides, in order of trust: hostname, then MAC,
    then serial — prefixed so two devices keyed on different identity types
    can never collide.
    """
    hostname = device.get("hostname")
    if hostname:
        return f"host:{hostname}"
    mac = normalize_mac(device.get("mac_address"))
    if mac:
        return f"mac:{mac}"
    serial = device.get("serial_number")
    if serial:
        return f"serial:{serial}"
    raise ValueError(
        "a device observation needs a hostname, MAC, or serial to be keyed"
    )


def process_key_for(device_key: str, proc: Dict[str, Any]) -> str:
    """A process upserts against its (device, pid, name) triple."""
    return f"{device_key}:{proc['pid']}:{proc['name']}"


def _key_part(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


def connection_key_for(device_key: str, conn: Dict[str, Any]) -> str:
    """A connection upserts against its device-scoped identifying 5-tuple.

    The device is part of the key: two hosts both bind ``0.0.0.0:22``, and
    the bare 5-tuple alone would collide on the table's unique index.
    """
    return ":".join(
        _key_part(part)
        for part in (
            device_key,
            conn.get("connection_type"),
            conn.get("protocol"),
            conn.get("local_ip"),
            conn.get("local_port"),
            conn.get("remote_ip"),
            conn.get("remote_port"),
        )
    )


# --- the demo dataset -----------------------------------------------------------


def build_demo_batch() -> Dict[str, Any]:
    """The demo topology, in the ingest payload's shape.

    Pure: returns the dict the ingest endpoint accepts (and this script's
    ``apply_batch`` applies), so the dataset can be asserted on without a
    database.
    """
    devices = [
        # The internet-facing entry point. MAC arrives upper-case on purpose:
        # normalization is the ingest's job, and the demo should prove it.
        {
            "hostname": "web-01",
            "mac_address": "0A:1B:2C:3D:4E:01",
            "serial_number": "C02X1234ABCD",
            "device_type": "server",
            "ip_address": "10.0.4.11",
            "os_info": "Ubuntu 24.04 LTS",
            "attributes": {"role": "internet-facing reverse proxy (DMZ)"},
        },
        {
            "hostname": "app-01",
            "mac_address": "0a:1b:2c:3d:4e:02",
            "serial_number": "C02X1234EF01",
            "device_type": "server",
            "ip_address": "10.0.8.21",
            "os_info": "Ubuntu 22.04 LTS",
            "attributes": {"role": "internal application server + NVR"},
        },
        {
            "hostname": "db-01",
            "mac_address": "0a:1b:2c:3d:4e:03",
            "serial_number": "C02X1234DB99",
            "device_type": "server",
            "ip_address": "10.0.12.30",
            "os_info": "Ubuntu 22.04 LTS",
            "attributes": {"role": "customer database"},
        },
        {
            "hostname": "analyst-ws",
            "mac_address": "0a:1b:2c:3d:4e:04",
            "serial_number": "DL3879XQ",
            "device_type": "workstation",
            "ip_address": "10.0.20.5",
            "os_info": "macOS 15.1",
            "attributes": {"role": "SOC analyst workstation"},
        },
        {
            "hostname": "cam-lobby",
            "mac_address": "0a:1b:2c:3d:4e:05",
            "serial_number": "CAM2F19",
            "device_type": "iot",
            "ip_address": "10.0.30.44",
            "os_info": "camera firmware 2.4.1",
            "attributes": {"role": "lobby camera"},
        },
    ]

    processes = [
        # web-01: the DMZ box.
        {
            "device": "web-01",
            "pid": 1204,
            "name": "nginx",
            "user": "www-data",
            "command": "nginx: worker process",
        },
        {
            "device": "web-01",
            "pid": 902,
            "name": "sshd",
            "user": "root",
            "command": "/usr/sbin/sshd -D",
        },
        {
            "device": "web-01",
            "pid": 3310,
            "name": "node_exporter",
            "user": "prometheus",
            "command": "/opt/node_exporter --web.listen-address=:9100",
        },
        # The tell: an ssh client running as the compromised nginx user.
        {
            "device": "web-01",
            "pid": 22401,
            "name": "ssh",
            "user": "www-data",
            "command": "ssh appuser@10.0.8.21",
            "attributes": {"note": "unauthorized — lateral-movement pivot"},
        },
        # app-01: the app tier, where the pivot lands.
        {
            "device": "app-01",
            "pid": 2201,
            "name": "gunicorn",
            "user": "www-data",
            "command": "gunicorn app:app -b 0.0.0.0:3000",
        },
        {
            "device": "app-01",
            "pid": 2202,
            "name": "gunicorn",
            "user": "www-data",
            "command": "gunicorn app:app -b 0.0.0.0:3000 (worker)",
        },
        {
            "device": "app-01",
            "pid": 902,
            "name": "sshd",
            "user": "root",
            "command": "/usr/sbin/sshd -D",
        },
        {
            "device": "app-01",
            "pid": 13100,
            "name": "ssh",
            "user": "www-data",
            "command": "ssh dbadmin@10.0.12.30",
            "attributes": {"note": "unauthorized — second hop toward the database"},
        },
        {
            "device": "app-01",
            "pid": 2400,
            "name": "nvr-streamd",
            "user": "nvr",
            "command": "/usr/bin/nvr-streamd --listen :554",
        },
        # db-01: the target.
        {
            "device": "db-01",
            "pid": 1076,
            "name": "postgres",
            "user": "postgres",
            "command": "postgres: writer",
        },
        {
            "device": "db-01",
            "pid": 1077,
            "name": "pgbouncer",
            "user": "postgres",
            "command": "/usr/sbin/pgbouncer -d /etc/pgbouncer.ini",
        },
        {
            "device": "db-01",
            "pid": 902,
            "name": "sshd",
            "user": "root",
            "command": "/usr/sbin/sshd -D",
        },
        # analyst-ws: the operator, and the story's opening session.
        {
            "device": "analyst-ws",
            "pid": 4416,
            "name": "Chrome",
            "user": "jdoe",
            "command": "/Applications/Google Chrome.app",
        },
        {
            "device": "analyst-ws",
            "pid": 51777,
            "name": "ssh",
            "user": "jdoe",
            "command": "ssh jdoe@web-01.vigil.local",
        },
        # cam-lobby: the IoT end of the texture.
        {
            "device": "cam-lobby",
            "pid": 810,
            "name": "rtsp-svc",
            "user": "root",
            "command": "/usr/bin/rtsp-svc --port 8004",
        },
    ]

    connections = [
        # --- web-01 ---------------------------------------------------------
        # Listening sockets (no remote end).
        {
            "process": {"device": "web-01", "pid": 1204, "name": "nginx"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 443,
            "state": "listen",
            "direction": "inbound",
        },
        {
            "process": {"device": "web-01", "pid": 902, "name": "sshd"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 22,
            "state": "listen",
            "direction": "inbound",
        },
        {
            "process": {"device": "web-01", "pid": 3310, "name": "node_exporter"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 9100,
            "state": "listen",
            "direction": "inbound",
        },
        # The analyst's browser against the public proxy — talks-to analyst-ws.
        {
            "process": {"device": "web-01", "pid": 1204, "name": "nginx"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.4.11",
            "local_port": 443,
            "remote_ip": "10.0.20.5",
            "remote_port": 52341,
            "state": "established",
            "direction": "inbound",
        },
        # nginx proxying to the app tier — talks-to app-01.
        {
            "process": {"device": "web-01", "pid": 1204, "name": "nginx"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.4.11",
            "local_port": 40212,
            "remote_ip": "10.0.8.21",
            "remote_port": 3000,
            "state": "established",
            "direction": "outbound",
        },
        # The pivot: web-01 ssh (as www-data) reaching app-01's sshd.
        {
            "process": {"device": "web-01", "pid": 22401, "name": "ssh"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.4.11",
            "local_port": 49152,
            "remote_ip": "10.0.8.21",
            "remote_port": 22,
            "state": "established",
            "direction": "outbound",
        },
        # --- app-01 ---------------------------------------------------------
        {
            "process": {"device": "app-01", "pid": 2201, "name": "gunicorn"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 3000,
            "state": "listen",
            "direction": "inbound",
        },
        {
            "process": {"device": "app-01", "pid": 902, "name": "sshd"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 22,
            "state": "listen",
            "direction": "inbound",
        },
        # The same proxy exchange, seen from the app side — talks-to web-01.
        {
            "process": {"device": "app-01", "pid": 2202, "name": "gunicorn"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 3000,
            "remote_ip": "10.0.4.11",
            "remote_port": 40212,
            "state": "established",
            "direction": "inbound",
        },
        # The pivot arriving — talks-to web-01.
        {
            "process": {"device": "app-01", "pid": 902, "name": "sshd"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 22,
            "remote_ip": "10.0.4.11",
            "remote_port": 49152,
            "state": "established",
            "direction": "inbound",
        },
        # The app tier's pooled connections to the database — the talks-to
        # edges the demo turns on: remote_ip is db-01's address.
        {
            "process": {"device": "app-01", "pid": 2202, "name": "gunicorn"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 51230,
            "remote_ip": "10.0.12.30",
            "remote_port": 5432,
            "state": "established",
            "direction": "outbound",
        },
        {
            "process": {"device": "app-01", "pid": 2202, "name": "gunicorn"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 51231,
            "remote_ip": "10.0.12.30",
            "remote_port": 5432,
            "state": "established",
            "direction": "outbound",
        },
        # The second hop: app-01 ssh toward db-01's sshd.
        {
            "process": {"device": "app-01", "pid": 13100, "name": "ssh"},
            "connection_type": "session",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 51990,
            "remote_ip": "10.0.12.30",
            "remote_port": 22,
            "state": "established",
            "direction": "outbound",
        },
        # The camera's RTSP session back to the NVR — talks-to cam-lobby.
        {
            "process": {"device": "app-01", "pid": 2400, "name": "nvr-streamd"},
            "connection_type": "session",
            "protocol": "tcp",
            "local_ip": "10.0.8.21",
            "local_port": 554,
            "remote_ip": "10.0.30.44",
            "remote_port": 50100,
            "state": "established",
            "direction": "inbound",
        },
        # --- db-01 ----------------------------------------------------------
        {
            "process": {"device": "db-01", "pid": 1076, "name": "postgres"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 5432,
            "state": "listen",
            "direction": "inbound",
        },
        {
            "process": {"device": "db-01", "pid": 1077, "name": "pgbouncer"},
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "127.0.0.1",
            "local_port": 6432,
            "state": "listen",
            "direction": "inbound",
        },
        # The database side of the pooled connections — talks-to app-01.
        {
            "process": {"device": "db-01", "pid": 1076, "name": "postgres"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.12.30",
            "local_port": 5432,
            "remote_ip": "10.0.8.21",
            "remote_port": 51230,
            "state": "established",
            "direction": "inbound",
        },
        {
            "process": {"device": "db-01", "pid": 1076, "name": "postgres"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.12.30",
            "local_port": 5432,
            "remote_ip": "10.0.8.21",
            "remote_port": 51231,
            "state": "established",
            "direction": "inbound",
        },
        # The second hop landing — talks-to app-01.
        {
            "process": {"device": "db-01", "pid": 902, "name": "sshd"},
            "connection_type": "session",
            "protocol": "tcp",
            "local_ip": "10.0.12.30",
            "local_port": 22,
            "remote_ip": "10.0.8.21",
            "remote_port": 51990,
            "state": "established",
            "direction": "inbound",
        },
        # Device-level: the sensor saw the flow but could not attribute it to
        # a PID. Exercises process_id = NULL (an unattributed outbound beacon).
        # A connection without a process carries its device by hostname.
        {
            "process": None,
            "device": "db-01",
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.12.30",
            "local_port": 47001,
            "remote_ip": "198.51.100.23",
            "remote_port": 443,
            "state": "established",
            "direction": "outbound",
        },
        # --- analyst-ws ------------------------------------------------------
        # mDNS listener over UDP — protocol texture beyond tcp.
        {
            "process": {"device": "analyst-ws", "pid": 4416, "name": "Chrome"},
            "connection_type": "socket",
            "protocol": "udp",
            "local_ip": "0.0.0.0",
            "local_port": 5353,
            "state": "listen",
            "direction": "inbound",
        },
        # The analyst's browser session into the DMZ — talks-to web-01.
        {
            "process": {"device": "analyst-ws", "pid": 4416, "name": "Chrome"},
            "connection_type": "stream",
            "protocol": "tcp",
            "local_ip": "10.0.20.5",
            "local_port": 52341,
            "remote_ip": "10.0.4.11",
            "remote_port": 443,
            "state": "established",
            "direction": "outbound",
        },
        # The story's opening: the analyst's SSH session into web-01.
        {
            "process": {"device": "analyst-ws", "pid": 51777, "name": "ssh"},
            "connection_type": "session",
            "protocol": "tcp",
            "local_ip": "10.0.20.5",
            "local_port": 51022,
            "remote_ip": "10.0.4.11",
            "remote_port": 22,
            "state": "established",
            "direction": "outbound",
        },
        # DNS over UDP — no device at 10.0.12.1, so no talks-to edge.
        {
            "process": {"device": "analyst-ws", "pid": 4416, "name": "Chrome"},
            "connection_type": "stream",
            "protocol": "udp",
            "local_ip": "10.0.20.5",
            "local_port": 53311,
            "remote_ip": "10.0.12.1",
            "remote_port": 53,
            "direction": "outbound",
        },
        # --- cam-lobby -------------------------------------------------------
        # The camera serving its stream — talks-to app-01.
        {
            "process": {"device": "cam-lobby", "pid": 810, "name": "rtsp-svc"},
            "connection_type": "session",
            "protocol": "tcp",
            "local_ip": "10.0.30.44",
            "local_port": 50100,
            "remote_ip": "10.0.8.21",
            "remote_port": 554,
            "state": "established",
            "direction": "outbound",
        },
        {
            "process": {"device": "cam-lobby", "pid": 810, "name": "rtsp-svc"},
            "connection_type": "socket",
            "protocol": "udp",
            "local_ip": "0.0.0.0",
            "local_port": 8004,
            "state": "listen",
            "direction": "inbound",
        },
    ]

    return {
        "source": DEMO_SOURCE,
        "devices": devices,
        "processes": processes,
        "connections": connections,
    }


# --- the apply step: the payload shape, upserted -------------------------------


def _upsert_device(session, device: Dict[str, Any]) -> TwinDevice:
    """Get-or-create a device by its natural key; refresh what it advertises."""
    device_key = device_key_for(device)
    row = session.scalars(select(TwinDevice).filter_by(device_key=device_key)).first()
    if row is None:
        row = TwinDevice(
            device_key=device_key, source=device.get("source", DEMO_SOURCE)
        )
        session.add(row)
        # Assign the PK now: a process on this device references it this batch.
        session.flush()
    row.hostname = device.get("hostname")
    row.mac_address = normalize_mac(device.get("mac_address"))
    row.serial_number = device.get("serial_number")
    row.device_type = device.get("device_type", "unknown")
    row.ip_address = device.get("ip_address")
    row.os_info = device.get("os_info")
    row.attributes = device.get("attributes")
    row.last_seen = utcnow()
    return row


def _upsert_process(
    session, proc: Dict[str, Any], device_row: TwinDevice
) -> TwinProcess:
    """Get-or-create a process under its (device, pid, name) natural key."""
    process_key = process_key_for(device_row.device_key, proc)
    row = session.scalars(
        select(TwinProcess).filter_by(process_key=process_key)
    ).first()
    if row is None:
        row = TwinProcess(
            process_key=process_key,
            device_id=device_row.id,
            pid=proc["pid"],
            name=proc["name"],
            source=proc.get("source", DEMO_SOURCE),
        )
        session.add(row)
        # Assign the PK now: a connection on this device references it this batch.
        session.flush()
    row.device_id = device_row.id
    row.user = proc.get("user")
    row.command = proc.get("command")
    row.attributes = proc.get("attributes")
    row.last_seen = utcnow()
    return row


def _upsert_connection(
    session,
    conn: Dict[str, Any],
    device_row: TwinDevice,
    process_row: Optional[TwinProcess],
) -> TwinConnection:
    """Get-or-create a connection under its 5-tuple natural key."""
    connection_key = connection_key_for(device_row.device_key, conn)
    row = session.scalars(
        select(TwinConnection).filter_by(connection_key=connection_key)
    ).first()
    if row is None:
        row = TwinConnection(
            connection_key=connection_key,
            device_id=device_row.id,
            source=conn.get("source", DEMO_SOURCE),
        )
        session.add(row)
    row.device_id = device_row.id
    row.process_id = process_row.id if process_row else None
    row.connection_type = conn["connection_type"]
    row.protocol = conn.get("protocol")
    row.local_ip = conn.get("local_ip")
    row.local_port = conn.get("local_port")
    row.remote_ip = conn.get("remote_ip")
    row.remote_port = conn.get("remote_port")
    row.state = conn.get("state")
    row.direction = conn.get("direction")
    row.attributes = conn.get("attributes")
    row.last_seen = utcnow()
    return row


def apply_batch(batch: Dict[str, Any]) -> Dict[str, int]:
    """Upsert one ingest-shaped batch; return the tables' row counts.

    One unit of work: the batch lands whole or not at all. Re-applying a
    batch updates the observed attributes and bumps ``last_seen``; row
    counts are the idempotency contract.
    """
    with unit_of_work() as session:
        # Devices first — every later reference resolves through them.
        device_rows: Dict[str, TwinDevice] = {}
        for device in batch["devices"]:
            row = _upsert_device(session, device)
            if device.get("hostname"):
                device_rows[device["hostname"]] = row

        process_rows: Dict[str, TwinProcess] = {}
        for proc in batch["processes"]:
            device_row = device_rows.get(proc.get("device"))
            if device_row is None:
                raise ValueError(
                    f"process references unknown device {proc.get('device')!r}"
                )
            process_rows[process_key_for(device_row.device_key, proc)] = (
                _upsert_process(session, proc, device_row)
            )

        for conn in batch["connections"]:
            device_row = device_rows.get(_conn_hostname(conn))
            if device_row is None:
                raise ValueError(
                    f"connection references unknown device {_conn_hostname(conn)!r}"
                )
            _upsert_connection(
                session,
                conn,
                device_row,
                _resolve_process(process_rows, device_row, conn),
            )

    return count_rows()


def _resolve_process(
    process_rows: Dict[str, TwinProcess],
    device_row: TwinDevice,
    conn: Dict[str, Any],
) -> Optional[TwinProcess]:
    """Map a connection's ``{device, pid, name}`` process reference to its row.

    ``None`` is the payload saying "the sensor could not attribute this flow
    to a process" — a device-level connection, not a dangling reference. A
    reference that names no process the batch carries is an ingest error and
    fails loudly here.
    """
    ref = conn.get("process")
    if ref is None:
        return None
    if ref.get("device") != device_row.hostname:
        raise ValueError(
            f"connection's process reference names device {ref.get('device')!r}, "
            f"but it was observed on {device_row.hostname!r}"
        )
    key = process_key_for(device_row.device_key, ref)
    row = process_rows.get(key)
    if row is None:
        raise ValueError(
            f"connection references process {key!r}, which the batch does not carry"
        )
    return row


def _conn_hostname(conn: Dict[str, Any]) -> Optional[str]:
    """The device a connection observation is about (its process's device)."""
    ref = conn.get("process")
    if ref:
        return ref.get("device")
    return conn.get("device")


def count_rows() -> Dict[str, int]:
    """Total rows per twin table — what run-twice must leave identical."""
    with unit_of_work() as session:
        return {
            "devices": session.query(TwinDevice).count(),
            "processes": session.query(TwinProcess).count(),
            "connections": session.query(TwinConnection).count(),
        }


def main() -> int:
    logger.info("Initializing database schema (create_all)...")
    init_database(echo=False, create_tables=True)

    batch = build_demo_batch()
    counts = apply_batch(batch)
    logger.info(
        "digital twin demo topology seeded: %d devices, %d processes, %d connections",
        counts["devices"],
        counts["processes"],
        counts["connections"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

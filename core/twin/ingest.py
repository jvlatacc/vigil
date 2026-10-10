"""The digital-twin ingest service: natural-key upserts and the graph read.

Two jobs, both session-passing and commit-free — the request's unit of work
owns the transaction, so every function here merely joins it:

**Ingest.** A batch carries observations, not identities: the server derives
each row's natural key (``device_key`` / ``process_key`` / ``connection_key``)
from the observation itself, so the same machine, process, or connection seen
twice — across posts, sources, or concurrent requests — lands on one row whose
``last_seen`` moved. Upserts are ``ON CONFLICT DO UPDATE`` against the unique
key indexes: two concurrent posts of the same batch serialize on the index and
the second updates the row the first created, instead of duplicating it or
dying on a check the ORM-level get-or-create pattern would race.

The derivation is pinned to the demo seed's (``scripts/seed_digital_twin_demo.py``
— ``device_key_for`` / ``process_key_for`` / ``connection_key_for``): the seed
must be re-runnable through this API — or alongside it — without duplicating a
single row. Device keys preserve the source's spelling (``host:web-01``), MACs
arrive schema-normalized, and missing connection-key parts render as ``-``. A
parity test (``tests/unit/twin/test_digital_twin_ingest.py``) fails when one
side drifts.

Field updates on conflict are ``coalesce(excluded, stored)`` — a re-observation
that omits a field never erases an earlier one (a host sensor that stops
reporting a serial does not unreport it), while a value that changed replaces
it. ``last_seen`` alone is set unconditionally: every observation is one,
whether or not anything else moved.

**Read.** ``build_graph_payload`` returns the layered graph — devices,
their processes, the connections those hold — plus the three edge families
the console renders: device *runs* process, process *binds* connection, and
the heuristic device *talks-to* device (a connection's ``remote_ip`` matching
another device's last-known ``ip_address`` — labeled heuristic because reused
or overlapping addresses can fabricate one).

Natural-key shapes (visible in the database for debugging, opaque to
callers): ``host:<hostname>`` / ``mac:<mac>`` / ``serial:<serial>`` for
devices — whichever identity the source provided, in that order; the device
key threaded through the composed keys of its processes and connections;
``{device_key}:{pid}:{name}`` and
``{device_key}:{type}:{protocol}:{local_ip}:{local_port}:{remote_ip}:{remote_port}``.
A composition longer than the 255-character key columns is truncated and
disambiguated with a SHA-256 suffix rather than rejected.
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.storage.models import TwinConnection, TwinDevice, TwinProcess
from core.storage.schemas.digital_twin import (
    TwinConnectionIn,
    TwinConnectionOut,
    TwinDeviceIn,
    TwinDeviceListResponse,
    TwinDeviceOut,
    TwinEdgeOut,
    TwinGraphPayload,
    TwinIngestBatch,
    TwinIngestResult,
    TwinProcessIn,
    TwinProcessOut,
)
from core.time import utcnow

_KEY_LIMIT = 255  # the *_key columns are String(255)

# (device_key, pid, name) -> (process_id, device_id), this batch's processes.
_ProcessKey = Tuple[str, int, str]

# A resolved device reference: the row's id and the natural key the row is
# keyed under — the key, not the caller's spelling, feeds later derivations.
_DeviceRef = Tuple[uuid.UUID, str]


class TwinReferenceError(ValueError):
    """A batch observation names a device or process no row has.

    Raised with the offending field path in the message (``processes[0].device:
    unknown device 'host:x'``); the router turns it into a 422 with that
    detail. Names what to fix, not what SQLAlchemy choked on.
    """


def _fit_key(raw: str) -> str:
    """A natural key that always fits its column.

    Readable while it composes to ≤255 characters; longer compositions (a
    maximum-length hostname threaded through a process key, IPv6 addresses'
    colons lengthening a connection key) truncate to a SHA-256-suffixed form —
    deterministic and idempotent like the readable one, and still unique
    across inputs.
    """
    if len(raw) <= _KEY_LIMIT:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{raw[: _KEY_LIMIT - 33]}:{digest}"


def derive_device_key(
    *,
    hostname: Optional[str] = None,
    mac_address: Optional[str] = None,
    serial_number: Optional[str] = None,
) -> str:
    """Derive a device's natural key: hostname, then MAC, then serial.

    The first identity the source provides decides — a feed that only knows
    MACs still gets one stable key per machine. Pinned to the seed's
    ``device_key_for``: the spelling is preserved verbatim (no case-folding —
    ``Web-01`` and ``web-01`` key differently, exactly as the seed treats
    them); MAC normalization happened at the schema boundary.
    """
    if hostname:
        return _fit_key(f"host:{hostname}")
    if mac_address:
        return _fit_key(f"mac:{mac_address}")
    if serial_number:
        return _fit_key(f"serial:{serial_number}")
    # The input schema refuses identity-less devices; this guards direct
    # callers of the service.
    raise TwinReferenceError(
        "a device needs at least one identity field: hostname, mac_address, "
        "or serial_number"
    )


def derive_process_key(device_key: str, pid: int, name: str) -> str:
    """A process is (device, pid, name) — the triple one observation window.

    ``device_key`` is the resolved device row's own key (``host:web-01``),
    never the reference string the caller spelled — the seed derives the same
    way, and that is what keeps a hostname-referenced re-post on the seed's
    rows instead of minting duplicates.
    """
    return _fit_key(f"{device_key}:{pid}:{name}")


def _key_part(value: Any) -> str:
    """One connection-key part: ``-`` when absent, else the string form.

    Mirrors the seed's ``_key_part`` exactly — a missing ``remote_ip`` must
    not render as an empty slot (``a::b``) on one side and ``-`` on the
    other, or the same observation keys twice.
    """
    return "-" if value in (None, "") else str(value)


def derive_connection_key(
    device_key: str,
    *,
    connection_type: str,
    protocol: Optional[str],
    local_ip: Optional[str],
    local_port: Optional[int],
    remote_ip: Optional[str],
    remote_port: Optional[int],
) -> str:
    """A connection is its 5-tuple, scoped to the device that reported it.

    The device is part of the key: two hosts both bind ``0.0.0.0:22``, and a
    bare 5-tuple would collide on the unique index. Absent parts render as
    ``-`` (the seed's ``_key_part``), so a listener with no remote and an
    established flow with one key distinctly. ``device_key`` is the resolved
    device row's own key, like ``derive_process_key``.
    """
    return _fit_key(
        ":".join(
            _key_part(part)
            for part in (
                device_key,
                connection_type,
                protocol,
                local_ip,
                local_port,
                remote_ip,
                remote_port,
            )
        )
    )


# --- ingest --------------------------------------------------------------------


def ingest_batch(session: Session, batch: TwinIngestBatch) -> TwinIngestResult:
    """Upsert one observation batch; joins the caller's transaction.

    Devices are upserted before the processes that reference them, processes
    before the connections that reference them, whatever order the arrays
    arrived in. A reference the batch itself just created resolves locally;
    one from an earlier ingest resolves by its natural key or hostname; one
    that resolves to neither is a :class:`TwinReferenceError` (a 422 at the
    router), and the request's rollback discards the partial batch.

    Returns counts of the observations processed, per entity class.
    """
    device_refs: Dict[str, _DeviceRef] = {}
    process_refs: Dict[_ProcessKey, Tuple[uuid.UUID, uuid.UUID]] = {}
    # Attribution inside one connection iteration: a process id when the flow
    # names one, None for a device-level observation.
    process_id: uuid.UUID | None

    for device in batch.devices:
        key = derive_device_key(
            hostname=device.hostname,
            mac_address=device.mac_address,
            serial_number=device.serial_number,
        )
        device_id = _upsert_device(session, batch.source, device, key)
        device_refs[key] = (device_id, key)
        # Hostname-only sources (the demo seed among them) reference devices
        # by bare hostname; register that spelling onto the same row.
        if device.hostname:
            device_refs.setdefault(device.hostname, (device_id, key))

    for proc in batch.processes:
        device_id, device_key = _resolve_device(
            session, proc.device, device_refs, field="processes[].device"
        )
        key = derive_process_key(device_key, proc.pid, proc.name)
        process_id = _upsert_process(session, batch.source, proc, key, device_id)
        process_refs[(device_key, proc.pid, proc.name)] = (process_id, device_id)

    for conn in batch.connections:
        if conn.process is not None:
            device_id, device_key = _resolve_device(
                session,
                conn.process.device,
                device_refs,
                field="connections[].process.device",
            )
            resolved = process_refs.get(
                (device_key, conn.process.pid, conn.process.name)
            )
            if resolved is None:
                process_id = _lookup_process(
                    session, device_key, conn.process.pid, conn.process.name
                )
                if process_id is None:
                    raise TwinReferenceError(
                        f"connections[].process: no process "
                        f"({conn.process.device}, pid {conn.process.pid}, "
                        f"{conn.process.name!r}) — post the process in this "
                        "batch or an earlier ingest"
                    )
            else:
                process_id = resolved[0]
            # A connection naming a process has that process's device; an
            # explicit device ref naming a different row is a caller bug.
            if conn.device is not None:
                explicit_id, _ = _resolve_device(
                    session, conn.device, device_refs, field="connections[].device"
                )
                if explicit_id != device_id:
                    raise TwinReferenceError(
                        f"connections[].device: {conn.device!r} does not name "
                        f"the same device as the process reference "
                        f"({conn.process.device!r})"
                    )
        else:
            # Device-level observation: the sensor saw the flow but could
            # not attribute it to a process. The connection still lands, at
            # device level — never dropped, never dangling.
            process_id = None
            device_id, device_key = _resolve_device(
                session, conn.device or "", device_refs, field="connections[].device"
            )

        key = derive_connection_key(
            device_key,
            connection_type=conn.connection_type,
            protocol=conn.protocol,
            local_ip=conn.local_ip,
            local_port=conn.local_port,
            remote_ip=conn.remote_ip,
            remote_port=conn.remote_port,
        )
        _upsert_connection(
            session,
            batch.source,
            conn,
            key,
            device_id=device_id,
            process_id=process_id,
        )

    return TwinIngestResult(
        source=batch.source,
        devices=len(batch.devices),
        processes=len(batch.processes),
        connections=len(batch.connections),
    )


def _resolve_device(
    session: Session,
    device_ref: str,
    batch_local: Dict[str, _DeviceRef],
    field: str,
) -> _DeviceRef:
    """Resolve a device reference to its row's (id, natural key).

    A reference is the device's ``device_key`` (what ``GET /devices``
    exposes) or the hostname the observation carried — the form the demo
    seed and hostname-only sources use. This batch's own devices first (the
    map holds both spellings), then rows earlier ingests created: exact
    natural key, then the hostname column, deterministically ordered.
    """
    resolved = batch_local.get(device_ref)
    if resolved is not None:
        return resolved
    device_id = session.scalars(
        select(TwinDevice.id).where(TwinDevice.device_key == device_ref)
    ).first()
    if device_id is not None:
        return device_id, device_ref
    row = session.scalars(
        select(TwinDevice)
        .where(TwinDevice.hostname == device_ref)
        .order_by(TwinDevice.device_key)
    ).first()
    if row is not None:
        return row.id, row.device_key
    raise TwinReferenceError(
        f"{field}: unknown device {device_ref!r} — post the device in "
        "this batch or an earlier ingest"
    )


def _lookup_process(
    session: Session, device_key: str, pid: int, name: str
) -> Optional[uuid.UUID]:
    """Resolve a process reference against rows earlier ingests created.

    ``device_key`` is the resolved device row's own key — matching how the
    row's ``process_key`` was itself derived.
    """
    key = derive_process_key(device_key, pid, name)
    return session.scalars(
        select(TwinProcess.id).where(TwinProcess.process_key == key)
    ).first()


def _upsert_device(
    session: Session, source: str, item: TwinDeviceIn, key: str
) -> uuid.UUID:
    """One device observation: insert, or refresh the row that key already has."""
    stmt = pg_insert(TwinDevice).values(
        device_key=key,
        # The ingest clock owns observation bookkeeping: first_seen is set
        # here rather than left to the model's column default, so first and
        # last come from one clock (and tests can pin both).
        first_seen=utcnow(),
        hostname=item.hostname,
        mac_address=item.mac_address,
        serial_number=item.serial_number,
        device_type=item.device_type or "unknown",
        ip_address=item.ip_address,
        os_info=item.os_info,
        attributes=item.attributes,
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[TwinDevice.device_key],
        set_={
            "hostname": func.coalesce(stmt.excluded.hostname, TwinDevice.hostname),
            "mac_address": func.coalesce(
                stmt.excluded.mac_address, TwinDevice.mac_address
            ),
            "serial_number": func.coalesce(
                stmt.excluded.serial_number, TwinDevice.serial_number
            ),
            "device_type": func.coalesce(
                stmt.excluded.device_type, TwinDevice.device_type
            ),
            "ip_address": func.coalesce(
                stmt.excluded.ip_address, TwinDevice.ip_address
            ),
            "os_info": func.coalesce(stmt.excluded.os_info, TwinDevice.os_info),
            "attributes": func.coalesce(
                stmt.excluded.attributes, TwinDevice.attributes
            ),
            "last_seen": utcnow(),
        },
    )
    session.execute(stmt)
    # The upsert guarantees exactly one row under this key in this transaction;
    # .one() turns a violated invariant into a loud error, not a silent None.
    return session.scalars(
        select(TwinDevice.id).where(TwinDevice.device_key == key)
    ).one()


def _upsert_process(
    session: Session,
    source: str,
    item: TwinProcessIn,
    key: str,
    device_id: uuid.UUID,
) -> uuid.UUID:
    """One process observation; identity (device, pid, name) never moves."""
    stmt = pg_insert(TwinProcess).values(
        process_key=key,
        # Same as the device upsert: one clock for first_seen/last_seen.
        first_seen=utcnow(),
        device_id=device_id,
        pid=item.pid,
        name=item.name,
        user=item.user,
        command=item.command,
        started_at=item.started_at,
        attributes=item.attributes,
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[TwinProcess.process_key],
        set_={
            "user": func.coalesce(stmt.excluded.user, TwinProcess.user),
            "command": func.coalesce(stmt.excluded.command, TwinProcess.command),
            "started_at": func.coalesce(
                stmt.excluded.started_at, TwinProcess.started_at
            ),
            "attributes": func.coalesce(
                stmt.excluded.attributes, TwinProcess.attributes
            ),
            "last_seen": utcnow(),
        },
    )
    session.execute(stmt)
    # Same invariant as the device upsert: .one() over .first().
    return session.scalars(
        select(TwinProcess.id).where(TwinProcess.process_key == key)
    ).one()


def _upsert_connection(
    session: Session,
    source: str,
    item: TwinConnectionIn,
    key: str,
    *,
    device_id: uuid.UUID,
    process_id: Optional[uuid.UUID],
) -> None:
    """One connection observation.

    The 5-tuple is identity and never moves; ``process_id`` is attribution —
    a later observation that could not attribute the flow keeps the earlier
    one rather than demoting the row to device level.
    """
    stmt = pg_insert(TwinConnection).values(
        connection_key=key,
        # Same as the device upsert: one clock for first_seen/last_seen.
        first_seen=utcnow(),
        device_id=device_id,
        process_id=process_id,
        connection_type=item.connection_type,
        protocol=item.protocol,
        local_ip=item.local_ip,
        local_port=item.local_port,
        remote_ip=item.remote_ip,
        remote_port=item.remote_port,
        state=item.state,
        direction=item.direction,
        started_at=item.started_at,
        attributes=item.attributes,
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[TwinConnection.connection_key],
        set_={
            "process_id": func.coalesce(
                stmt.excluded.process_id, TwinConnection.process_id
            ),
            "protocol": func.coalesce(stmt.excluded.protocol, TwinConnection.protocol),
            "state": func.coalesce(stmt.excluded.state, TwinConnection.state),
            "direction": func.coalesce(
                stmt.excluded.direction, TwinConnection.direction
            ),
            "started_at": func.coalesce(
                stmt.excluded.started_at, TwinConnection.started_at
            ),
            "attributes": func.coalesce(
                stmt.excluded.attributes, TwinConnection.attributes
            ),
            "last_seen": utcnow(),
        },
    )
    session.execute(stmt)


# --- read ----------------------------------------------------------------------


def list_devices(session: Session) -> TwinDeviceListResponse:
    """Every known device, natural key first — the table/debugging read."""
    rows = session.scalars(select(TwinDevice).order_by(TwinDevice.device_key)).all()
    devices = [TwinDeviceOut.model_validate(row) for row in rows]
    return TwinDeviceListResponse(devices=devices, total=len(devices))


def build_graph_payload(
    session: Session,
    *,
    since: Optional[datetime] = None,
    device_id: Optional[uuid.UUID] = None,
) -> TwinGraphPayload:
    """The layered graph: entities plus the derived edges between them.

    ``since`` keeps only rows re-observed at/after the instant (a feed's
    incremental read); ``device_id`` scopes to one device — its processes and
    connections, with cross-device edges only to remotes the filtered payload
    still names. Either way lists order by natural key, so the same entity
    set always serializes identically.
    """
    device_query = select(TwinDevice).order_by(TwinDevice.device_key)
    if since is not None:
        device_query = device_query.where(TwinDevice.last_seen >= since)
    if device_id is not None:
        device_query = device_query.where(TwinDevice.id == device_id)
    device_rows = list(session.scalars(device_query))

    if not device_rows:
        return TwinGraphPayload(generated_at=utcnow())

    device_ids = [row.id for row in device_rows]

    process_query = (
        select(TwinProcess)
        .where(TwinProcess.device_id.in_(device_ids))
        .order_by(TwinProcess.process_key)
    )
    connection_query = (
        select(TwinConnection)
        .where(TwinConnection.device_id.in_(device_ids))
        .order_by(TwinConnection.connection_key)
    )
    if since is not None:
        process_query = process_query.where(TwinProcess.last_seen >= since)
        connection_query = connection_query.where(TwinConnection.last_seen >= since)

    processes = [
        TwinProcessOut.model_validate(row) for row in session.scalars(process_query)
    ]
    connections = [
        TwinConnectionOut.model_validate(row)
        for row in session.scalars(connection_query)
    ]
    devices = [TwinDeviceOut.model_validate(row) for row in device_rows]

    return TwinGraphPayload(
        generated_at=utcnow(),
        devices=devices,
        processes=processes,
        connections=connections,
        edges=derive_edges(devices, processes, connections),
    )


def derive_edges(
    devices: List[TwinDeviceOut],
    processes: List[TwinProcessOut],
    connections: List[TwinConnectionOut],
) -> List[TwinEdgeOut]:
    """The three edge families, derived from entity lists — pure and order-stable.

    ``runs`` joins every process to its device, ``binds`` every attributed
    connection to its process. ``talks-to`` matches a connection's
    ``remote_ip`` against the device map (first device to claim an address in
    payload order wins), skips the device's own connections to itself, and
    collapses repeated observations of one pair into one edge — mirroring the
    console's own mappers. Edges referencing entities the payload does not
    name are never emitted, so no client sees a dangling edge.
    """
    device_ids = {d.id for d in devices}
    process_ids = {p.id for p in processes}

    edges: List[TwinEdgeOut] = []
    for process in processes:
        if process.device_id in device_ids:
            edges.append(
                TwinEdgeOut(
                    id=f"runs:{process.device_id}:{process.id}",
                    source=str(process.device_id),
                    target=str(process.id),
                    kind="runs",
                )
            )
    for connection in connections:
        if (
            connection.process_id is not None
            and connection.process_id in process_ids
            and connection.device_id in device_ids
        ):
            edges.append(
                TwinEdgeOut(
                    id=f"binds:{connection.process_id}:{connection.id}",
                    source=str(connection.process_id),
                    target=str(connection.id),
                    kind="binds",
                )
            )

    device_by_ip: Dict[str, uuid.UUID] = {}
    for device in devices:
        if device.ip_address and device.ip_address not in device_by_ip:
            device_by_ip[device.ip_address] = device.id

    seen_pairs = set()
    for connection in connections:
        remote_id = (
            device_by_ip.get(connection.remote_ip) if connection.remote_ip else None
        )
        if remote_id is None or remote_id == connection.device_id:
            continue
        pair = (connection.device_id, remote_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append(
            TwinEdgeOut(
                id=f"talks-to:{connection.device_id}->{remote_id}",
                source=str(connection.device_id),
                target=str(remote_id),
                kind="talks-to",
                heuristic=True,
            )
        )
    return edges

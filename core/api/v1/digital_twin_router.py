"""Digital twin — versioned contract surface (``/api/v1/digital-twin``).

The observation ingest an external feed relies on (a host sensor, a seed
script, an NDR adapter) and the layered graph reads the console consumes.
The twin's vocabulary — devices, processes, connections — is the settled
part; the upsert and read logic lives in ``core.twin.ingest``, session-passing
and commit-free, so every route here joins the request's unit of work.

Routes answer at the versioned paths and at their pre-version aliases
(``legacy_prefixes``): one handler set, two addresses, the v1 contract
convention. Every route is ``Auth.REQUIRED`` — MACs and serials are sensitive
inventory, and nothing about the twin is public.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.schemas.digital_twin import (
    TwinDeviceListResponse,
    TwinGraphPayload,
    TwinIngestBatch,
    TwinIngestResult,
)
from core.twin.ingest import (
    TwinReferenceError,
    build_graph_payload,
    ingest_batch,
    list_devices,
)

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/v1/digital-twin",
    tags=["digital-twin"],
    auth=Auth.REQUIRED,
    legacy_prefixes=("/api/digital-twin",),
)


@router.post("/ingest", response_model=TwinIngestResult)
def ingest_observations(
    batch: TwinIngestBatch, session: UnitOfWorkSession
) -> TwinIngestResult:
    """Idempotent upsert of device/process/connection observations.

    The server derives each row's natural key from the observation, so
    re-posting a batch updates ``last_seen`` and changes no row counts —
    the "still here" signal a polling feed sends. References between rows
    (a process's device, a connection's process) are natural keys the batch
    or an earlier ingest created; an unknown one is a 422 naming the field.
    """
    try:
        return ingest_batch(session, batch)
    except TwinReferenceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/graph", response_model=TwinGraphPayload)
def get_graph(
    session: UnitOfWorkSession,
    since: Optional[datetime] = Query(
        None,
        description="Keep only entities re-observed at or after this instant.",
    ),
    device_id: Optional[uuid.UUID] = Query(
        None,
        description="Scope the graph to one device: its processes and "
        "connections, with talks-to edges only to remotes the scoped "
        "payload still names.",
    ),
) -> TwinGraphPayload:
    """The whole twin in one payload: devices, processes, connections, edges.

    Every node carries its entity attributes — MAC, serial, PID, the
    connection 5-tuple, type. Edges: device ``runs`` process, process
    ``binds`` connection, and the heuristic device ``talks-to`` device where
    a connection's ``remote_ip`` matches another known device's last-known
    ``ip_address`` (``heuristic=true`` — reused addresses can fabricate one).
    """
    return build_graph_payload(session, since=since, device_id=device_id)


@router.get("/devices", response_model=TwinDeviceListResponse)
def get_devices(session: UnitOfWorkSession) -> TwinDeviceListResponse:
    """The flat device list — tables and debugging, ``device_key`` included."""
    return list_devices(session)

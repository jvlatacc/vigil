"""Wire schemas for the digital-twin ingest and graph API.

Served by ``core.api.v1.digital_twin_router``; the upsert and read logic
lives in ``core.twin.ingest``. These are the only twin wire schemas — this
module is the observation surface: feeds POST device/process/connection
observations and the graph endpoint reads back the layered map.

Input schemas are strict where the columns are typed enums (``connection_type``,
``direction``) and bounded where a column is a fixed ``String`` — a value that
would overflow a column must be a 422 with field detail, never a 500 from the
driver. Output schemas mirror the merged frontend wire types
(``clients/web/src/screens/twin/types.ts``) plus the columns the screen does
not name yet (the ``*_key`` natural keys references are built from, ``os_info``,
``attributes``).
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from core.storage.schemas.base import IsoDateTime, OptDateTime, ORMSchema

# The three connection classes the twin distinguishes — mirrors
# TWIN_CONNECTION_TYPES (core/storage/models/digital_twin.py), whose check
# constraint is the database's copy of this Literal.
ConnectionType = Literal["socket", "stream", "session"]

EdgeKind = Literal["runs", "binds", "talks-to"]

_HEX_PAIRS = re.compile(r"^[0-9a-f]{12}$")


def normalize_mac(value: str) -> str:
    """Normalize a MAC address to the column's ``aa:bb:cc:dd:ee:ff`` form.

    Accepts the spellings sources actually send — ``AA:BB:CC:DD:EE:FF``,
    ``aa-bb-cc-dd-ee-ff``, ``aabb.ccdd.eeff``, ``AABBCCDDEEFF`` — and raises
    ``ValueError`` for anything else, so a malformed identity is a 422 at the
    schema boundary instead of an unmatchable index entry.

    The stored form is what the ingest indexes and what equal MACs compare
    against, so every feed's spelling of one address lands on one value.
    """
    cleaned = re.sub(r"[ .:\-]", "", value.strip().lower())
    if not _HEX_PAIRS.fullmatch(cleaned):
        raise ValueError(f"{value!r} is not a MAC address")
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


# --- ingest (request) schemas -------------------------------------------------
# References are natural keys the server derived on an earlier observation
# (``GET /devices`` returns them) or that earlier rows of the same batch
# created — never client-invented UUIDs.


class TwinDeviceIn(BaseModel):
    """One device observation.

    The identity fields (``hostname``, ``mac_address``, ``serial_number``) are
    what the ingest derives the ``device_key`` from, so at least one is
    required; everything else is the last-known state of the machine.
    """

    hostname: Optional[str] = Field(None, max_length=250)
    mac_address: Optional[str] = Field(None, max_length=64)
    serial_number: Optional[str] = Field(None, max_length=64)
    # Open vocabulary on purpose (server | workstation | appliance | iot | ...):
    # a check constraint would turn the next source's noun into a 422.
    device_type: Optional[str] = Field(None, max_length=30)
    ip_address: Optional[str] = Field(None, max_length=45)
    os_info: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    @field_validator("mac_address")
    @classmethod
    def _normalize_mac(cls, value: Optional[str]) -> Optional[str]:
        return normalize_mac(value) if value else value

    @model_validator(mode="after")
    def _needs_identity(self) -> "TwinDeviceIn":
        if not (self.hostname or self.mac_address or self.serial_number):
            raise ValueError(
                "a device needs at least one identity field: hostname, "
                "mac_address, or serial_number"
            )
        return self


class TwinProcessIn(BaseModel):
    """One process observation, on the device named by ``device``."""

    device: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "device_key of the device the process ran on, or the hostname "
            "the device was observed under"
        ),
    )
    pid: int = Field(ge=0, le=2147483647)
    name: str = Field(min_length=1, max_length=255)
    user: Optional[str] = Field(None, max_length=100)
    command: Optional[str] = None
    started_at: Optional[datetime] = None
    attributes: Optional[Dict[str, Any]] = None


class TwinProcessRef(BaseModel):
    """Names an already-observed process by its natural key."""

    device: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "device_key of the device the process ran on, or the hostname "
            "the device was observed under"
        ),
    )
    pid: int = Field(ge=0, le=2147483647)
    name: str = Field(min_length=1, max_length=255)


class TwinConnectionIn(BaseModel):
    """One connection observation.

    A connection belongs to its device — named directly by ``device`` or,
    when the source could attribute it, implied by the owning ``process``
    (whose ``device`` is the connection's device). Naming neither is the one
    shape the twin cannot place, so it is refused here.
    """

    device: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description=(
            "device_key, or the hostname the device was observed under; "
            "implied by `process` when omitted, and when both are given "
            "they must resolve to the same device"
        ),
    )
    process: Optional[TwinProcessRef] = None
    connection_type: ConnectionType
    protocol: Optional[str] = Field(None, max_length=16)
    local_ip: Optional[str] = Field(None, max_length=45)
    local_port: Optional[int] = Field(None, ge=0, le=65535)
    remote_ip: Optional[str] = Field(None, max_length=45)
    remote_port: Optional[int] = Field(None, ge=0, le=65535)
    state: Optional[str] = Field(None, max_length=30)
    direction: Optional[Literal["inbound", "outbound"]] = None
    started_at: Optional[datetime] = None
    attributes: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _needs_device(self) -> "TwinConnectionIn":
        if not self.device and not self.process:
            raise ValueError(
                "a connection needs a device reference or a process reference "
                "(which names its device)"
            )
        return self


class TwinIngestBatch(BaseModel):
    """One observation envelope from one feed: the source and what it saw.

    Re-posting a batch is safe and meaningful — it is how a feed says "still
    here": row counts stay stable and every re-observed row's ``last_seen``
    moves forward. A feed aggregating several vendors posts one batch per
    source.
    """

    source: str = Field(min_length=1, max_length=50)
    devices: List[TwinDeviceIn] = Field(default_factory=list)
    processes: List[TwinProcessIn] = Field(default_factory=list)
    connections: List[TwinConnectionIn] = Field(default_factory=list)


class TwinIngestResult(BaseModel):
    """Counts of observations the batch carried, per entity class.

    These echo the batch, not the database: idempotency means a re-post
    returns the same numbers while the row counts stay put.
    """

    source: str
    devices: int
    processes: int
    connections: int


# --- graph (response) schemas -------------------------------------------------


class TwinDeviceOut(ORMSchema):
    """A device as the API returns it — physical identity plus last-known state."""

    id: Any  # uuid.UUID; serialized as a string
    device_key: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    device_type: str
    ip_address: Optional[str] = None
    os_info: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    source: str
    first_seen: IsoDateTime
    last_seen: IsoDateTime


class TwinProcessOut(ORMSchema):
    """A process as the API returns it."""

    id: Any  # uuid.UUID; serialized as a string
    device_id: Any  # uuid.UUID; serialized as a string
    pid: int
    name: str
    user: Optional[str] = None
    command: Optional[str] = None
    started_at: OptDateTime = None
    attributes: Optional[Dict[str, Any]] = None
    source: str
    first_seen: IsoDateTime
    last_seen: IsoDateTime


class TwinConnectionOut(ORMSchema):
    """A connection as the API returns it — the identifying 5-tuple included."""

    id: Any  # uuid.UUID; serialized as a string
    device_id: Any  # uuid.UUID; serialized as a string
    process_id: Optional[Any] = None  # uuid.UUID | None; serialized as a string
    connection_type: ConnectionType
    protocol: Optional[str] = None
    local_ip: Optional[str] = None
    local_port: Optional[int] = None
    remote_ip: Optional[str] = None
    remote_port: Optional[int] = None
    state: Optional[str] = None
    direction: Optional[str] = None
    started_at: OptDateTime = None
    attributes: Optional[Dict[str, Any]] = None
    source: str
    first_seen: IsoDateTime
    last_seen: IsoDateTime


class TwinEdgeOut(BaseModel):
    """One derived relationship between two graph nodes.

    ``source``/``target`` are the entity ids the payload's own lists use, so
    a client can join edges to nodes without a second lookup. ``runs`` and
    ``binds`` are structural facts; ``talks-to`` is the v1 heuristic (a
    connection's ``remote_ip`` matching another device's last-known
    ``ip_address``) and carries ``heuristic=True`` — reused or overlapping
    addresses can fabricate one.
    """

    id: str
    source: str
    target: str
    kind: EdgeKind
    heuristic: bool = False


class TwinGraphPayload(BaseModel):
    """The whole twin in one payload; every node carries its entity attributes.

    The three entity lists are the wire shape the console screen consumes;
    ``edges`` is the same derivation server-side (``runs`` device→process,
    ``binds`` process→connection, heuristic ``talks-to`` device→device) for
    callers that would rather not re-derive it.
    """

    generated_at: IsoDateTime
    devices: List[TwinDeviceOut] = Field(default_factory=list)
    processes: List[TwinProcessOut] = Field(default_factory=list)
    connections: List[TwinConnectionOut] = Field(default_factory=list)
    edges: List[TwinEdgeOut] = Field(default_factory=list)


class TwinDeviceListResponse(BaseModel):
    """The flat device list tables and debugging read; ``device_key`` is here."""

    devices: List[TwinDeviceOut] = Field(default_factory=list)
    total: int

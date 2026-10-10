"""Digital-twin ORM models: devices, processes, connections.

The physical-to-logical map the console's digital-twin graph reads: a
device is a physical resource (MAC address, serial number) a host sensor
or inventory feed observed; the processes that ran on it; and the network
connections — sockets, streams, sessions — those processes held. The
ingest API (a later PR) upserts observations against the ``*_key``
natural keys, so re-posting a batch updates ``last_seen`` and changes no
row counts; the graph endpoint pivots between the layers.

The ``Twin`` prefix keeps these clear of the chat ``Conversation``
model's "session" and the findings' free-form ``entity_context`` JSONB —
building on that JSONB is exactly the weakness this surface exists to
fix: unindexed, untyped, uncorrelatable.

Schema and rationale: ``infra/database/init/42_digital_twin.sql``.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

# The three connection classes the twin distinguishes. "session" is the
# long-lived exchange (a TLS session, a UDP flow), "stream" the ordered
# byte pipe, "socket" the bare endpoint binding. Validated in the database
# by check constraint; the ingest API restates it as a Pydantic Literal.
TWIN_CONNECTION_TYPES = ("socket", "stream", "session")


class TwinDevice(Base):
    """One physical resource the twin knows about.

    A row is an observed inventory entry, not a live machine: ``ip_address``
    is the last address it was seen at (the heuristic key the graph's
    cross-device "talks-to" edges match on, and reused addresses are why
    those edges are labelled heuristic), while ``mac_address`` and
    ``serial_number`` are the identity. MAC is stored normalized to the
    lower-case colon form ``aa:bb:cc:dd:ee:ff``; the ingest normalizes
    before writing so the index compares equal to what it matches with.
    """

    __tablename__ = "twin_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # Natural key the ingest upserts against — one row per observed device,
    # however many feeds report it. Derived by the ingest service (host
    # name, MAC, or serial — whichever identity the source provides), never
    # a client-supplied UUID.
    device_key: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Last known address; used for talks-to matching, not identity.
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    # Normalized aa:bb:cc:dd:ee:ff.
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # server | workstation | appliance | iot | container_host | ... — an open
    # vocabulary, deliberately unconstrained: the taxonomy grows per source,
    # and a check constraint would turn the next source's noun into a 500.
    device_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default="unknown"
    )
    os_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Which feed produced the observation: "seed", "darktrace", "medic", ...
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )
    # Source-native extras that have no column of their own. Free-form by
    # design — the typed facts are the columns above.
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("uniq_twin_devices_device_key", "device_key", unique=True),
        Index("idx_twin_devices_ip_address", "ip_address"),
        Index("idx_twin_devices_mac_address", "mac_address"),
        Index("idx_twin_devices_serial_number", "serial_number"),
    )


class TwinProcess(Base):
    """One process observed on a device, named by its PID.

    (device, pid, name) identifies a process within one observation
    window; ``process_key`` — the ingest's serialization of that triple —
    is the natural key later observations upsert against. When the device
    goes, its processes go with it (CASCADE): a process with no machine
    behind it is nothing the twin can place.
    """

    __tablename__ = "twin_processes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # Natural key the ingest upserts against; see the class docstring.
    process_key: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("twin_devices.id", ondelete="CASCADE"), nullable=False
    )
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "user" is a reserved word in PostgreSQL; SQLAlchemy quotes it, and the
    # SQL mirror spells it "user" too. The account the process ran as.
    user: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    command: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # When the process started, as observed; NULL when the source does not
    # report it. Observation bookkeeping is first_seen/last_seen below.
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("uniq_twin_processes_process_key", "process_key", unique=True),
        # Process lookups lead with the device (the graph's "what ran on
        # this box"), then the PID.
        Index("idx_twin_processes_device_pid", "device_id", "pid"),
    )


class TwinConnection(Base):
    """One network connection observed on a device.

    ``connection_type`` is the enum that separates the three things an
    analyst means by "connection": a socket (bare local binding), a stream
    (ordered byte pipe), a session (a long-lived exchange). A connection
    belongs to its device — it dies with the device (CASCADE) — but may
    outlive its process: a network sensor reports device-level traffic it
    cannot attribute to a PID, so ``process_id`` is nullable and SET NULL
    on process deletion, demoting the row to a device-level connection
    rather than erasing an observed flow.
    """

    __tablename__ = "twin_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # Natural key the ingest upserts against — the ingest's serialization
    # of the identifying 5-tuple below.
    connection_key: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("twin_devices.id", ondelete="CASCADE"), nullable=False
    )
    # NULL for a device-level connection the source could not attribute to
    # a process; SET NULL when the process is deleted.
    process_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("twin_processes.id", ondelete="SET NULL"), nullable=True
    )
    # socket | stream | session — see TWIN_CONNECTION_TYPES.
    connection_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # tcp | udp | other.
    protocol: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    local_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    local_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The remote end; the graph matches this against other devices'
    # ip_address for the heuristic cross-device edge.
    remote_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    remote_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # TCP state (established, listen, time_wait, ...) as the source spells it.
    state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # inbound | outbound, relative to the device.
    direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # When the connection was established, as observed; NULL when the source
    # does not report it. Observation bookkeeping is first_seen/last_seen.
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "connection_type IN ('socket', 'stream', 'session')",
            name="ck_twin_connections_connection_type",
        ),
        Index("uniq_twin_connections_connection_key", "connection_key", unique=True),
        # The graph reads a device's connections filtered by layer class.
        Index("idx_twin_connections_device_type", "device_id", "connection_type"),
        # The talks-to pivot: which connections point at a given address.
        Index("idx_twin_connections_remote_ip", "remote_ip"),
    )

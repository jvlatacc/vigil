"""Versioned snapshot envelope for the CEP engine (spec ACs 3 and 6).

The engine holds all correlation state in the daemon's memory, so a
restart loses it by definition; this module is the durability contract
that narrows the loss to an honestly bounded window. One row in
``cep_snapshots`` is one envelope — the entity graph this PR owns plus
the pattern engine's machines and seen-ids as opaque JSON — written
periodically (``CEP_SNAPSHOT_INTERVAL_S``, 60 s default) and once more on
graceful shutdown, and restored from the latest row on boot.

Shared contract with the sibling pattern-engine PR: this module owns the
``graph`` section (via ``EntityGraph.snapshot``/``restore``) and treats
``machines`` and ``seen_ids`` as opaque JSON-safe payloads. The hooks
plugged in here are any object with ``snapshot_state()`` /
``restore_state(payload)`` — the engine's implementations land in that
PR, the wiring in the follow-up integration PR — so nothing here can
know (and nothing here validates) their internal shapes.

Every restore outcome is stated, never silent: the daemon boots either
"restored with gap" (the snapshot predates the crash; findings in that
window are absent — bounded by the snapshot interval, never zero) or
"fresh start" (no row, or one this build cannot read), with the reason
logged at the moment it is decided.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol

from core.cep.graph import EntityGraph
from core.telemetry import get_meter
from core.time import utcnow

logger = logging.getLogger(__name__)

# The envelope format version, persisted in the cep_snapshots.engine_version
# column and checked again inside the payload on restore. Bump on an
# incompatible change; restore refuses other versions rather than guessing.
SNAPSHOT_VERSION = 1

# Snapshot rows older than this are pruned by age on the snapshot cadence.
# Restore reads only the newest row; older rows exist for operator
# forensics, and a day covers any restart storm worth investigating.
RETENTION_S = 86400


class StateSection(Protocol):
    """What a state owner (the pattern engine, the seen-id set) exposes so
    its section of the envelope can ride the shared snapshot. Payloads are
    opaque here: JSON-safe blobs the owner alone can interpret."""

    def snapshot_state(self) -> Any: ...

    def restore_state(self, payload: Any) -> None: ...


@dataclass(frozen=True)
class SnapshotEnvelope:
    """One recovery point: engine format version plus every state section.

    ``machines`` and ``seen_ids`` pass through untouched — the engine's
    contract, not this module's. ``graph`` is this module's contract with
    ``EntityGraph``.
    """

    engine_version: int
    graph: Dict[str, Any]
    machines: Any = None
    seen_ids: Any = None

    def to_payload(self) -> Dict[str, Any]:
        """The JSON-safe dict the store persists. json.dumps is the
        JSON-safety proof: a non-serializable section raises at the writer,
        in snapshot_once's handled failure, instead of producing a row no
        future boot can read."""
        return {
            "engine_version": self.engine_version,
            "graph": self.graph,
            "machines": self.machines,
            "seen_ids": self.seen_ids,
        }

    @classmethod
    def from_payload(cls, payload: Any) -> "SnapshotEnvelope":
        """Parse a stored row back into an envelope, rejecting anything
        this build cannot read with the reason named."""
        if not isinstance(payload, dict):
            raise ValueError("snapshot payload must be an object")
        version = payload.get("engine_version")
        if not isinstance(version, int):
            raise ValueError(f"engine_version must be an integer, got {version!r}")
        if version != SNAPSHOT_VERSION:
            raise ValueError(
                f"envelope version {version} != this build's {SNAPSHOT_VERSION}"
            )
        graph = payload.get("graph")
        if not isinstance(graph, dict):
            raise ValueError("envelope is missing a 'graph' object")
        return cls(
            engine_version=version,
            graph=graph,
            machines=payload.get("machines"),
            seen_ids=payload.get("seen_ids"),
        )


class SnapshotStore(Protocol):
    """The storage seam: three verbs, no ORM model, mirroring the
    agent-ledger split (raw SQL table, Python reads/writes rows only). The
    Postgres implementation below is the shipped one; tests inject a fake.
    An adapter for a graph DB lands behind this same seam."""

    def save(self, payload: Dict[str, Any]) -> None: ...

    def latest(self) -> Optional[Dict[str, Any]]: ...

    def prune(self, retention_s: int) -> int: ...


class SnapshotManager:
    """Owns the snapshot cadence: periodic write, graceful-shutdown write,
    and the boot restore.

    Runs as a daemon component task (``run(shutdown_event)``), off the
    event loop for the DB round-trips via ``asyncio.to_thread`` — the
    scheduler sweep's convention. Every snapshot failure is logged with
    its reason and widens the restart loss window; none of them can raise
    into the daemon, whose spine this layer must never touch.
    """

    def __init__(
        self,
        graph: EntityGraph,
        store: SnapshotStore,
        *,
        interval_s: int,
        machines: Optional[StateSection] = None,
        seen_ids: Optional[StateSection] = None,
        retention_s: int = RETENTION_S,
    ) -> None:
        self._graph = graph
        self._store = store
        self._interval_s = max(1, interval_s)
        self._machines = machines
        self._seen_ids = seen_ids
        self._retention_s = max(1, retention_s)
        self.last_snapshot_at: Optional[datetime] = None
        self.last_restore_age_s: Optional[float] = None
        self._final_written = False
        self.stats: Dict[str, Any] = {
            "cep_snapshots_written": 0,
            "cep_snapshot_failures": 0,
            "cep_snapshot_restored": 0,
            # Current-state flag (the tap's cep_degraded pattern): 1 while
            # the last write failed, so /health can show the widened loss
            # window without reading logs.
            "cep_snapshot_degraded": 0,
        }
        self._written_counter: Any = None
        self._failure_counter: Any = None
        self._restore_counter: Any = None
        self._instruments_ready = False

    def build_envelope(self) -> SnapshotEnvelope:
        return SnapshotEnvelope(
            engine_version=SNAPSHOT_VERSION,
            graph=self._graph.snapshot(),
            machines=self._machines.snapshot_state() if self._machines else None,
            seen_ids=self._seen_ids.snapshot_state() if self._seen_ids else None,
        )

    def snapshot_once(self) -> bool:
        """Write one envelope and prune by age. Never raises: the return
        value says whether the recovery point advanced, and the log says
        why when it did not."""
        try:
            self._store.save(self.build_envelope().to_payload())
        except Exception as exc:
            self.stats["cep_snapshot_failures"] += 1
            self.stats["cep_snapshot_degraded"] = 1
            self._record(self._failure_counter)
            logger.warning(
                "CEP snapshot write failed (%s); the restart loss window "
                "widens until the next successful snapshot",
                exc,
            )
            return False
        # In-process bookkeeping on the codebase's naive-UTC clock (the
        # shared utcnow helper), so consumers doing arithmetic on it —
        # the metrics mirror's snapshot age — mix clock conventions never.
        self.last_snapshot_at = utcnow()
        self.stats["cep_snapshots_written"] += 1
        self.stats["cep_snapshot_degraded"] = 0
        self._record(self._written_counter)
        try:
            pruned = self._store.prune(self._retention_s)
            if pruned:
                logger.info("CEP snapshot retention pruned %d row(s)", pruned)
        except Exception as exc:
            # Retention is maintenance, not correctness: a failed prune
            # leaves old rows in place, visible on every tick, rather than
            # being swallowed.
            logger.warning("CEP snapshot retention prune failed: %s", exc)
        return True

    def restore(self) -> Optional[float]:
        """Restore from the latest snapshot row.

        Returns the snapshot's age in seconds when state was restored —
        the honest lower bound of the loss window, for the boot log to
        state — or None for a fresh start, with the reason logged here.
        A snapshot this build cannot read (wrong version, malformed
        envelope) starts fresh rather than correlating over half a state.
        """
        try:
            payload = self._store.latest()
        except Exception as exc:
            logger.warning(
                "CEP snapshot restore could not read the store (%s); "
                "correlation state starts empty",
                exc,
            )
            return None
        if payload is None:
            logger.info("CEP snapshots: no row on file; correlation state starts empty")
            return None
        try:
            envelope = SnapshotEnvelope.from_payload(payload)
            self._graph.restore(envelope.graph)
            if self._machines is not None and envelope.machines is not None:
                self._machines.restore_state(envelope.machines)
            if self._seen_ids is not None and envelope.seen_ids is not None:
                self._seen_ids.restore_state(envelope.seen_ids)
        except ValueError as exc:
            # GraphRestoreError is a ValueError: one handler names every
            # "this build cannot read that row" reason.
            logger.warning(
                "CEP snapshot unreadable, starting fresh (%s); re-delivered "
                "findings are still matched idempotently by the engine",
                exc,
            )
            return None
        age = (
            datetime.now(timezone.utc) - self._snapshot_taken_at(payload)
        ).total_seconds()
        self.last_restore_age_s = max(0.0, age)
        self.stats["cep_snapshot_restored"] = 1
        self._record(self._restore_counter)
        return self.last_restore_age_s

    # ------------------------------------------------------------------
    # Metrics mirror (spec AC 8)
    # ------------------------------------------------------------------

    def _ensure_instruments(self) -> None:
        """The counters' OTEL mirrors, created on first record (the tap's
        pattern) so they bind to the real meter once init_telemetry has run
        and to the no-op one when it has not. Thread-safe: the SDK meter is,
        and this runs off the event loop via asyncio.to_thread."""
        if self._instruments_ready:
            return
        self._instruments_ready = True
        try:
            meter = get_meter("vigil.daemon")
            self._written_counter = meter.create_counter(
                name="vigil.cep.snapshots",
                description="CEP state snapshots written to the cep_snapshots store",
                unit="1",
            )
            self._failure_counter = meter.create_counter(
                name="vigil.cep.snapshot_failures",
                description="Failed CEP snapshot writes (the restart loss window widens)",
                unit="1",
            )
            self._restore_counter = meter.create_counter(
                name="vigil.cep.restores",
                description="CEP correlation states restored from a snapshot on boot",
                unit="1",
            )
        except Exception as _err:
            logger.debug("OTEL CEP instruments unavailable: %s", _err)

    def _record(self, counter: Any) -> None:
        self._ensure_instruments()
        try:
            if counter is not None:
                counter.add(1)
        except Exception as _err:
            logger.debug("OTEL CEP record failed (non-fatal): %s", _err)

    @staticmethod
    def _snapshot_taken_at(payload: Dict[str, Any]) -> datetime:
        """When the envelope was written, from the store's row stamp. A
        payload without one (should not happen — the column is NOT NULL)
        reads as now, which understates the gap; the caller's boot line
        states the interval bound regardless."""
        taken_at = payload.get("created_at")
        if isinstance(taken_at, datetime):
            return (
                taken_at if taken_at.tzinfo else taken_at.replace(tzinfo=timezone.utc)
            )
        if isinstance(taken_at, str):
            try:
                parsed = datetime.fromisoformat(taken_at)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """The snapshot loop: write every ``interval_s`` and once more on
        graceful shutdown, so a clean stop loses nothing and a crash loses
        at most the interval (documented, never promised zero)."""
        try:
            while not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=self._interval_s
                    )
                    break  # graceful shutdown requested
                except asyncio.TimeoutError:
                    pass
                await asyncio.to_thread(self.snapshot_once)
        except asyncio.CancelledError:
            pass  # the final snapshot below still runs
        # Synchronous by intent: this runs once, at shutdown, and must
        # complete even when the task was cancelled mid-write.
        self._final_snapshot()

    def _final_snapshot(self) -> None:
        """The graceful-shutdown snapshot, idempotent against a
        cancellation racing the loop's own final write."""
        if self._final_written:
            return
        self._final_written = True
        self.snapshot_once()


class PostgresSnapshotStore:
    """The ``cep_snapshots`` access layer over the shared DB manager.

    INSERT/SELECT plus the age-scoped prune function — exactly the grant
    set the migration gives ``vigil_app``, no more. A missing table (an
    upgraded deployment whose init SQL has not run yet) disables the store
    once, loudly: snapshots are unavailable until the migration lands, and
    the boot log's loss-window line says exactly that.
    """

    def __init__(self) -> None:
        self._available = True

    def save(self, payload: Dict[str, Any]) -> None:
        def op(conn: Any) -> None:
            conn.execute(
                _text(
                    "INSERT INTO cep_snapshots (engine_version, payload) "
                    "VALUES (:engine_version, CAST(:payload AS jsonb))"
                ),
                {
                    "engine_version": payload.get("engine_version", SNAPSHOT_VERSION),
                    "payload": json.dumps(payload),
                },
            )

        self._run("snapshot write", op)

    def latest(self) -> Optional[Dict[str, Any]]:
        def op(conn: Any) -> Optional[Dict[str, Any]]:
            row = conn.execute(
                _text(
                    "SELECT created_at, payload FROM cep_snapshots "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            ).first()
            if row is None:
                return None
            created_at, body = row
            if isinstance(body, str):  # a driver that hands back text
                body = json.loads(body)
            if isinstance(body, dict):
                body = dict(body)
                body["created_at"] = created_at
            return body

        return self._run("snapshot restore", op)

    def prune(self, retention_s: int) -> int:
        def op(conn: Any) -> int:
            row = conn.execute(
                _text("SELECT prune_cep_snapshots(CAST(:max_age AS interval))"),
                {"max_age": f"{retention_s} seconds"},
            ).scalar()
            return int(row or 0)

        return self._run("snapshot retention", op)

    def _run(self, what: str, op: Callable[[Any], Any]) -> Any:
        """One operation on one connection, with the missing-table case
        classified once and named (the init SQL file to run) instead of
        retried into log noise."""
        if not self._available:
            raise _StoreUnavailable(
                "CEP snapshot store unavailable (see earlier warning)"
            )
        try:
            from core.storage.connection import get_db_manager

            manager = get_db_manager()
            if manager.engine is None:
                manager.initialize()
            engine = manager.engine
            if engine is None:  # initialize() did not build one
                raise _StoreUnavailable("DB manager has no engine")
            conn = engine.connect()
            try:
                return op(conn)
            finally:
                conn.close()
        except Exception as exc:
            if _is_missing_table(exc):
                self._available = False
                logger.warning(
                    "cep_snapshots table does not exist (%s); CEP snapshots are "
                    "unavailable until infra/database/init/40_cep_snapshots.sql "
                    "is applied. Correlation runs in memory and a restart "
                    "loses all state — the loss window is unbounded until then.",
                    exc,
                )
                raise _StoreUnavailable(
                    f"{what} unavailable: the cep_snapshots table does not exist; "
                    "apply infra/database/init/40_cep_snapshots.sql"
                ) from exc
            raise


class _StoreUnavailable(RuntimeError):
    pass


def _text(query: str) -> Any:
    from sqlalchemy import text

    return text(query)


def _is_missing_table(exc: Any) -> bool:
    """Postgres SQLSTATE 42P01 (undefined_table), however SQLAlchemy wraps
    it — the SQLSTATE, not a message match."""
    seen: list = [exc]
    for maybe in ("orig", "cause"):
        nested = getattr(exc, maybe, None)
        if nested is not None:
            seen.append(nested)
    for candidate in seen:
        if getattr(candidate, "pgcode", None) == "42P01":
            return True
    return False

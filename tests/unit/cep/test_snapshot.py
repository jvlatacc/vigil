"""Snapshot envelope and manager behavior (spec AC 6, graph half).

The durability contract under test: an envelope round-trips through JSON
with its opaque sections untouched; restore reads the newest row and
states the loss window it implies; an unreadable or missing snapshot
starts fresh with the reason logged, never silently; the periodic loop
and the graceful-shutdown snapshot each write exactly as often as they
should; and a store failure never raises into the daemon.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.cep.graph import EntityGraph
from core.cep.snapshot import (
    SNAPSHOT_VERSION,
    PostgresSnapshotStore,
    SnapshotEnvelope,
    SnapshotManager,
)

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


class FakeStore:
    """In-memory rows, newest-wins; fails only when ``fail_with`` is set."""

    def __init__(self) -> None:
        self.rows: list = []
        self.fail_with: Exception | None = None
        self.pruned_with: list = []

    def save(self, payload: dict) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.rows.append(payload)

    def latest(self):
        if self.fail_with is not None:
            raise self.fail_with
        return self.rows[-1] if self.rows else None

    def prune(self, retention_s: int) -> int:
        self.pruned_with.append(retention_s)
        return 0


class FakeState:
    """A StateSection stand-in for the engine's machines / seen-ids: an
    opaque payload this test alone can interpret."""

    def __init__(self, state=None) -> None:
        self._state = state
        self.restored_with = "never-restored"

    def snapshot_state(self):
        return self._state

    def restore_state(self, payload) -> None:
        self.restored_with = payload
        self._state = payload


def make_manager(store=None, **kwargs) -> SnapshotManager:
    kwargs.setdefault("interval_s", 60)
    return SnapshotManager(graph=EntityGraph(), store=store or FakeStore(), **kwargs)


# -- envelope --------------------------------------------------------------


def test_envelope_roundtrips_through_json_untouched():
    graph = EntityGraph()
    graph.observe_node("host", "web-1", T0)
    mgr = make_manager(
        machines=FakeState({"step": 2, "findings": ["f-1"]}),
        seen_ids=FakeState(["f-1", "f-2"]),
    )
    mgr._graph = graph
    payload = json.loads(json.dumps(mgr.build_envelope().to_payload()))

    back = SnapshotEnvelope.from_payload(payload)
    assert back.engine_version == SNAPSHOT_VERSION
    assert back.machines == {"step": 2, "findings": ["f-1"]}
    assert back.seen_ids == ["f-1", "f-2"]
    assert back.graph["version"] == 1


def test_envelope_rejects_non_object_and_missing_graph():
    with pytest.raises(ValueError, match="object"):
        SnapshotEnvelope.from_payload(["not", "an", "object"])
    with pytest.raises(ValueError, match="graph"):
        SnapshotEnvelope.from_payload({"engine_version": 1})


def test_envelope_rejects_a_version_this_build_cannot_read():
    with pytest.raises(ValueError, match="version"):
        SnapshotEnvelope.from_payload({"engine_version": 999, "graph": {}})
    with pytest.raises(ValueError, match="integer"):
        SnapshotEnvelope.from_payload({"engine_version": "1", "graph": {}})


# -- restore semantics -----------------------------------------------------


def test_restore_from_empty_store_is_a_fresh_start():
    mgr = make_manager()
    assert mgr.restore() is None
    assert mgr.last_restore_age_s is None
    assert mgr.stats["cep_snapshot_restored"] == 0


def test_restore_returns_the_snapshot_age_and_counts_one_restore():
    store = FakeStore()
    make_manager(store=store).snapshot_once()

    rebooted = make_manager(store=store, machines=FakeState(), seen_ids=FakeState())
    age = rebooted.restore()
    assert age is not None
    assert 0 <= age < 60
    assert rebooted.last_restore_age_s == age
    assert rebooted.stats["cep_snapshot_restored"] == 1


def test_restore_rebuilds_the_graph_and_opaque_sections():
    store = FakeStore()
    graph = EntityGraph()
    graph.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)
    writer = make_manager(
        store=store,
        machines=FakeState({"machine-a": {"step": 1}}),
        seen_ids=FakeState(["f-1"]),
    )
    writer._graph = graph
    writer.snapshot_once()

    rebooted_graph = EntityGraph()
    rebooted_machines = FakeState()
    rebooted_seen = FakeState()
    rebooted = SnapshotManager(
        graph=rebooted_graph,
        store=store,
        interval_s=60,
        machines=rebooted_machines,
        seen_ids=rebooted_seen,
    )
    assert rebooted.restore() is not None

    # the graph half of AC 6's equivalence
    assert rebooted_graph.snapshot() == graph.snapshot()
    # the opaque sections came back exactly as written
    assert rebooted_machines.restored_with == {"machine-a": {"step": 1}}
    assert rebooted_seen.restored_with == ["f-1"]


def test_restore_of_an_unreadable_snapshot_starts_fresh():
    store = FakeStore()
    graph = EntityGraph()
    graph.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)
    writer = make_manager(store=store)
    writer._graph = graph
    writer.snapshot_once()

    # the row on file was written by a build this one cannot read
    store.rows[-1]["engine_version"] = 999
    rebooted = make_manager(store=store)
    assert rebooted.restore() is None
    assert rebooted.stats["cep_snapshot_restored"] == 0


def test_restore_of_a_row_with_a_corrupt_graph_starts_fresh():
    store = FakeStore()
    make_manager(store=store).snapshot_once()

    store.rows[-1]["graph"]["nodes"] = "not-a-list"
    rebooted = make_manager(store=store)
    assert rebooted.restore() is None


def test_restore_ignores_an_unreadable_store():
    store = FakeStore()
    store.fail_with = RuntimeError("connection refused")
    mgr = make_manager(store=store)
    assert mgr.restore() is None


def test_restore_age_uses_the_row_stamp_not_wall_clock_only():
    """The store stamps created_at; the age the boot log reports comes
    from it, so a payload written 30s ago reports ~30s, not ~0."""
    store = FakeStore()
    make_manager(store=store).snapshot_once()
    store.rows[-1]["created_at"] = datetime.now(timezone.utc) - timedelta(seconds=30)

    rebooted = make_manager(store=store)
    age = rebooted.restore()
    assert age is not None
    assert 29 <= age <= 31


# -- snapshot_once: failure handling and retention --------------------------


def test_snapshot_once_failure_is_counted_and_never_raises():
    store = FakeStore()
    store.fail_with = RuntimeError("db down")
    mgr = make_manager(store=store)
    assert mgr.snapshot_once() is False
    assert mgr.stats["cep_snapshot_failures"] == 1
    assert mgr.stats["cep_snapshots_written"] == 0


def test_snapshot_once_prunes_with_the_configured_retention():
    store = FakeStore()
    mgr = make_manager(store=store, retention_s=3600)
    mgr.snapshot_once()
    assert store.pruned_with == [3600]


def test_retention_failure_does_not_undo_the_write():
    store = FakeStore()

    def failing_prune(retention_s: int) -> int:
        raise RuntimeError("prune unavailable")

    store.prune = failing_prune  # type: ignore[method-assign]
    mgr = make_manager(store=store)
    assert mgr.snapshot_once() is True
    assert mgr.stats["cep_snapshots_written"] == 1


# -- the loop ---------------------------------------------------------------


async def test_periodic_loop_snapshots_on_interval_until_shutdown():
    """The manager clamps the interval to >= 1s, so one real tick plus the
    shutdown write is the observable cadence here."""
    store = FakeStore()
    mgr = make_manager(store=store, interval_s=1)
    stop = asyncio.Event()
    loop = asyncio.ensure_future(mgr.run(stop))

    await asyncio.sleep(1.5)
    stop.set()
    await asyncio.wait_for(loop, timeout=2)

    assert len(store.rows) >= 2  # the periodic tick plus the shutdown write
    assert all(row["engine_version"] == SNAPSHOT_VERSION for row in store.rows)


async def test_graceful_shutdown_writes_one_final_snapshot():
    """A daemon stopped between intervals still leaves a fresh recovery
    point — a clean stop loses nothing."""
    store = FakeStore()
    mgr = make_manager(store=store, interval_s=3600)
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(mgr.run(stop), timeout=2)

    assert len(store.rows) == 1
    assert mgr.last_snapshot_at is not None


async def test_cancellation_still_writes_the_final_snapshot():
    """The daemon tears tasks down by cancellation; the shutdown snapshot
    must survive it."""
    store = FakeStore()
    mgr = make_manager(store=store, interval_s=3600)
    loop = asyncio.ensure_future(mgr.run(asyncio.Event()))
    await asyncio.sleep(0.05)
    loop.cancel()
    await asyncio.wait_for(loop, timeout=2)

    assert len(store.rows) == 1


# -- the shipped Postgres store: wiring, not DB behavior --------------------


def test_postgres_store_missing_table_disables_the_store_once(caplog, monkeypatch):
    """A store pointed at a database without cep_snapshots disables itself
    once, naming the init SQL, instead of retrying into log noise."""

    class MissingTableError(Exception):
        pass

    err = MissingTableError('relation "cep_snapshots" does not exist')
    err.pgcode = "42P01"  # type: ignore[attr-defined]

    class BrokenManager:
        engine = None

        def initialize(self, *args, **kwargs) -> None:
            raise err

    import core.storage.connection as conn_mod

    monkeypatch.setattr(conn_mod, "get_db_manager", lambda: BrokenManager())
    store = PostgresSnapshotStore()

    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError, match="unavailable"):
            store.save({"engine_version": 1, "graph": {}})
        # the second call short-circuits on the disabled flag — one warning
        with pytest.raises(RuntimeError, match="unavailable"):
            store.save({"engine_version": 1, "graph": {}})

    warnings = [r for r in caplog.records if "40_cep_snapshots.sql" in r.message]
    assert len(warnings) == 1


def test_degraded_flag_tracks_the_last_write_outcome():
    """Spec AC 8: the degraded flag follows the last write — 1 while the
    last snapshot failed (the restart loss window is widening), 0 once a
    write succeeds — so /health can show it without reading logs."""
    store = FakeStore()
    manager = make_manager(store)
    assert manager.stats["cep_snapshot_degraded"] == 0

    store.fail_with = RuntimeError("db down")
    assert manager.snapshot_once() is False
    assert manager.stats["cep_snapshot_degraded"] == 1

    store.fail_with = None
    assert manager.snapshot_once() is True
    assert manager.stats["cep_snapshot_degraded"] == 0

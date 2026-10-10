"""The digital-twin demo seed.

Two layers, matching the script's split: the pure payload (``build_demo_batch``
and the key derivation) asserts on plain dicts, no database; the apply step
round-trips through Postgres on the throwaway database
``tests/unit/conftest.py`` provisions, proving the idempotency contract —
run twice, identical row counts, ``last_seen`` bumped, ``first_seen`` never
touched.

Spec: acceptance criterion 6 — a demo topology of at least 4 devices,
10 processes, and 20 connections spanning all three ``connection_type``
values, with a lateral-movement narrative that lands on db-01 so the graph
renders a heuristic talks-to edge.
"""

import pytest
from sqlalchemy import select

from core.storage.models import TwinConnection, TwinDevice, TwinProcess
from core.storage.unit_of_work import unit_of_work
from scripts.seed_digital_twin_demo import (
    apply_batch,
    build_demo_batch,
    connection_key_for,
    device_key_for,
    normalize_mac,
    process_key_for,
)

pytestmark = [pytest.mark.unit]

# The spec's floor for the demo dataset (criterion 6).
MIN_DEVICES = 4
MIN_PROCESSES = 10
MIN_CONNECTIONS = 20


@pytest.fixture
def batch():
    return build_demo_batch()


# --- the payload, no database ---------------------------------------------------


def test_demo_batch_meets_the_spec_floor(batch):
    assert len(batch["devices"]) >= MIN_DEVICES
    assert len(batch["processes"]) >= MIN_PROCESSES
    assert len(batch["connections"]) >= MIN_CONNECTIONS
    assert batch["source"] == "seed"


def test_demo_batch_spans_all_three_connection_types(batch):
    used = {c["connection_type"] for c in batch["connections"]}
    assert used == {"socket", "stream", "session"}


def test_demo_batch_keys_are_unique_within_the_batch(batch):
    device_keys = [device_key_for(d) for d in batch["devices"]]
    process_keys = [
        process_key_for(f"host:{p['device']}", p) for p in batch["processes"]
    ]
    connection_keys = [
        connection_key_for(f"host:{(c['process'] or {}).get('device')}", c)
        for c in batch["connections"]
    ]
    assert len(set(device_keys)) == len(device_keys)
    assert len(set(process_keys)) == len(process_keys)
    assert len(set(connection_keys)) == len(connection_keys)
    # The collision that forced device-scoping: identical listeners on
    # two different hosts must key apart.
    assert connection_key_for(
        "host:web-01",
        {
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 22,
        },
    ) != connection_key_for(
        "host:app-01",
        {
            "connection_type": "socket",
            "protocol": "tcp",
            "local_ip": "0.0.0.0",
            "local_port": 22,
        },
    )


def test_demo_batch_references_resolve(batch):
    """Processes name a device in the batch; connections name a batch process."""
    hostnames = {d["hostname"] for d in batch["devices"]}
    process_refs = {(p["device"], p["pid"], p["name"]) for p in batch["processes"]}
    for conn in batch["connections"]:
        if conn["process"] is None:
            continue  # device-level: the sensor could not attribute the flow
        assert conn["process"]["device"] in hostnames
        ref = (
            conn["process"]["device"],
            conn["process"]["pid"],
            conn["process"]["name"],
        )
        assert ref in process_refs


def test_demo_batch_tells_the_lateral_movement_story(batch):
    """web-01 → app-01 → db-01, with at least one connection to db-01's IP.

    The talks-to edge the graph renders matches a connection's ``remote_ip``
    against another device's ``ip_address`` — the story must end somewhere
    that edge can point.
    """
    ips = {d["hostname"]: d["ip_address"] for d in batch["devices"]}
    by_device = {}
    for conn in batch["connections"]:
        if conn.get("remote_ip") is None:  # listeners have no remote end
            continue
        if conn["process"] is None:  # device-level: no originating process
            continue
        by_device.setdefault(conn["process"]["device"], []).append(conn["remote_ip"])

    # The pivot out of the DMZ, and the second hop into the database.
    assert ips["app-01"] in by_device["web-01"]
    assert ips["db-01"] in by_device["app-01"]


# --- pure helpers ----------------------------------------------------------------


def test_normalize_mac_handles_the_common_spellings():
    assert normalize_mac("0A:1B:2C:3D:4E:01") == "0a:1b:2c:3d:4e:01"
    assert normalize_mac("0a-1b-2c-3d-4e-01") == "0a:1b:2c:3d:4e:01"
    assert normalize_mac("0a1b.2c3d.4e01") == "0a:1b:2c:3d:4e:01"
    assert normalize_mac("0a1b2c3d4e01") == "0a:1b:2c:3d:4e:01"


def test_normalize_mac_passes_none_and_the_unparseable_through():
    assert normalize_mac(None) is None
    assert normalize_mac("not-a-mac") == "not-a-mac"


def test_device_key_prefers_hostname_then_mac_then_serial():
    assert device_key_for({"hostname": "web-01"}) == "host:web-01"
    assert (
        device_key_for({"mac_address": "0A:1B:2C:3D:4E:01"}) == "mac:0a:1b:2c:3d:4e:01"
    )
    assert device_key_for({"serial_number": "C02X1234ABCD"}) == "serial:C02X1234ABCD"
    with pytest.raises(ValueError):
        device_key_for({})


def test_connection_key_renders_the_five_tuple_with_dashes_for_nulls():
    assert (
        connection_key_for(
            "host:web-01",
            {
                "connection_type": "socket",
                "protocol": "tcp",
                "local_ip": "0.0.0.0",
                "local_port": 443,
            },
        )
        == "host:web-01:socket:tcp:0.0.0.0:443:-:-"
    )


# --- the apply step, round-tripped through Postgres -------------------------------


@pytest.mark.database
@pytest.mark.external_service
class TestApplyBatch:
    @pytest.fixture(autouse=True)
    def _clean(self):
        with unit_of_work() as session:
            session.query(TwinConnection).delete()
            session.query(TwinProcess).delete()
            session.query(TwinDevice).delete()
        yield
        with unit_of_work() as session:
            session.query(TwinConnection).delete()
            session.query(TwinProcess).delete()
            session.query(TwinDevice).delete()

    def _rows(self, model, order_by):
        with unit_of_work() as session:
            rows = session.scalars(select(model).order_by(order_by)).all()
            # Detach so the assertions read what Postgres holds, not the cache.
            session.expunge_all()
        return rows

    def test_first_run_seeds_the_floor_counts(self, batch):
        counts = apply_batch(batch)
        assert counts["devices"] == len(batch["devices"])
        assert counts["processes"] == len(batch["processes"])
        assert counts["connections"] == len(batch["connections"])
        assert counts["devices"] >= MIN_DEVICES
        assert counts["processes"] >= MIN_PROCESSES
        assert counts["connections"] >= MIN_CONNECTIONS

    def test_running_twice_leaves_row_counts_identical(self, batch):
        first = apply_batch(batch)
        second = apply_batch(batch)
        assert second == first

    def test_second_run_bumps_last_seen_and_never_first_seen(self, batch):
        apply_batch(batch)
        devices_before = {
            d.device_key: (d.first_seen, d.last_seen)
            for d in self._rows(TwinDevice, TwinDevice.device_key)
        }
        processes_before = {
            p.process_key: (p.first_seen, p.last_seen)
            for p in self._rows(TwinProcess, TwinProcess.process_key)
        }
        connections_before = {
            c.connection_key: (c.first_seen, c.last_seen)
            for c in self._rows(TwinConnection, TwinConnection.connection_key)
        }

        apply_batch(batch)

        for rows_before, model, order in (
            (devices_before, TwinDevice, TwinDevice.device_key),
            (processes_before, TwinProcess, TwinProcess.process_key),
            (connections_before, TwinConnection, TwinConnection.connection_key),
        ):
            rows_after = {getattr(r, order.key): r for r in self._rows(model, order)}
            assert set(rows_after) == set(rows_before), "row counts changed on re-run"
            for key, (first_seen, last_seen) in rows_before.items():
                row = rows_after[key]
                assert row.first_seen == first_seen, f"{key}: first_seen moved"
                assert row.last_seen > last_seen, f"{key}: last_seen did not bump"

    def test_every_connection_type_survives_the_round_trip(self, batch):
        apply_batch(batch)
        types = {
            c.connection_type
            for c in self._rows(TwinConnection, TwinConnection.connection_key)
        }
        assert types == {"socket", "stream", "session"}

    def test_a_talks_to_precondition_row_reaches_the_database(self, batch):
        """db-01's address appears as some connection's remote_ip — the edge
        the graph's heuristic cross-device matching needs."""
        apply_batch(batch)
        ips = {
            d.hostname: d.ip_address
            for d in self._rows(TwinDevice, TwinDevice.hostname)
        }
        remotes = {
            c.remote_ip
            for c in self._rows(TwinConnection, TwinConnection.connection_key)
        }
        assert ips["db-01"] in remotes

    def test_the_unattributed_beacon_lands_device_level(self, batch):
        """A connection whose sensor could not name a process carries
        process_id = NULL, not a dangling reference."""
        apply_batch(batch)
        beacons = [
            c
            for c in self._rows(TwinConnection, TwinConnection.connection_key)
            if c.remote_ip == "198.51.100.23"
        ]
        assert len(beacons) == 1
        assert beacons[0].process_id is None
        assert beacons[0].device_id is not None

"""Unit tests for the digital-twin natural keys and pure graph derivation.

The ingest service derives every row's natural key server-side, so the same
machine, process, or connection observed twice — across posts, sources, or
concurrent requests — must land on one row. These tests pin the derivation
shapes and, critically, the PARITY CONTRACT with the demo seed
(``scripts/seed_digital_twin_demo.py``): the seed's rerun-through-the-API
guarantee holds only if both sides derive identical keys, so any drift here
fails fast rather than duplicating rows in production.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.storage.schemas.digital_twin import (
    TwinConnectionOut,
    TwinDeviceIn,
    TwinDeviceOut,
    TwinProcessOut,
)
from core.twin.ingest import (
    TwinReferenceError,
    _key_part,
    derive_connection_key,
    derive_device_key,
    derive_edges,
    derive_process_key,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]

_T = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def seed():
    """The demo seed module, loaded from ``scripts/`` (not a package)."""
    spec = importlib.util.spec_from_file_location(
        "seed_digital_twin_demo", REPO_ROOT / "scripts" / "seed_digital_twin_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- device keys ---------------------------------------------------------------


def test_hostname_spelling_is_preserved():
    """The seed keys ``host:web-01`` — case and spacing are identity."""
    assert derive_device_key(hostname="web-01") == "host:web-01"
    assert derive_device_key(hostname="Web-01") == "host:Web-01"


def test_mac_identity_uses_the_normalized_form():
    # MACs arrive normalized by the input schema; the key embeds that form.
    assert derive_device_key(mac_address="0a:1b:2c:3d:4e:01") == (
        "mac:0a:1b:2c:3d:4e:01"
    )


def test_serial_identity():
    assert derive_device_key(serial_number="C02X1234ABCD") == "serial:C02X1234ABCD"


def test_hostname_outranks_mac_and_serial():
    assert (
        derive_device_key(
            hostname="web-01", mac_address="0a:1b:2c:3d:4e:01", serial_number="S1"
        )
        == "host:web-01"
    )


def test_identity_less_device_is_refused():
    with pytest.raises(TwinReferenceError):
        derive_device_key()


# --- connection keys -----------------------------------------------------------


def test_empty_parts_render_as_dash():
    """Mirrors the seed's ``_key_part``: a missing part is a slot, not a gap.

    An empty string and None both mean "not observed"; port 0 is a real
    value and must survive as ``0``.
    """
    assert _key_part(None) == "-"
    assert _key_part("") == "-"
    assert _key_part(0) == "0"
    assert _key_part("tcp") == "tcp"


def test_connection_key_scopes_by_device():
    """Two hosts both bind 0.0.0.0:22 — a bare 5-tuple would collide."""
    five_tuple = dict(
        connection_type="socket",
        protocol="tcp",
        local_ip="0.0.0.0",
        local_port=22,
        remote_ip=None,
        remote_port=None,
    )
    assert derive_connection_key("host:web-01", **five_tuple) == (
        "host:web-01:socket:tcp:0.0.0.0:22:-:-"
    )
    assert derive_connection_key("host:app-01", **five_tuple) == (
        "host:app-01:socket:tcp:0.0.0.0:22:-:-"
    )


def test_named_shared_example_matches_the_seed(seed):
    """One shared observation, derived both ways, equal — and equal to the
    literal the seed format promises.

    Cross-referenced with scripts/seed_digital_twin_demo.py::connection_key_for.
    """
    observation = {
        "connection_type": "socket",
        "protocol": "tcp",
        "local_ip": "0.0.0.0",
        "local_port": 22,
    }
    device_key = "host:web-01"
    assert (
        derive_connection_key(
            device_key,
            connection_type=observation["connection_type"],
            protocol=observation["protocol"],
            local_ip=observation["local_ip"],
            local_port=observation["local_port"],
            remote_ip=None,
            remote_port=None,
        )
        == seed.connection_key_for(device_key, observation)
        == "host:web-01:socket:tcp:0.0.0.0:22:-:-"
    )


def test_long_compositions_fit_the_column():
    """A maximum-length hostname threaded through a connection key still
    fits ``connection_key`` (String(255)) — deterministically, so the
    shortened form keeps its idempotency."""
    hostname = "h" * 250
    key = derive_connection_key(
        f"host:{hostname}",
        connection_type="socket",
        protocol="tcp",
        local_ip="10.0.0.1",
        local_port=1,
        remote_ip="10.0.0.2",
        remote_port=2,
    )
    assert len(key) == 255
    again = derive_connection_key(
        f"host:{hostname}",
        connection_type="socket",
        protocol="tcp",
        local_ip="10.0.0.1",
        local_port=1,
        remote_ip="10.0.0.2",
        remote_port=2,
    )
    assert again == key


# --- seed parity (the contract the seed's rerun guarantee rides on) ------------


def test_device_keys_match_the_seed_derivation(seed):
    for entry in seed.build_demo_batch()["devices"]:
        validated = TwinDeviceIn(**entry)
        assert derive_device_key(
            hostname=validated.hostname,
            mac_address=validated.mac_address,
            serial_number=validated.serial_number,
        ) == seed.device_key_for(entry)


def test_process_keys_match_the_seed_derivation(seed):
    batch = seed.build_demo_batch()
    devices = {d["hostname"]: d for d in batch["devices"]}
    for entry in batch["processes"]:
        device_entry = devices[entry["device"]]
        device_key = seed.device_key_for(device_entry)
        assert derive_process_key(
            device_key, entry["pid"], entry["name"]
        ) == seed.process_key_for(device_key, entry)


def test_connection_keys_match_the_seed_derivation(seed):
    batch = seed.build_demo_batch()
    devices = {d["hostname"]: d for d in batch["devices"]}
    for entry in batch["connections"]:
        ref = entry.get("process")
        hostname = ref["device"] if ref else entry["device"]
        device_key = seed.device_key_for(devices[hostname])
        assert derive_connection_key(
            device_key,
            connection_type=entry["connection_type"],
            protocol=entry.get("protocol"),
            local_ip=entry.get("local_ip"),
            local_port=entry.get("local_port"),
            remote_ip=entry.get("remote_ip"),
            remote_port=entry.get("remote_port"),
        ) == seed.connection_key_for(device_key, entry)


# --- pure edge derivation ------------------------------------------------------


def _device(**overrides):
    fields = dict(
        id=uuid.uuid4(),
        device_key=f"host:{overrides.get('hostname', 'dev')}",
        hostname=overrides.pop("hostname", None),
        device_type="server",
        ip_address=overrides.pop("ip_address", None),
        source="test",
        first_seen=_T,
        last_seen=_T,
    )
    return TwinDeviceOut(**{**fields, **overrides})


def _process(device, **overrides):
    fields = dict(
        id=uuid.uuid4(),
        device_id=device.id,
        pid=1204,
        name="nginx",
        source="test",
        first_seen=_T,
        last_seen=_T,
    )
    return TwinProcessOut(**{**fields, **overrides})


def _connection(device, process=None, **overrides):
    fields = dict(
        id=uuid.uuid4(),
        device_id=device.id,
        process_id=process.id if process else None,
        connection_type="socket",
        protocol="tcp",
        local_ip="0.0.0.0",
        local_port=443,
        remote_ip=overrides.pop("remote_ip", None),
        remote_port=overrides.pop("remote_port", None),
        state="established",
        source="test",
        first_seen=_T,
        last_seen=_T,
    )
    return TwinConnectionOut(**{**fields, **overrides})


def test_runs_and_binds_edges_are_derived():
    device = _device(hostname="web-01", ip_address="10.0.4.11")
    process = _process(device)
    connection = _connection(device, process)

    edges = derive_edges([device], [process], [connection])

    kinds = {(edge.kind, edge.source, edge.target) for edge in edges}
    assert ("runs", str(device.id), str(process.id)) in kinds
    assert ("binds", str(process.id), str(connection.id)) in kinds


def test_talks_to_edge_is_cross_device_and_flagged_heuristic():
    web = _device(hostname="web-01", ip_address="10.0.4.11")
    app = _device(hostname="app-01", ip_address="10.0.8.21")
    process = _process(web)
    # web-01's ssh client talking to app-01's address — the seed's
    # lateral-movement shape.
    connection = _connection(web, process, remote_ip="10.0.8.21", remote_port=22)

    edges = derive_edges([web, app], [process], [connection])

    talks = [edge for edge in edges if edge.kind == "talks-to"]
    assert len(talks) == 1
    assert talks[0].source == str(web.id)
    assert talks[0].target == str(app.id)
    assert talks[0].heuristic is True


def test_connection_to_the_devices_own_address_makes_no_edge():
    device = _device(hostname="web-01", ip_address="10.0.4.11")
    connection = _connection(device, remote_ip="10.0.4.11", remote_port=8443)

    talks = [
        edge
        for edge in derive_edges([device], [], [connection])
        if edge.kind == "talks-to"
    ]
    assert talks == []


def test_repeated_observations_of_one_pair_collapse_to_one_edge():
    web = _device(hostname="web-01", ip_address="10.0.4.11")
    app = _device(hostname="app-01", ip_address="10.0.8.21")
    first = _connection(web, remote_ip="10.0.8.21", remote_port=22)
    second = _connection(web, remote_ip="10.0.8.21", remote_port=2222)

    talks = [
        edge
        for edge in derive_edges([web, app], [], [first, second])
        if edge.kind == "talks-to"
    ]

    assert len(talks) == 1


def test_edges_never_reference_entities_the_payload_does_not_name():
    """A connection attributed to a process outside the (filtered) payload
    must not dangle."""
    web = _device(hostname="web-01", ip_address="10.0.4.11")
    other_process = _process(_device(hostname="elsewhere"))
    connection = _connection(web, other_process)

    edges = derive_edges([web], [], [connection])

    ids = {web.id}
    assert all(
        uuid.UUID(edge.source) in ids and uuid.UUID(edge.target) in ids
        for edge in edges
    )

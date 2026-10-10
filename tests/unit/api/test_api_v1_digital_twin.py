"""Route-level tests for the digital-twin v1 contract (``/api/v1/digital-twin``).

The idempotency and race guarantees are database behavior — ``ON CONFLICT``
upserts against the natural-key indexes — so these tests run against a real
throwaway PostgreSQL database (the ``external_service`` mark) with the real
unit-of-work dependency, not session fakes. The demo seed
(``scripts/seed_digital_twin_demo.py``) is the shared fixture data: re-running
it through the API must land on the seed's own rows, which is the parity
contract ``tests/unit/twin/test_digital_twin_ingest.py`` pins at the
derivation level.
"""

from __future__ import annotations

import importlib.util
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.api.v1.digital_twin_router import ROUTER_META
from core.api.v1.digital_twin_router import router as twin_router
from core.storage.connection import get_db_session
from core.storage.models import TwinConnection, TwinDevice, TwinProcess
from core.storage.schemas.digital_twin import TwinIngestBatch
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow
from core.twin.ingest import ingest_batch
from services.api.middleware.auth import get_current_active_user

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def seed():
    """The demo seed module, loaded from ``scripts/`` (not a package)."""
    spec = importlib.util.spec_from_file_location(
        "seed_digital_twin_demo", REPO_ROOT / "scripts" / "seed_digital_twin_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed_batch(seed):
    """The demo batch as JSON, validated through the ingest schema."""
    return TwinIngestBatch(**seed.build_demo_batch()).model_dump(mode="json")


@pytest.fixture(autouse=True)
def clean_twin_tables():
    """The throwaway database lives for the whole session; every test starts
    from an empty twin."""
    db = get_db_session()
    for model in (TwinConnection, TwinProcess, TwinDevice):
        db.query(model).delete()
    db.commit()
    db.close()
    yield
    db = get_db_session()
    for model in (TwinConnection, TwinProcess, TwinDevice):
        db.query(model).delete()
    db.commit()
    db.close()


def _mount_twin(application: FastAPI) -> None:
    """Mount the twin router the way ``services/api/discovery.py`` does for an
    ``Auth.REQUIRED`` router: the active-user dependency, at every advertised
    prefix (the versioned contract and its legacy alias)."""
    for prefix in (ROUTER_META.prefix, *ROUTER_META.legacy_prefixes):
        application.include_router(
            twin_router, prefix=prefix, dependencies=[Depends(get_current_active_user)]
        )


@pytest.fixture()
def twin_app(authenticate_app):
    application = FastAPI()
    authenticate_app(application)
    _mount_twin(application)
    return application


@pytest.fixture()
def client(twin_app):
    return TestClient(twin_app)


def _twin_row_counts():
    db = get_db_session()
    try:
        return (
            db.query(TwinDevice).count(),
            db.query(TwinProcess).count(),
            db.query(TwinConnection).count(),
        )
    finally:
        db.close()


# --- ingest: idempotency and the seed parity contract ---------------------------


def test_seed_batch_reposts_idempotently_through_the_api(client, seed_batch):
    """The seed, posted through the API twice, lands on its own rows — closing
    the seed PR's unverified end-to-end note at the API level."""
    first = client.post("/api/v1/digital-twin/ingest", json=seed_batch)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "source": "seed",
        "devices": len(seed_batch["devices"]),
        "processes": len(seed_batch["processes"]),
        "connections": len(seed_batch["connections"]),
    }

    second = client.post("/api/v1/digital-twin/ingest", json=seed_batch)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()

    assert _twin_row_counts() == (
        len(seed_batch["devices"]),
        len(seed_batch["processes"]),
        len(seed_batch["connections"]),
    )


def test_reposting_bumps_last_seen_without_touching_counts(
    client, seed_batch, monkeypatch
):
    """A re-post is the feed's "still here" signal: same rows, later clock."""
    import core.twin.ingest as ingest_module

    class _Clock:
        """Steppable stand-in for ``core.time.utcnow`` — naive UTC by design
        (the twin columns are naive ``DateTime``; see ``core/time.py``)."""

        def __init__(self, start):
            self.now = start

        def __call__(self):
            return self.now

    clock = _Clock(datetime(2026, 10, 9, 12, 0, 0))  # naive UTC, like the house clock
    monkeypatch.setattr(ingest_module, "utcnow", clock)

    assert (
        client.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 200
    )
    first_seen_at = clock.now
    clock.now = clock.now + timedelta(seconds=1)
    assert (
        client.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 200
    )

    db = get_db_session()
    try:
        device_last_seen = {row.last_seen for row in db.query(TwinDevice).all()}
        process_last_seen = {row.last_seen for row in db.query(TwinProcess).all()}
        connection_last_seen = {row.last_seen for row in db.query(TwinConnection).all()}
        first_seens = {row.first_seen for row in db.query(TwinDevice).all()}
    finally:
        db.close()

    assert device_last_seen == {clock.now}
    assert process_last_seen == {clock.now}
    assert connection_last_seen == {clock.now}
    assert first_seens == {first_seen_at}


def test_concurrent_reposts_do_not_duplicate_rows(seed_batch):
    """Feeds posting the same batch at once serialize on the natural-key
    indexes: one row per observation, no 500s, no duplicates."""
    batch = TwinIngestBatch(**seed_batch)

    errors: list[Exception] = []

    def _post():
        try:
            with unit_of_work() as session:
                ingest_batch(session, batch)
        except Exception as exc:  # asserted below, never swallowed silently
            errors.append(exc)

    threads = [threading.Thread(target=_post) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert _twin_row_counts() == (
        len(batch.devices),
        len(batch.processes),
        len(batch.connections),
    )


def test_hostname_and_device_key_references_resolve_to_one_row(client):
    """The same process, referenced by bare hostname and then by its device
    key (the two accepted forms), lands on one row."""
    assert (
        client.post(
            "/api/v1/digital-twin/ingest",
            json={
                "source": "test",
                "devices": [{"hostname": "web-01"}],
                "processes": [],
                "connections": [],
            },
        ).status_code
        == 200
    )
    process_by_hostname = {
        "source": "test",
        "devices": [],
        "processes": [{"device": "web-01", "pid": 1204, "name": "nginx"}],
        "connections": [],
    }
    assert (
        client.post("/api/v1/digital-twin/ingest", json=process_by_hostname).status_code
        == 200
    )
    process_by_key = {
        "source": "test",
        "devices": [],
        "processes": [{"device": "host:web-01", "pid": 1204, "name": "nginx"}],
        "connections": [],
    }
    assert (
        client.post("/api/v1/digital-twin/ingest", json=process_by_key).status_code
        == 200
    )

    devices, processes, _ = _twin_row_counts()
    assert (devices, processes) == (1, 1)


def test_device_level_connection_without_process_ingests(client):
    """A flow the sensor saw but could not attribute still lands, at device
    level — never dropped, never dangling."""
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"hostname": "fw-01"}],
            "processes": [],
            "connections": [
                {
                    "device": "fw-01",
                    "connection_type": "stream",
                    "protocol": "udp",
                    "local_ip": "10.0.1.1",
                    "local_port": 514,
                    "direction": "inbound",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text

    graph = client.get("/api/v1/digital-twin/graph").json()
    assert len(graph["connections"]) == 1
    assert graph["connections"][0]["process_id"] is None
    assert not [edge for edge in graph["edges"] if edge["kind"] == "binds"]


# --- ingest: validation ---------------------------------------------------------


def test_unknown_device_reference_is_422_with_field_detail(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [],
            "processes": [{"device": "host:nowhere", "pid": 1, "name": "nginx"}],
            "connections": [],
        },
    )
    assert response.status_code == 422
    assert "host:nowhere" in response.text
    assert "processes[].device" in response.text


def test_unknown_process_reference_is_422(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"hostname": "web-01"}],
            "processes": [],
            "connections": [
                {
                    "process": {"device": "web-01", "pid": 1204, "name": "nginx"},
                    "connection_type": "socket",
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "nginx" in response.text


def test_invalid_connection_type_is_422(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"hostname": "web-01"}],
            "processes": [],
            "connections": [{"device": "web-01", "connection_type": "tunnel"}],
        },
    )
    assert response.status_code == 422
    assert "connection_type" in response.text


def test_connection_with_neither_device_nor_process_is_422(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"hostname": "web-01"}],
            "processes": [],
            "connections": [{"connection_type": "socket"}],
        },
    )
    assert response.status_code == 422


def test_malformed_mac_is_422(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"hostname": "web-01", "mac_address": "not-a-mac"}],
            "processes": [],
            "connections": [],
        },
    )
    assert response.status_code == 422
    assert "mac_address" in response.text


def test_identity_less_device_is_422(client):
    response = client.post(
        "/api/v1/digital-twin/ingest",
        json={
            "source": "test",
            "devices": [{"device_type": "server"}],
            "processes": [],
            "connections": [],
        },
    )
    assert response.status_code == 422


# --- reads: graph shape, scoping, and the heuristic edge ------------------------


def test_graph_returns_layered_payload_with_attributes_and_derived_edges(
    client, seed_batch
):
    assert (
        client.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 200
    )

    body = client.get("/api/v1/digital-twin/graph").json()

    assert set(body) >= {
        "generated_at",
        "devices",
        "processes",
        "connections",
        "edges",
    }
    assert len(body["devices"]) == len(seed_batch["devices"])
    assert len(body["processes"]) == len(seed_batch["processes"])
    assert len(body["connections"]) == len(seed_batch["connections"])

    # Entity attributes: MAC and serial on devices, pid on processes, the
    # 5-tuple on connections.
    web = next(d for d in body["devices"] if d["hostname"] == "web-01")
    assert web["device_key"] == "host:web-01"
    assert web["mac_address"] and ":" in web["mac_address"]
    assert web["serial_number"]
    assert all(isinstance(p["pid"], int) for p in body["processes"])
    assert all(
        c["local_port"] is not None or c["remote_port"] is not None
        for c in body["connections"]
    )

    # The three edge families, and no dangling references.
    kinds = {edge["kind"] for edge in body["edges"]}
    assert kinds == {"runs", "binds", "talks-to"}
    named_ids = (
        {d["id"] for d in body["devices"]}
        | {p["id"] for p in body["processes"]}
        | {c["id"] for c in body["connections"]}
    )
    assert all(
        edge["source"] in named_ids and edge["target"] in named_ids
        for edge in body["edges"]
    )

    # The seed's lateral-movement narrative: web-01's ssh client talking to
    # app-01 surfaces as a heuristic cross-device edge.
    by_host = {d["hostname"]: d["id"] for d in body["devices"]}
    talks_to = [edge for edge in body["edges"] if edge["kind"] == "talks-to"]
    assert talks_to
    assert all(edge["heuristic"] is True for edge in talks_to)
    assert any(
        edge["source"] == by_host["web-01"] and edge["target"] == by_host["app-01"]
        for edge in talks_to
    )


def test_graph_scopes_to_one_device(client, seed_batch):
    assert (
        client.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 200
    )

    devices = client.get("/api/v1/digital-twin/devices").json()
    assert devices["total"] == len(seed_batch["devices"])
    web = next(d for d in devices["devices"] if d["hostname"] == "web-01")
    assert web["device_key"] == "host:web-01"

    scoped = client.get(f"/api/v1/digital-twin/graph?device_id={web['id']}").json()
    assert [d["id"] for d in scoped["devices"]] == [web["id"]]
    assert scoped["processes"]
    assert all(p["device_id"] == web["id"] for p in scoped["processes"])


def test_graph_since_filter_excludes_stale_observations(client, seed_batch):
    assert (
        client.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 200
    )

    future = utcnow() + timedelta(days=1)
    body = client.get("/api/v1/digital-twin/graph", params={"since": future}).json()

    assert body["devices"] == []
    assert body["processes"] == []
    assert body["connections"] == []
    assert body["edges"] == []


def test_legacy_prefix_serves_the_same_contract(client, seed_batch):
    response = client.post("/api/digital-twin/ingest", json=seed_batch)
    assert response.status_code == 200, response.text
    assert response.json()["devices"] == len(seed_batch["devices"])
    assert client.get("/api/digital-twin/graph").json()["devices"]


# --- the auth gate --------------------------------------------------------------


def test_unauthenticated_requests_are_401(seed_batch):
    """Mounted the way discovery mounts every ``Auth.REQUIRED`` router — the
    active-user dependency, and no authenticated user in place. The root
    conftest forces DEV_MODE off, so this exercises the real cookie/JWT path,
    and no route answers without a session."""
    application = FastAPI()
    _mount_twin(application)
    bare = TestClient(application)

    assert bare.get("/api/v1/digital-twin/graph").status_code == 401
    assert bare.get("/api/v1/digital-twin/devices").status_code == 401
    assert bare.post("/api/v1/digital-twin/ingest", json=seed_batch).status_code == 401

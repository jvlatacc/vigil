"""MTD registry and never-route exclusions against Postgres.

The round-trips the no-DB contract tests in ``test_mtd_models.py`` cannot
see: rows survive the commit, the partial uniques and check constraints are
refused by the server, and removing a never-route entry is a recorded
status transition — the row is still there afterwards.

Runs on the throwaway database tests/unit/conftest.py provisions per process.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.storage.models import MtdDecoyRegistry, MtdIpExclusion
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


@pytest.fixture(autouse=True)
def _clean():
    with unit_of_work() as session:
        session.query(MtdIpExclusion).delete()
        session.query(MtdDecoyRegistry).delete()
    yield
    with unit_of_work() as session:
        session.query(MtdIpExclusion).delete()
        session.query(MtdDecoyRegistry).delete()


def _add_decoy(name="ssh-decoy-01", **kw):
    row = MtdDecoyRegistry(
        decoy_id=kw.pop("decoy_id", f"decoy-{name}"),
        name=name,
        kind=kw.pop("kind", "ssh"),
        endpoint=kw.pop("endpoint", f"{name}:2222"),
        canary_credential_ref=kw.pop(
            "canary_credential_ref", f"honey_router.canary.{name}"
        ),
        **kw,
    )
    with unit_of_work() as session:
        session.add(row)
    return row


def _add_exclusion(ip="203.0.113.7", **kw):
    row = MtdIpExclusion(
        exclusion_id=kw.pop("exclusion_id", f"mtdexcl-{abs(hash(ip)) % 16**16:016x}"),
        ip=ip,
        reason=kw.pop("reason", "production host, never route"),
        added_by=kw.pop("added_by", "analyst-1"),
        **kw,
    )
    with unit_of_work() as session:
        session.add(row)
    return row


def _fetch(model, **filters):
    with unit_of_work() as session:
        rows = session.scalars(select(model).filter_by(**filters)).all()
        # Detach so the assertions read what Postgres holds, not the cache.
        session.expunge_all()
    return rows


# --- the decoy registry -------------------------------------------------------


def test_a_registered_decoy_round_trips_through_postgres():
    _add_decoy(
        decoy_id="decoy-fixed",
        name="http-decoy-01",
        kind="http",
        endpoint="http-decoy-01:8080",
        canary_credential_ref="honey_router.canary.http-decoy-01",
        rotated_at=utcnow(),
    )
    (row,) = _fetch(MtdDecoyRegistry, decoy_id="decoy-fixed")
    assert row.name == "http-decoy-01"
    assert row.kind == "http"
    assert row.endpoint == "http-decoy-01:8080"
    assert row.canary_credential_ref == "honey_router.canary.http-decoy-01"
    assert row.rotated_at is not None


def test_insert_fills_the_defaults_the_server_owns():
    _add_decoy(decoy_id="decoy-defaults")
    (row,) = _fetch(MtdDecoyRegistry, decoy_id="decoy-defaults")
    assert row.status == "active"
    assert row.created_at is not None
    assert row.updated_at is not None
    assert row.rotated_at is None


def test_two_active_decoys_cannot_share_a_name():
    _add_decoy(decoy_id="decoy-first", name="ssh-decoy-01")
    with pytest.raises(IntegrityError):
        _add_decoy(decoy_id="decoy-second", name="ssh-decoy-01")


def test_a_retired_decoys_name_is_free_again_and_the_row_is_kept():
    _add_decoy(decoy_id="decoy-one", name="ssh-decoy-01")
    with unit_of_work() as session:
        retired = session.get(MtdDecoyRegistry, "decoy-one")
        retired.status = "retired"
    _add_decoy(decoy_id="decoy-two", name="ssh-decoy-01")

    rows = _fetch(MtdDecoyRegistry, name="ssh-decoy-01")
    assert sorted(r.decoy_id for r in rows) == ["decoy-one", "decoy-two"]
    assert {r.status for r in rows} == {"retired", "active"}


def test_a_decoy_kind_outside_ssh_http_is_refused():
    with pytest.raises(IntegrityError):
        _add_decoy(decoy_id="decoy-ftp", kind="ftp")


# --- the never-route exclusions -----------------------------------------------


def test_a_never_route_row_round_trips_with_defaults():
    _add_exclusion(exclusion_id="mtdexcl-fixed", ip="203.0.113.7")
    (row,) = _fetch(MtdIpExclusion, exclusion_id="mtdexcl-fixed")
    assert row.ip == "203.0.113.7"
    assert row.reason == "production host, never route"
    assert row.added_by == "analyst-1"
    assert row.status == "active"
    assert row.added_at is not None
    assert row.removed_at is None and row.removed_by is None


def test_removal_is_a_recorded_status_transition_the_row_is_kept():
    _add_exclusion(exclusion_id="mtdexcl-removal")
    when = utcnow()
    with unit_of_work() as session:
        row = session.get(MtdIpExclusion, "mtdexcl-removal")
        row.status = "removed"
        row.removed_at = when
        row.removed_by = "analyst-2"

    # A fresh session: the row is still there, transition recorded.
    rows = _fetch(MtdIpExclusion, exclusion_id="mtdexcl-removal")
    assert len(rows) == 1
    removed = rows[0]
    assert removed.status == "removed"
    assert removed.removed_by == "analyst-2"
    assert removed.removed_at == when
    assert removed.reason == "production host, never route"


def test_one_active_never_route_row_per_address():
    _add_exclusion(exclusion_id="mtdexcl-first", ip="203.0.113.7")
    with pytest.raises(IntegrityError):
        _add_exclusion(exclusion_id="mtdexcl-second", ip="203.0.113.7")


def test_a_removed_address_can_be_never_routed_again():
    _add_exclusion(exclusion_id="mtdexcl-first", ip="203.0.113.7")
    with unit_of_work() as session:
        row = session.get(MtdIpExclusion, "mtdexcl-first")
        row.status = "removed"
        row.removed_at = utcnow()
        row.removed_by = "analyst-2"
    _add_exclusion(exclusion_id="mtdexcl-second", ip="203.0.113.7")

    rows = _fetch(MtdIpExclusion, ip="203.0.113.7")
    assert sorted(r.exclusion_id for r in rows) == [
        "mtdexcl-first",
        "mtdexcl-second",
    ]
    assert {r.status for r in rows} == {"removed", "active"}


@pytest.mark.parametrize(
    "status, removed_at, removed_by",
    [
        ("removed", None, "analyst-2"),  # removal without the record
        ("active", "set", "analyst-2"),  # a record without the transition
    ],
)
def test_status_and_the_removal_record_cannot_disagree(status, removed_at, removed_by):
    with pytest.raises(IntegrityError):
        _add_exclusion(
            exclusion_id="mtdexcl-disagree",
            status=status,
            removed_at=utcnow() if removed_at == "set" else None,
            removed_by=removed_by,
        )

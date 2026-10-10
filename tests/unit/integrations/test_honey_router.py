"""Unit tests for the honey-router's pure helpers and dispatch seams.

No database, no kubernetes client: registry lookups are faked at
``core.storage.connection.get_db_manager`` and backends at the module's
``get_backend``/``resolve_decoy`` seams. These tests run in the no-DB CI
job (no ``external_service`` marker).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest

import core.storage.connection as storage_connection
from core.integrations.honey_router import route as hr
from core.integrations.honey_router.route import (
    DecoyResolution,
    DecoyTarget,
    get_backend,
    is_route_expired,
    list_active_decoys,
    needs_unroute,
    parse_endpoint,
    resolve_decoy,
    route,
    unroute,
)
from core.time import utcnow

NOW = utcnow()


def _decoy_row(**overrides):
    row = SimpleNamespace(
        decoy_id="decoy-ssh-01",
        name="SSH decoy",
        kind="ssh",
        endpoint="10.42.0.77:2222",
        status="active",
        rotated_at=None,
        canary_credential_ref="vault:canary/ssh-01",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _decoy_target():
    return DecoyTarget(
        decoy_id="decoy-ssh-01",
        name="SSH decoy",
        kind="ssh",
        endpoint_host="10.42.0.77",
        endpoint_port=2222,
        namespace="vigil-decoys",
    )


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows if isinstance(rows, list) else [rows]

    def get(self, model, decoy_id):
        for row in self._rows:
            if row is not None and row.decoy_id == decoy_id:
                return row
        return None

    def query(self, model):
        return _FakeQuery([r for r in self._rows if r is not None])


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    @contextmanager
    def session_scope(self):
        yield _FakeSession(self._rows)


class _RecordingBackend:
    name = "fake"

    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"success": True, "backend": "fake"}

    def route(self, attacker_ip, decoy):
        self.calls.append(("route", attacker_ip, decoy.decoy_id))
        return dict(self.result)

    def unroute(self, attacker_ip):
        self.calls.append(("unroute", attacker_ip))
        return dict(self.result)


class TestParseEndpoint:
    def test_host_port(self):
        assert parse_endpoint("10.42.0.77:2222") == ("10.42.0.77", 2222)

    def test_bracketed_ipv6(self):
        assert parse_endpoint("[2001:db8::1]:22") == ("2001:db8::1", 22)

    def test_missing_port_raises(self):
        with pytest.raises(ValueError, match="no port"):
            parse_endpoint("10.42.0.77")

    def test_non_numeric_port_raises(self):
        with pytest.raises(ValueError):
            parse_endpoint("10.42.0.77:ssh")

    def test_out_of_range_port_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_endpoint("10.42.0.77:99999")


class TestResolveDecoy:
    def _patch_db(self, monkeypatch, rows):
        monkeypatch.setattr(storage_connection, "get_db_manager", lambda: _FakeDb(rows))

    def test_active_row_resolves_to_target(self, monkeypatch):
        self._patch_db(monkeypatch, _decoy_row())
        resolution = resolve_decoy("decoy-ssh-01", "vigil-decoys")
        assert resolution.ok
        assert resolution.target == _decoy_target()

    def test_missing_row_is_a_named_refusal(self, monkeypatch):
        self._patch_db(monkeypatch, [None])
        resolution = resolve_decoy("ghost", "vigil-decoys")
        assert not resolution.ok
        assert resolution.error == "decoy_not_found"

    def test_retired_decoy_never_routes(self, monkeypatch):
        self._patch_db(monkeypatch, _decoy_row(status="retired"))
        resolution = resolve_decoy("decoy-ssh-01", "vigil-decoys")
        assert not resolution.ok
        assert resolution.error == "decoy_retired"

    def test_malformed_endpoint_is_caught_not_raised(self, monkeypatch):
        self._patch_db(monkeypatch, _decoy_row(endpoint="no-port-here"))
        resolution = resolve_decoy("decoy-ssh-01", "vigil-decoys")
        assert not resolution.ok
        assert resolution.error == "malformed_endpoint"


class TestGetBackend:
    def test_default_backend_is_cilium(self, monkeypatch):
        monkeypatch.setattr(
            hr, "resolve", lambda descriptor: {"backend": "", "namespace": "default"}
        )
        backend, err = get_backend()
        assert backend is not None and backend.name == "cilium"
        assert err == ""

    def test_unknown_backend_is_a_named_failure(self, monkeypatch):
        monkeypatch.setattr(
            hr, "resolve", lambda descriptor: {"backend": "fog", "namespace": ""}
        )
        backend, err = get_backend()
        assert backend is None
        assert "fog" in err


class TestRouteDispatch:
    @pytest.fixture(autouse=True)
    def _deterministic_namespace(self, monkeypatch):
        # route() resolves the namespace from integration config; pin it so
        # the dispatch tests never touch the real config resolver.
        monkeypatch.setattr(
            hr,
            "resolve",
            lambda descriptor: {"backend": "cilium", "namespace": "vigil-decoys"},
        )

    def test_success_carries_decoy_and_ttl_for_the_audit_trail(self, monkeypatch):
        monkeypatch.setattr(
            hr, "resolve_decoy", lambda decoy_id, ns: DecoyResolution(_decoy_target())
        )
        backend = _RecordingBackend()
        monkeypatch.setattr(hr, "get_backend", lambda: (backend, ""))
        result = route("203.0.113.7", "decoy-ssh-01", ttl_seconds=3600)
        assert result["success"] is True
        assert result["decoy_id"] == "decoy-ssh-01"
        assert result["session_ttl_seconds"] == 3600
        assert backend.calls == [("route", "203.0.113.7", "decoy-ssh-01")]

    def test_unknown_decoy_routes_nothing(self, monkeypatch):
        monkeypatch.setattr(
            hr,
            "resolve_decoy",
            lambda decoy_id, ns: DecoyResolution(None, error="decoy_not_found"),
        )
        backend = _RecordingBackend()
        monkeypatch.setattr(hr, "get_backend", lambda: (backend, ""))
        result = route("203.0.113.7", "ghost", ttl_seconds=3600)
        assert result == {
            "success": False,
            "error": "decoy_not_found",
            "message": "Decoy 'ghost' cannot receive routes",
        }
        assert backend.calls == []

    def test_backend_failure_is_returned_verbatim(self, monkeypatch):
        monkeypatch.setattr(
            hr, "resolve_decoy", lambda decoy_id, ns: DecoyResolution(_decoy_target())
        )
        backend = _RecordingBackend(result={"success": False, "error": "boom"})
        monkeypatch.setattr(hr, "get_backend", lambda: (backend, ""))
        result = route("203.0.113.7", "decoy-ssh-01")
        assert result["success"] is False
        assert result["error"] == "boom"

    def test_no_backend_at_all_is_honest(self, monkeypatch):
        monkeypatch.setattr(
            hr, "resolve_decoy", lambda decoy_id, ns: DecoyResolution(_decoy_target())
        )
        monkeypatch.setattr(hr, "get_backend", lambda: (None, "no such backend"))
        result = route("203.0.113.7", "decoy-ssh-01")
        assert result["success"] is False
        assert result["error"] == "no_route_backend"

    def test_unroute_dispatches_to_backend(self, monkeypatch):
        backend = _RecordingBackend()
        monkeypatch.setattr(hr, "get_backend", lambda: (backend, ""))
        result = unroute("203.0.113.7")
        assert result["success"] is True
        assert backend.calls == [("unroute", "203.0.113.7")]


class TestIsRouteExpired:
    def test_expired_when_ttl_has_passed(self):
        executed = NOW - timedelta(hours=2)
        assert is_route_expired(executed.isoformat(), 3600, NOW) is True

    def test_not_expired_within_ttl(self):
        executed = NOW - timedelta(minutes=5)
        assert is_route_expired(executed.isoformat(), 3600, NOW) is False

    def test_missing_ttl_never_expires(self):
        executed = NOW - timedelta(hours=99)
        assert is_route_expired(executed.isoformat(), None, NOW) is False

    def test_missing_executed_at_never_expires(self):
        assert is_route_expired(None, 3600, NOW) is False
        assert is_route_expired("", 3600, NOW) is False

    def test_naive_executed_at_is_interpreted_in_now_timezone(self):
        naive = (NOW - timedelta(hours=2)).replace(tzinfo=None)
        assert is_route_expired(naive.isoformat(), 3600, NOW) is True

    def test_naive_and_aware_datetimes_compare_cleanly(self):
        # Naive now (core.time.utcnow convention) against an aware
        # executed_at — and the reverse — must compare cleanly, never
        # raise mid-sweep and never silently mis-order.
        from datetime import timezone

        now_naive = NOW.replace(tzinfo=None)
        expired_aware = (NOW - timedelta(hours=2)).replace(tzinfo=timezone.utc)
        fresh_aware = NOW.replace(tzinfo=timezone.utc)
        assert is_route_expired(expired_aware.isoformat(), 3600, now_naive) is True
        assert is_route_expired(fresh_aware.isoformat(), 3600, now_naive) is False

    def test_unparseable_values_never_expire(self):
        executed = NOW - timedelta(hours=2)
        assert is_route_expired(executed.isoformat(), "not-a-number", NOW) is False
        assert is_route_expired(12345, 3600, NOW) is False
        assert is_route_expired(executed.isoformat(), {"bad": 1}, NOW) is False


class TestNeedsUnroute:
    def test_no_result_means_needs_unroute(self):
        assert needs_unroute(None) is True
        assert needs_unroute({}) is True

    def test_failed_or_missing_reversal_keeps_retrying(self):
        assert needs_unroute({"reversal": {"success": False}}) is True
        assert needs_unroute({"reversal": {}}) is True

    def test_successful_reversal_suppresses(self):
        assert needs_unroute({"reversal": {"success": True}}) is False


class TestListActiveDecoys:
    def test_listing_never_includes_canary_credential_ref(self, monkeypatch):
        rows = [
            _decoy_row(),
            _decoy_row(decoy_id="decoy-http-01", kind="http"),
        ]
        monkeypatch.setattr(storage_connection, "get_db_manager", lambda: _FakeDb(rows))
        items = list_active_decoys()
        assert [item["decoy_id"] for item in items] == [
            "decoy-ssh-01",
            "decoy-http-01",
        ]
        assert all("canary_credential_ref" not in item for item in items)

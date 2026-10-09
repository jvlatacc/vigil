"""The Settings surface cannot weaken the never-quarantine floor.

The environment wins: an entry DAEMON_NEVER_QUARANTINE protects is refused
with the same 409 the Act override gets, an entry that does not parse is
refused with a 422 that says why, and the merged view shows the floor first
and marks it not removable.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.api.routers.config import (
    ProtectedTargetEntry,
    add_protected_target,
    list_protected_targets,
    remove_protected_target,
)

pytestmark = pytest.mark.unit

ROUTER = "services.api.routers.config"


def _settings(**attrs):
    settings = SimpleNamespace(daemon_never_quarantine=("ip:10.0.0.5",))
    for key, value in attrs.items():
        setattr(settings, key, value)
    return settings


def _user():
    return SimpleNamespace(user_id="user-1")


def _db_manager():
    manager = MagicMock()

    @contextmanager
    def _scope():
        yield MagicMock()

    manager.session_scope = _scope
    return manager


class TestRemoveProtectedTarget:
    def test_removing_an_environment_entry_is_refused(self):
        with patch(f"{ROUTER}.get_settings", return_value=_settings()):
            with pytest.raises(HTTPException) as err:
                remove_protected_target(
                    kind="ip", value="10.0.0.5", current_user=_user()
                )
        assert err.value.status_code == 409
        assert "The environment wins" in err.value.detail

    def test_an_unparseable_entry_is_refused_with_why(self):
        with patch(f"{ROUTER}.get_settings", return_value=_settings()):
            with pytest.raises(HTTPException) as err:
                remove_protected_target(
                    kind="ip", value="10.0.0.256", current_user=_user()
                )
        assert err.value.status_code == 422
        assert "10.0.0.256" in err.value.detail


class TestAddProtectedTarget:
    def test_an_operator_row_tightens_and_the_floor_stays_first(self):
        def _active_rows(session):
            # The view re-reads the store: the floor plus the row just added.
            return [
                SimpleNamespace(
                    kind="ip",
                    value="10.0.0.5",
                    origin="env",
                    reason="",
                    created_by="environment",
                    created_at=None,
                ),
                SimpleNamespace(
                    kind="cidr",
                    value="10.60.0.0/16",
                    origin="operator",
                    reason="the SCADA ring",
                    created_by="user-1",
                    created_at=None,
                ),
            ]

        with (
            patch(f"{ROUTER}.get_settings", return_value=_settings()),
            patch("core.storage.connection.get_db_manager", return_value=_db_manager()),
            patch(
                "core.storage.protected_target_repository.active_row_for",
                return_value=None,
            ),
            patch(
                "core.storage.protected_target_repository.active_rows",
                side_effect=_active_rows,
            ),
        ):
            response = add_protected_target(
                entry=ProtectedTargetEntry(
                    kind="cidr", value="10.60.0.0/16", reason="the SCADA ring"
                ),
                current_user=_user(),
            )
        assert response.targets[0].origin == "env"
        assert response.targets[0].removable is False
        added = response.targets[-1]
        assert (added.kind, added.value, added.origin) == (
            "cidr",
            "10.60.0.0/16",
            "operator",
        )
        assert added.created_by == "user-1"
        assert added.removable is True

    def test_a_duplicate_is_refused(self):
        db = _db_manager()
        with (
            patch(f"{ROUTER}.get_settings", return_value=_settings()),
            patch("core.storage.connection.get_db_manager", return_value=db),
            patch(
                "core.storage.protected_target_repository.active_row_for",
                return_value=SimpleNamespace(kind="ip", value="10.0.0.9"),
            ),
        ):
            with pytest.raises(HTTPException) as err:
                add_protected_target(
                    entry=ProtectedTargetEntry(
                        kind="ip", value="10.0.0.9", reason="already"
                    ),
                    current_user=_user(),
                )
        assert err.value.status_code == 409


class TestListProtectedTargets:
    def test_the_merged_view_marks_the_floor_not_removable(self):
        row = SimpleNamespace(
            kind="hostname_glob",
            value="*.corp.example",
            origin="operator",
            reason="the office range",
            created_by="user-2",
            created_at=None,
        )

        def _active_rows(session):
            return [row]

        with (
            patch(f"{ROUTER}.get_settings", return_value=_settings()),
            patch("core.storage.connection.get_db_manager", return_value=_db_manager()),
            patch(
                "core.storage.protected_target_repository.active_rows",
                side_effect=_active_rows,
            ),
        ):
            response = list_protected_targets()
        assert [t.origin for t in response.targets] == ["env", "operator"]
        assert [t.removable for t in response.targets] == [False, True]
        assert response.unparsed == []

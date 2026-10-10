"""Integration credentials never sit plaintext, and previews stay anonymous.

Three hygiene properties, pinned hermetically (no database, no network):

- A canary saved through the real save handler round-trips into the
  encrypted store and never into the ``integration_configs`` row (E7).
- The startup migration sweeps a legacy plaintext row into the store and
  scrubs the row, preserving ``enabled`` and the non-secret fields, and
  lets the store win on conflicts.
- A credential-shaped value in an unregistered field is refused with a 400
  that names the field — never silently persisted (E7).
- Token previews expose at most the last four characters (E6).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")

from core.deps import provide_integration_bridge  # noqa: E402
from core.integrations.integration_secrets import (  # noqa: E402
    env_var_for,
    migrate_plaintext_credentials,
    unregistered_credential_fields,
)
from core.storage.models import User  # noqa: E402
from services.api import main as backend_main  # noqa: E402
from services.api.middleware import auth as auth_module  # noqa: E402
from services.api.routers import config as config_router  # noqa: E402

pytestmark = pytest.mark.unit

# A 36-character credential-shaped canary — the length of the secret
# portion E6 caught leaking through the previews.
CANARY = "4f9a2c7e1b8d" * 3


class FakeSecretStore:
    """In-memory stand-in for ``core.secrets.get_secret``/``set_secret``."""

    def __init__(self, values=None):
        self.values: dict = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value
        return True


class FakeConfigStore:
    """In-memory stand-in for ``ConfigService``'s integration rows."""

    def __init__(self, rows=None):
        self.rows: list = list(rows or [])
        self.writes: list = []

    def list_integrations(self, enabled_only=False):
        return [dict(row) for row in self.rows]

    def get_integration_config(self, integration_id):
        for row in self.rows:
            if row["integration_id"] == integration_id:
                return dict(row)
        return None

    def set_integration_config(self, integration_id, config, enabled=True, **kwargs):
        self.writes.append(
            {
                "integration_id": integration_id,
                "config": config,
                "enabled": enabled,
                "change_reason": kwargs.get("change_reason"),
            }
        )
        # Create-or-update, like ConfigService: a save of an integration
        # with no row yet lands as a new one.
        for row in self.rows:
            if row["integration_id"] == integration_id:
                row["config"] = config
                row["enabled"] = enabled
                break
        else:
            self.rows.append(
                {
                    "integration_id": integration_id,
                    "config": config,
                    "enabled": enabled,
                }
            )
        return True


@pytest.fixture
def hygiene_api(monkeypatch):
    """The real config router with storage and the secret store faked out.

    Yields a factory: ``client, config_store, secrets = hygiene_api()`` —
    the same fakes feed the handler and the assertions, so a test sees
    exactly what the API did and did not persist.
    """
    secrets = FakeSecretStore()
    holder: dict = {}

    monkeypatch.setattr(
        config_router, "get_config_service", lambda user_id="system": holder["store"]
    )
    monkeypatch.setattr(config_router, "set_secret", secrets.set)
    monkeypatch.setattr(config_router, "get_secret", secrets.get)
    # The JSON mirror is a filesystem side effect of the save handler, not
    # what these tests pin; the DB row and the store are.
    monkeypatch.setattr(config_router, "_mirror_to_file", lambda *a, **k: None)
    monkeypatch.setattr("core.integrations.integration_secrets.get_secret", secrets.get)
    monkeypatch.setattr("core.integrations.integration_secrets.set_secret", secrets.set)
    monkeypatch.setattr(
        "core.auth.auth_service.AuthService.check_permission",
        lambda user_id, perm, session=None: True,
    )

    app = backend_main.app
    admin = User(
        user_id="admin",
        username="arnold_admin",
        email="a@test.local",
        password_hash="",
        role_id="role-admin",
        is_active=True,
        mfa_enabled=False,
    )
    app.dependency_overrides[auth_module.get_current_active_user] = lambda: admin
    app.dependency_overrides[auth_module.get_current_user] = lambda: admin
    app.dependency_overrides[provide_integration_bridge] = lambda: MagicMock()

    def _make(rows=None):
        holder["store"] = FakeConfigStore(rows=rows)
        return TestClient(app), holder["store"], secrets

    yield _make

    for dep in (
        auth_module.get_current_active_user,
        auth_module.get_current_user,
        provide_integration_bridge,
    ):
        app.dependency_overrides.pop(dep, None)


# --- E7: the save path puts the canary in the store, not the row ------------


def test_a_saved_canary_round_trips_into_the_store(hygiene_api):
    client, store, secrets = hygiene_api()
    saved = client.post(
        "/api/config/integrations",
        json={
            "enabled_integrations": ["firecrawl"],
            "integrations": {
                "firecrawl": {
                    "api_key": CANARY,
                    "url": "https://firecrawl.example",
                }
            },
        },
    )
    assert saved.status_code == 200, saved.text

    env_key = env_var_for("firecrawl", "api_key")
    assert secrets.values[env_key] == CANARY
    # The DB row keeps the non-secret field and never sees the canary.
    assert store.rows[0]["config"] == {"url": "https://firecrawl.example"}


def test_a_credential_in_an_unregistered_field_is_refused(hygiene_api):
    client, store, secrets = hygiene_api()
    saved = client.post(
        "/api/config/integrations",
        json={
            "enabled_integrations": ["firecrawl"],
            "integrations": {
                "firecrawl": {
                    # Not typed as a password field, so not registered.
                    "custom_api_key": CANARY,
                    "url": "https://firecrawl.example",
                }
            },
        },
    )
    assert saved.status_code == 400, saved.text
    # The refusal names the field so the operator can register it — never
    # the value.
    assert "custom_api_key" in saved.text
    assert CANARY not in saved.text
    # Nothing was persisted anywhere.
    assert store.rows == []
    assert store.writes == []
    assert secrets.values == {}


def test_only_unregistered_credential_shaped_fields_are_flagged():
    # Registered fields ride the store path and are never flagged...
    assert unregistered_credential_fields("firecrawl", {"api_key": CANARY}) == []
    # ...non-credential-shaped unregistered fields are legitimate config...
    assert (
        unregistered_credential_fields(
            "firecrawl", {"host": "lab.example", "notes": "", "retries": 3}
        )
        == []
    )
    # ...and a credential-shaped unregistered one is named.
    assert unregistered_credential_fields("firecrawl", {"custom_api_key": CANARY}) == [
        "custom_api_key"
    ]


# --- E7: the migration scrubs legacy plaintext rows -------------------------


def _legacy_row():
    """A pre-secret-store row: the canary sits plaintext beside real config."""
    return {
        "integration_id": "firecrawl",
        "enabled": False,
        "config": {"api_key": CANARY, "url": "https://firecrawl.example"},
        "integration_name": "Firecrawl",
        "integration_type": None,
        "description": None,
    }


def test_the_migration_moves_a_legacy_row_into_the_store(monkeypatch):
    secrets = FakeSecretStore()
    monkeypatch.setattr("core.integrations.integration_secrets.get_secret", secrets.get)
    monkeypatch.setattr("core.integrations.integration_secrets.set_secret", secrets.set)
    store = FakeConfigStore(rows=[_legacy_row()])

    migrated = migrate_plaintext_credentials(store)

    env_key = env_var_for("firecrawl", "api_key")
    assert migrated == {"firecrawl": ["api_key"]}
    assert secrets.values[env_key] == CANARY
    # The row is scrubbed; the non-secret field and the disabled flag
    # survive the rewrite.
    assert store.rows[0]["config"] == {"url": "https://firecrawl.example"}
    assert store.writes[0]["enabled"] is False
    assert "encrypted store" in store.writes[0]["change_reason"]
    # Idempotent: a second sweep has nothing left to move.
    assert migrate_plaintext_credentials(store) == {}


def test_the_migration_lets_the_store_win_on_conflicts(monkeypatch):
    env_key = env_var_for("firecrawl", "api_key")
    # The store already holds the credential — saved after the legacy row
    # was written. The stale row plaintext must not resurrect itself.
    secrets = FakeSecretStore({env_key: "current-value"})
    monkeypatch.setattr("core.integrations.integration_secrets.get_secret", secrets.get)
    monkeypatch.setattr("core.integrations.integration_secrets.set_secret", secrets.set)
    store = FakeConfigStore(rows=[_legacy_row()])

    migrated = migrate_plaintext_credentials(store)

    assert migrated == {"firecrawl": ["api_key"]}
    assert secrets.values[env_key] == "current-value"
    assert store.rows[0]["config"] == {"url": "https://firecrawl.example"}


# --- E6: previews expose a tail, never a head -------------------------------


def test_the_github_token_preview_shows_only_a_tail(hygiene_api):
    client, _, secrets = hygiene_api()
    token = "ghp_" + "7f3b9d2e4c6a" * 3
    secrets.values["GITHUB_TOKEN"] = token

    got = client.get("/api/config/github")

    assert got.status_code == 200
    assert got.json()["token_preview"] == f"...{token[-4:]}"
    assert token[:12] not in got.text


def test_the_claude_key_preview_shows_only_a_tail(hygiene_api):
    client, _, secrets = hygiene_api()
    key = "sk-ant-" + "9a4c1e7b3f5d" * 3
    secrets.values["CLAUDE_API_KEY"] = key

    got = client.get("/api/config/claude")

    assert got.status_code == 200
    assert got.json()["key_preview"] == f"...{key[-4:]}"
    assert key[:8] not in got.text


def test_a_short_secret_gets_no_preview_at_all(hygiene_api):
    client, _, secrets = hygiene_api()
    secrets.values["GITHUB_TOKEN"] = "abc"

    got = client.get("/api/config/github")

    assert got.status_code == 200
    assert got.json() == {"configured": True, "token_preview": None}

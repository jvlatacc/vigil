"""Deny-by-default child environment for spawned MCP servers (E1).

Every spawned MCP server used to receive the backend's complete process
environment — ``JWT_SECRET_KEY``, ``AGENT_INTERNAL_TOKEN``, ``POSTGRES_PASSWORD``
and every integration token — because ``_initialize_servers`` built each child
env from ``os.environ.copy()``. One compromised community npx/uvx package
equaled full-platform compromise.

The contract now: a child's environment is the SDK's safe-to-inherit names plus
the CA bundle, ``VIGIL_DIR``/``PYTHONPATH``, the entry's own declared config env
(substituted), and — only for names the entry references or explicitly lists in
``required_env_vars`` — values forwarded from the ambient environment or the
secret store. Nothing else passes through.

The key-set ratchet fails on any new inherited name: if you add a legitimate
new base name, extend ``default_child_env()`` (and this test's expectations)
deliberately, not as a side effect of an env tweak elsewhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.integrations.mcp import service as mcp_service  # noqa: E402
from core.integrations.mcp.child_env import default_child_env  # noqa: E402
from core.integrations.mcp.service import (  # noqa: E402
    MCPService,
    extract_required_env_vars,
)

pytestmark = pytest.mark.unit

# Credential-shaped names a real backend holds. No shipped mcp-config.json
# entry references any of them; if one ever does, the planted-value ratchet
# below is the test that tells you — before the credential leaves the process.
AMBIENT_CREDENTIALS = {
    "JWT_SECRET_KEY": "jwt-signing-secret-canary",
    "AGENT_INTERNAL_TOKEN": "agent-internal-token-canary",
    "POSTGRES_PASSWORD": "postgres-password-canary",
    "POSTGRES_USER": "postgres-user-canary",
    "ANTHROPIC_API_KEY": "anthropic-api-key-canary",
    "STRIPE_SECRET_KEY": "stripe-secret-key-canary",
}


@pytest.fixture
def ambient_credentials(monkeypatch):
    """Plant credential-shaped values in the backend's process environment."""
    for key, value in AMBIENT_CREDENTIALS.items():
        monkeypatch.setenv(key, value)
    yield AMBIENT_CREDENTIALS


@pytest.fixture
def no_secret_store(monkeypatch):
    """The store answers nothing: only declared/referenced ambient names flow."""
    monkeypatch.setattr(mcp_service, "get_secret", lambda key, default=None: default)


def _entry_references(entry: dict, name: str) -> bool:
    """Whether an mcp-config entry names ``name`` anywhere it may resolve from."""
    declared = {
        k: v for k, v in (entry.get("env") or {}).items() if not k.startswith("_")
    }
    args = entry.get("args") or []
    if any(
        isinstance(v, str) and name in v for v in list(declared.values()) + list(args)
    ):
        return True
    return name in (entry.get("required_env_vars") or [])


def _load_shipped_servers():
    return MCPService(project_root=REPO)


def test_no_credential_shaped_variable_reaches_any_shipped_child(
    ambient_credentials, no_secret_store
):
    """The E1 canary: no planted credential value or name appears in any
    spawned server's environment, unless that server's own entry references it."""
    config = json.loads((REPO / "mcp-config.json").read_text())["mcpServers"]

    service = _load_shipped_servers()

    for name, server in service.servers.items():
        entry = config[name]
        for env_key in server.env:
            assert env_key not in AMBIENT_CREDENTIALS or _entry_references(
                entry, env_key
            ), (
                f"{name}: child env carries ambient credential {env_key}; "
                "its entry must declare it or list it in required_env_vars"
            )
        for env_value in server.env.values():
            for credential_value in AMBIENT_CREDENTIALS.values():
                assert credential_value not in env_value, (
                    f"{name}: a planted credential value leaked into the child "
                    "environment"
                )


def test_every_child_env_is_the_base_plus_what_its_entry_declares(
    ambient_credentials, no_secret_store
):
    """Ratchet: a child env is the default base plus names its own entry names.

    Any new key in a child's environment has to come from one of the designed
    sources — the SDK defaults, the CA bundle, VIGIL_DIR/PYTHONPATH, the
    entry's env block, or the names the entry references or opts in. An
    os.environ.copy() regressing anywhere in the loader fails here on the
    first inherited name it adds.
    """
    config = json.loads((REPO / "mcp-config.json").read_text())["mcpServers"]
    base = set(default_child_env()) | {"VIGIL_DIR", "PYTHONPATH"}

    service = _load_shipped_servers()

    for name, server in service.servers.items():
        entry = config[name]
        declared = {
            k: v for k, v in (entry.get("env") or {}).items() if not k.startswith("_")
        }
        referenced = set(
            extract_required_env_vars(declared, entry.get("args") or [])
        ) | set(entry.get("required_env_vars") or [])
        allowed = base | set(declared) | referenced
        unexpected = set(server.env) - allowed
        assert not unexpected, (
            f"{name}: child env inherited undeclared names {sorted(unexpected)} "
            "— the deny-by-default boundary regressed"
        )


def test_an_undeclared_ambient_variable_is_not_forwarded(
    ambient_credentials, no_secret_store, tmp_path, monkeypatch
):
    """A marker the backend exports but no entry names must not reach a child."""
    monkeypatch.setenv("VIGIL_PARENT_MARKER", "inherited")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "python",
                        "args": ["-m", "tools.demo"],
                        "env": {"CUSTOM_FROM_CONFIG": "yes"},
                    }
                }
            }
        )
    )

    service = MCPService(project_root=tmp_path)

    env = service.servers["demo"].env
    assert "VIGIL_PARENT_MARKER" not in env
    assert "JWT_SECRET_KEY" not in env
    assert env["CUSTOM_FROM_CONFIG"] == "yes"


def test_an_entry_opting_in_receives_the_ambient_variable(
    ambient_credentials, no_secret_store, tmp_path, monkeypatch
):
    """required_env_vars is the explicit channel: the listed name (only) is
    forwarded from the backend's environment."""
    monkeypatch.setenv("VIGIL_PARENT_MARKER", "inherited")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "python",
                        "args": ["-m", "tools.demo"],
                        "required_env_vars": ["VIGIL_PARENT_MARKER"],
                    }
                }
            }
        )
    )

    service = MCPService(project_root=tmp_path)

    env = service.servers["demo"].env
    assert env["VIGIL_PARENT_MARKER"] == "inherited"
    assert "JWT_SECRET_KEY" not in env  # the unlisted neighbors stay out


def test_a_referenced_name_is_forwarded_and_its_declaration_resolves(
    ambient_credentials, no_secret_store, tmp_path, monkeypatch
):
    """A declared value referencing an ambient name resolves through the
    opt-in — not through a wholesale os.environ copy."""
    monkeypatch.setenv("VIGIL_PARENT_MARKER", "ambient-value")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "python",
                        "args": ["-m", "tools.demo"],
                        "env": {"PARENT_MARKER": "${VIGIL_PARENT_MARKER}"},
                    }
                }
            }
        )
    )

    service = MCPService(project_root=tmp_path)

    env = service.servers["demo"].env
    assert env["PARENT_MARKER"] == "ambient-value"
    assert env["VIGIL_PARENT_MARKER"] == "ambient-value"  # the opt-in itself


def test_a_store_stored_opt_in_reaches_the_child(
    ambient_credentials, tmp_path, monkeypatch
):
    """The opt-in resolves through the secret store too — a credential may
    live in secrets.enc instead of an export (mirrors the dormancy gate)."""
    monkeypatch.setenv("VIGIL_PARENT_MARKER", "inherited")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "python",
                        "args": ["-m", "tools.demo"],
                        "required_env_vars": ["STORED_TOKEN_XYZ"],
                    }
                }
            }
        )
    )
    store_values = {"STORED_TOKEN_XYZ": "stored-token-canary"}

    with patch(
        "core.integrations.mcp.service.get_secret",
        side_effect=lambda key, default=None: store_values.get(key, default),
    ):
        service = MCPService(project_root=tmp_path)

    env = service.servers["demo"].env
    assert env["STORED_TOKEN_XYZ"] == "stored-token-canary"
    assert "JWT_SECRET_KEY" not in env


def test_the_base_names_survive_so_servers_can_find_their_binaries(
    ambient_credentials, no_secret_store, tmp_path
):
    """Deny-by-default must not strip the SDK's safe names: PATH and friends
    are how npx/uvx/python resolve at spawn time."""
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {"command": "python", "args": ["-m", "tools.demo"]}
                }
            }
        )
    )

    service = MCPService(project_root=tmp_path)

    env = service.servers["demo"].env
    assert "PATH" in env
    assert env["VIGIL_DIR"]
    assert env["PYTHONPATH"] == str(tmp_path)

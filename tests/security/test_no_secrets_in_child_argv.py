"""No resolved secret may appear in a spawned MCP server's argv (E3).

The LogLM entry used to substitute its bearer token straight into the child's
command line — ``--header Authorization: Bearer <token>`` — where every other
process on the host could read it from ``/proc/<pid>/cmdline``. Since every MCP
child is a same-UID process, that meant every community npx/uvx package could
harvest every integration token.

The contract now: argv substitution is *public* — it resolves values the
entry's own env block declared, and never consults the secret store. The
LogLM token reaches the child through its environment (mcp-remote 0.1.49
expands ``${VAR}`` in header values from the child env), so the placeholder
stays literal in argv and the resolved value never appears there.

Ratchet style: the shipped-config sweep fails on any resolved credential value
showing up in any server's computed argv, present or future. If you change the
mechanism (e.g. an in-process streamable-HTTP client replaces mcp-remote),
update ``test_the_loglm_bearer_token_stays_a_literal_placeholder`` in the same
commit — it pins the shipped mechanism; the sweep pins the property.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.integrations.mcp import service as mcp_service  # noqa: E402
from core.integrations.mcp.service import MCPService  # noqa: E402

pytestmark = pytest.mark.unit

# Ambient credential-shaped names no shipped entry references. Their values
# must never appear in any child's argv.
AMBIENT_CREDENTIALS = {
    "JWT_SECRET_KEY": "jwt-signing-secret-canary",
    "AGENT_INTERNAL_TOKEN": "agent-internal-token-canary",
    "POSTGRES_PASSWORD": "postgres-password-canary",
    "ANTHROPIC_API_KEY": "anthropic-api-key-canary",
    "STRIPE_SECRET_KEY": "stripe-secret-key-canary",
}

# Store-only credentials. The LogLM token is the E3 case: the store holds it,
# the child's env receives it, argv must not.
STORE_CREDENTIALS = {
    "LOGLM_MCP_TOKEN": "loglm-store-bearer-canary",
    "SPLUNK_HEC_TOKEN_XYZ": "splunk-store-token-canary",
}


@pytest.fixture
def planted_environment(monkeypatch):
    """Plant credentials in the ambient environment and the secret store."""
    for key, value in AMBIENT_CREDENTIALS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        mcp_service,
        "get_secret",
        lambda key, default=None: STORE_CREDENTIALS.get(key, default),
    )
    yield


def _all_server_args(service: MCPService):
    for name, server in service.servers.items():
        for arg in server.args:
            yield name, arg


def test_no_resolved_credential_value_appears_in_any_shipped_argv(
    planted_environment,
):
    """Sweep every shipped server's computed argv for planted credential
    values — ambient or store-resolved. The loader resolves argv through the
    public substitution only, so a value from either source is a regression."""
    service = MCPService(project_root=REPO)

    canaries = {
        **AMBIENT_CREDENTIALS,
        **STORE_CREDENTIALS,
    }
    for name, arg in _all_server_args(service):
        for secret_name, canary in canaries.items():
            assert canary not in arg, (
                f"{name}: resolved {secret_name} appears in child argv — "
                "resolved secrets must reach the child env, never the "
                "command line"
            )


def test_the_loglm_bearer_token_stays_a_literal_placeholder(
    planted_environment,
):
    """The E3 regression pin: the LogLM header keeps its ``${VAR}`` placeholder
    in argv (mcp-remote expands it from the child env at runtime) while the
    resolved token reaches the child's environment."""
    service = MCPService(project_root=REPO)

    loglm = service.servers["loglm"]
    assert any(
        "${LOGLM_MCP_TOKEN}" in arg for arg in loglm.args
    ), "the LogLM bearer placeholder was resolved into argv — E3 regressed"
    assert loglm.env.get("LOGLM_MCP_TOKEN") == STORE_CREDENTIALS["LOGLM_MCP_TOKEN"], (
        "the LogLM token must reach the child environment, where mcp-remote "
        "expands it into the header"
    )


def test_public_substitution_never_consults_the_secret_store(tmp_path, monkeypatch):
    """``_substitute_public_value`` is the argv channel: a name that only
    resolves in the secret store must stay literal."""
    monkeypatch.setattr(
        mcp_service,
        "get_secret",
        lambda key, default=None: STORE_CREDENTIALS.get(key, default),
    )
    (tmp_path / "mcp-config.json").write_text(
        json.dumps({"mcpServers": {"demo": {"command": "python", "args": ["x"]}}})
    )
    fresh = MCPService(project_root=tmp_path)

    assert (
        fresh._substitute_public_value("${LOGLM_MCP_TOKEN}", {}) == "${LOGLM_MCP_TOKEN}"
    )
    assert (
        fresh._substitute_public_value("Bearer ${LOGLM_MCP_TOKEN}", {})
        == "Bearer ${LOGLM_MCP_TOKEN}"
    )


def test_declared_values_still_expand_in_argv(tmp_path, monkeypatch):
    """The sanctioned channel: a value the entry declares in its own env block
    expands into argv (the okta Docker ``-e`` pattern depends on it)."""
    monkeypatch.setattr(mcp_service, "get_secret", lambda key, default=None: default)
    (tmp_path / "mcp-config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "docker",
                        "args": [
                            "run",
                            "--rm",
                            "-e",
                            "OKTA_URL=${OKTA_ORG_URL}",
                            "okta-mcp:latest",
                        ],
                        "env": {"OKTA_ORG_URL": "https://example.okta.com"},
                    }
                }
            }
        )
    )

    service = MCPService(project_root=tmp_path)

    assert service.servers["demo"].args == [
        "run",
        "--rm",
        "-e",
        "OKTA_URL=https://example.okta.com",
        "okta-mcp:latest",
    ]

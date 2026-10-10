"""Branch tests for ``scripts/headless_onboard.py``.

The script is the console-free path from an empty instance to a working MCP
credential (spec D2). Each test scripts the HTTP responses per branch and
asserts the contract: every step checks before it acts, a 403 on the
bootstrap create continues to login, wrong credentials and MFA-gated accounts
fail with actionable guidance and a documented exit code, and the token
reaches stdout exactly once in human mode -- never the filesystem.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.unit


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "vigil_headless_onboard", REPO / "scripts" / "headless_onboard.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolves its fields through sys.modules, which an ad-hoc
    # module load does not populate -- register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


class FakeTransport:
    """Pops one scripted response per call and records every call made."""

    def __init__(self, *script: Any) -> None:
        self.script: List[Any] = list(script)
        self.calls: List[Dict[str, Any]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        json_body: Dict[str, Any] | None = None,
        timeout: float | None = None,
    ):
        self.calls.append(
            {"method": method, "url": url, "token": token, "json_body": json_body}
        )
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def response(mod, status: int, body: Any = None, headers: Dict[str, str] | None = None):
    return mod.ApiResponse(status=status, headers=headers or {}, body=body)


def _login_chain(mod, *, surface_enabled: bool = True):
    """Responses for an already-bootstrapped instance: login -> mint."""
    chain = [
        response(mod, 200, {"required": False}),
        response(mod, 200, {"access_token": "jwt-1", "refresh_token": "r", "user": {}}),
        response(
            mod,
            200,
            {"enabled": surface_enabled, "path": "/mcp", "credentials": []},
        ),
    ]
    if not surface_enabled:
        chain.append(response(mod, 200, {"enabled": True}))
    chain.append(
        response(
            mod,
            201,
            {"token": "vgl_mcp_x", "credential": {"credential_id": "mcpc-x"}},
        )
    )
    return chain


def _onboard(mod, transport, **overrides):
    kwargs: Dict[str, Any] = {
        "username": "vigil-admin",
        "email": "admin@example.test",
        "password": "correct-horse-battery-staple",
        "label": "headless-ci",
        "transport": transport,
    }
    kwargs.update(overrides)
    return mod.onboard("http://127.0.0.1:6987", **kwargs)


def test_fresh_instance_bootstraps_enables_and_mints(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": True}),
        response(mod, 201, {"username": "vigil-admin", "user_id": "u1"}),
        response(mod, 200, {"access_token": "jwt-1", "refresh_token": "r", "user": {}}),
        response(mod, 200, {"enabled": False, "path": "/mcp", "credentials": []}),
        response(mod, 200, {"enabled": True}),
        response(
            mod,
            201,
            {"token": "vgl_mcp_abc", "credential": {"credential_id": "mcpc-1"}},
        ),
    )

    result = _onboard(mod, transport)

    assert result["bootstrapped"] is True
    assert result["surface_enabled"] is True
    assert result["mcp_token"] == "vgl_mcp_abc"
    assert result["credential_id"] == "mcpc-1"
    server = result["client_config"]["mcpServers"]["vigil"]
    assert server["url"] == "http://127.0.0.1:6987/mcp"
    assert server["headers"]["Authorization"] == "Bearer vgl_mcp_abc"

    methods = [(call["method"], call["url"]) for call in transport.calls]
    assert methods == [
        ("GET", "http://127.0.0.1:6987/api/auth/bootstrap"),
        ("POST", "http://127.0.0.1:6987/api/auth/bootstrap"),
        ("POST", "http://127.0.0.1:6987/api/auth/login"),
        ("GET", "http://127.0.0.1:6987/api/mcp/surface"),
        ("PUT", "http://127.0.0.1:6987/api/mcp/surface"),
        ("POST", "http://127.0.0.1:6987/api/mcp/surface/credentials"),
    ]
    # The bootstrap create carried the identity; login used username_or_email;
    # every call after login bore its bearer token.
    assert transport.calls[1]["json_body"]["username"] == "vigil-admin"
    assert transport.calls[1]["json_body"]["email"] == "admin@example.test"
    assert transport.calls[2]["json_body"]["username_or_email"] == "vigil-admin"
    assert transport.calls[3]["token"] == "jwt-1"
    assert transport.calls[4]["token"] == "jwt-1"
    assert transport.calls[4]["json_body"] == {"enabled": True}
    assert transport.calls[5]["json_body"] == {"label": "headless-ci"}


def test_already_bootstrapped_instance_skips_bootstrap_and_enable(mod):
    transport = FakeTransport(*_login_chain(mod, surface_enabled=True))

    result = _onboard(mod, transport)

    assert result["bootstrapped"] is False
    assert result["surface_enabled"] is False
    assert result["mcp_token"] == "vgl_mcp_x"
    methods = [(call["method"], call["url"]) for call in transport.calls]
    assert ("POST", "http://127.0.0.1:6987/api/auth/bootstrap") not in methods
    assert all(call["method"] != "PUT" for call in transport.calls)
    assert len(transport.calls) == 4


def test_bootstrap_race_403_continues_to_login(mod):
    """A 403 from the create is the closed-forever endpoint, never an error."""
    transport = FakeTransport(
        response(mod, 200, {"required": True}),
        response(
            mod,
            403,
            {
                "detail": "An account already exists. Ask an administrator to create yours."
            },
        ),
        response(mod, 200, {"access_token": "jwt-3", "refresh_token": "r", "user": {}}),
        response(mod, 200, {"enabled": True, "path": "/mcp", "credentials": []}),
        response(
            mod,
            201,
            {"token": "vgl_mcp_789", "credential": {"credential_id": "mcpc-3"}},
        ),
    )

    result = _onboard(mod, transport)

    assert result["bootstrapped"] is False
    assert result["mcp_token"] == "vgl_mcp_789"


def test_wrong_password_fails_with_exit_code_2(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": False}),
        response(mod, 401, {"detail": "Invalid username/email or password"}),
    )

    with pytest.raises(mod.AuthError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 2
    assert "password" in excinfo.value.message.lower()
    assert "vigil-admin" in excinfo.value.message
    # Nothing past the failed login may run.
    assert len(transport.calls) == 2


def test_mfa_account_fails_with_explicit_guidance(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": False}),
        response(
            mod,
            401,
            {"detail": "MFA code required"},
            headers={"X-MFA-Required": "true"},
        ),
    )

    with pytest.raises(mod.MfaRequiredError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 3
    message = excinfo.value.message.lower()
    assert "mfa" in message
    assert "without mfa" in message
    assert "pre-minted" in message


def test_locked_account_maps_to_exit_4_with_retry_after(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": False}),
        response(
            mod,
            423,
            {"detail": "Account locked due to repeated failed login attempts"},
            headers={"Retry-After": "90"},
        ),
    )

    with pytest.raises(mod.AccountLockedError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 4
    assert "90" in excinfo.value.message


def test_rate_limited_login_maps_to_exit_5(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": False}),
        response(mod, 429, {"detail": "Rate limit exceeded"}),
    )

    with pytest.raises(mod.RateLimitedError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 5
    assert "rate limited" in excinfo.value.message.lower()


def test_weak_password_rejected_at_bootstrap_is_config_error(mod):
    transport = FakeTransport(
        response(mod, 200, {"required": True}),
        response(mod, 400, {"detail": "Password must be at least 12 characters."}),
    )

    with pytest.raises(mod.ConfigError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 1
    assert "12 characters" in excinfo.value.message


def test_missing_identity_is_config_error_before_any_call(mod):
    transport = FakeTransport()

    with pytest.raises(mod.ConfigError) as excinfo:
        _onboard(mod, transport, username=None, email=None, password=None)

    assert excinfo.value.exit_code == 1
    assert transport.calls == []


def test_bootstrap_required_but_email_missing_is_config_error(mod):
    transport = FakeTransport(response(mod, 200, {"required": True}))

    with pytest.raises(mod.ConfigError) as excinfo:
        _onboard(mod, transport, email=None)

    assert excinfo.value.exit_code == 1
    # Only the check ran; the create was never attempted without an email.
    assert [call["method"] for call in transport.calls] == ["GET"]


def test_unreachable_api_maps_to_exit_6(mod):
    transport = FakeTransport(mod.ApiUnreachableError("no route to host"))

    with pytest.raises(mod.ApiUnreachableError) as excinfo:
        _onboard(mod, transport)

    assert excinfo.value.exit_code == 6


def test_context_path_is_honored_in_api_urls_and_client_config(mod):
    transport = FakeTransport(*_login_chain(mod))

    result = _onboard(mod, transport, context_path="/vigil")

    assert all(
        call["url"].startswith("http://127.0.0.1:6987/vigil/api/")
        for call in transport.calls
    )
    assert (
        result["client_config"]["mcpServers"]["vigil"]["url"]
        == "http://127.0.0.1:6987/vigil/mcp"
    )


def test_expires_in_days_is_passed_to_the_mint(mod):
    transport = FakeTransport(*_login_chain(mod))

    _onboard(mod, transport, expires_in_days=30)

    assert transport.calls[-1]["json_body"] == {
        "label": "headless-ci",
        "expires_in_days": 30,
    }


# --- CLI ---------------------------------------------------------------------


class _FakeSession:
    """Minimal requests.Session double: records requests, holds a cookie jar."""

    def __init__(self, cookies: Dict[str, str] | None = None) -> None:
        self.headers: Dict[str, str] = {}
        self.cookies: Dict[str, str] = cookies or {}
        self.sent: List[Dict[str, Any]] = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.sent.append(
            {"method": method, "url": url, "headers": headers, "json": json}
        )
        return SimpleNamespace(
            status_code=204, headers={}, content=b"", json=lambda: None
        )


def test_requests_transport_echoes_the_csrf_cookie(mod, monkeypatch):
    """CSRF is a double-submit check: jar cookie and matching header go together."""
    session = _FakeSession(cookies={mod.CSRF_COOKIE: "tok-123"})
    monkeypatch.setattr(mod, "_session", session)

    result = mod.requests_transport(
        "POST",
        "http://x/api/auth/login",
        token="jwt-9",
        json_body={"username_or_email": "a", "password": "b"},
    )

    assert result.status == 204
    assert session.sent[0]["headers"]["Authorization"] == "Bearer jwt-9"
    assert session.headers[mod.CSRF_HEADER] == "tok-123"


def test_requests_transport_without_csrf_cookie_sets_no_header(mod, monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(mod, "_session", session)

    mod.requests_transport("GET", "http://x/api/auth/bootstrap")

    assert mod.CSRF_HEADER not in session.headers


def _cli_argv(*extra: str) -> list[str]:
    return [
        "--base-url",
        "http://127.0.0.1:6987",
        "--label",
        "headless-ci",
        "--username",
        "vigil-admin",
        "--email",
        "admin@example.test",
        "--password",
        "correct-horse-battery-staple",
        *extra,
    ]


def test_cli_json_mode_prints_exactly_one_object(mod, capsys):
    transport = FakeTransport(*_login_chain(mod))

    rc = mod.main(_cli_argv("--json"), transport=transport)

    assert rc == 0
    captured = capsys.readouterr()
    # json.loads on the whole stdout: one object, and nothing else on it.
    parsed = json.loads(captured.out)
    assert parsed["bootstrapped"] is False
    assert parsed["surface_enabled"] is False
    assert parsed["mcp_token"].startswith("vgl_mcp_")
    assert parsed["client_config"]["mcpServers"]["vigil"]["headers"][
        "Authorization"
    ].endswith(parsed["mcp_token"])


def test_cli_human_mode_prints_the_token_exactly_once(mod, capsys):
    transport = FakeTransport(*_login_chain(mod))

    rc = mod.main(_cli_argv(), transport=transport)

    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.count("vgl_mcp_") == 1
    # stdout is still a single pasteable JSON block; progress goes to stderr.
    assert json.loads(captured.out)["mcpServers"]["vigil"]["url"].endswith("/mcp")
    assert "credential: minted" in captured.err


def test_cli_wrong_credentials_exit_2_with_stderr_guidance(mod, capsys):
    transport = FakeTransport(
        response(mod, 200, {"required": False}),
        response(mod, 401, {"detail": "Invalid username/email or password"}),
    )

    rc = mod.main(_cli_argv("--json"), transport=transport)

    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "password" in captured.err.lower()


def test_cli_unreachable_api_exits_6(mod, capsys):
    transport = FakeTransport(mod.ApiUnreachableError("connection refused"))

    rc = mod.main(_cli_argv("--json"), transport=transport)

    assert rc == 6
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "connection refused" in captured.err


def test_cli_identity_falls_back_to_env_vars(mod, monkeypatch, capsys):
    transport = FakeTransport(*_login_chain(mod))
    monkeypatch.setenv("VIGIL_BOOTSTRAP_ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("VIGIL_BOOTSTRAP_ADMIN_EMAIL", "env@example.test")
    monkeypatch.setenv("VIGIL_BOOTSTRAP_ADMIN_PASSWORD", "env-password-12plus")

    rc = mod.main(["--json"], transport=transport)

    assert rc == 0
    login_calls = [
        call for call in transport.calls if call["url"].endswith("/api/auth/login")
    ]
    assert login_calls[0]["json_body"]["username_or_email"] == "env-admin"
    assert login_calls[0]["json_body"]["password"] == "env-password-12plus"


def test_cli_usage_error_exits_1(mod, capsys):
    with pytest.raises(SystemExit) as excinfo:
        mod.main(["--expires-in-days", "not-a-number"])

    assert excinfo.value.code == 1
    assert "error:" in capsys.readouterr().err

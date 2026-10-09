#!/usr/bin/env python3
"""Take an empty Vigil instance to a working MCP credential, without a browser.

The console-free counterpart of Settings -> MCP: one idempotent,
non-interactive command chains the four HTTP calls the REST API already
serves --

    1. GET  /api/auth/bootstrap   does the instance still need its first account?
       POST /api/auth/bootstrap   create it (skipped when one already exists)
    2. POST /api/auth/login       -> bearer token in the response body
    3. GET  /api/mcp/surface      is Vigil's own MCP surface listening?
       PUT  /api/mcp/surface      open it (skipped when already open)
    4. POST /api/mcp/surface/credentials   mint a ``vgl_mcp_`` credential

Every step checks before it acts, so re-running is safe: an already-logged-in
instance skips straight to step 2, and the last step mints an additional
revocable credential rather than failing. A 403 from the bootstrap create --
the endpoint closes forever once one user exists -- is a race we can only lose
cleanly: continue to login, never error.

The token is printed once, embedded in a ready-to-paste MCP client config,
and never written to disk by this script. The credential is actor-scoped;
revoke it from the console or ``DELETE /api/mcp/surface/credentials/{id}``.

Identity comes from --username/--email/--password or the
VIGIL_BOOTSTRAP_ADMIN_USERNAME / VIGIL_BOOTSTRAP_ADMIN_EMAIL /
VIGIL_BOOTSTRAP_ADMIN_PASSWORD environment variables. Prefer the env vars: a
password on argv is visible in ``ps``. An MFA-enabled account is refused on
purpose -- headless automation cannot answer an MFA prompt; use a dedicated
admin without MFA, or a credential minted in advance.

Usage::

    VIGIL_BOOTSTRAP_ADMIN_PASSWORD='...' python scripts/headless_onboard.py \
        --base-url http://127.0.0.1:6987 --label headless-ci --json

Exit codes: 0 success; 1 configuration (missing identity, weak password);
2 authentication failed; 3 MFA required; 4 account locked; 5 rate limited;
6 API unreachable; 7 unexpected API response.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:6987"
DEFAULT_LABEL = "headless"
DEFAULT_TIMEOUT = 30.0
# Where Vigil mounts its own MCP surface when the API reports no other path.
DEFAULT_MCP_PATH = "/mcp"

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_AUTH = 2
EXIT_MFA = 3
EXIT_LOCKED = 4
EXIT_RATE = 5
EXIT_UNREACHABLE = 6
EXIT_API = 7


class OnboardError(Exception):
    """A failure with an operator-facing message and a documented exit code."""

    exit_code = EXIT_API

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(OnboardError):
    exit_code = EXIT_CONFIG


class AuthError(OnboardError):
    exit_code = EXIT_AUTH


class MfaRequiredError(OnboardError):
    exit_code = EXIT_MFA


class AccountLockedError(OnboardError):
    exit_code = EXIT_LOCKED


class RateLimitedError(OnboardError):
    exit_code = EXIT_RATE


class ApiUnreachableError(OnboardError):
    exit_code = EXIT_UNREACHABLE


class ApiError(OnboardError):
    exit_code = EXIT_API


@dataclass
class ApiResponse:
    """The transport-independent slice of an HTTP response the chain reads."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any = None


# (method, url, *, token, json_body, timeout) -> ApiResponse. The seam every
# step talks through; tests inject a scripted fake instead of requests.
Transport = Callable[..., ApiResponse]


# The API's CSRF middleware is a double-submit check: an unsafe call must echo
# the csrf_token cookie back in X-CSRF-Token (services/api/middleware/csrf.py).
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# One session per process: the chain runs once, and the cookie jar it keeps is
# what lets a cookieless CLI pass the CSRF check the browser client passes.
_session: Optional["requests.Session"] = None


def requests_transport(
    method: str,
    url: str,
    *,
    token: Optional[str] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ApiResponse:
    """The real transport: a cookie-keeping session, bearer-authed when given.

    The first response seeds the csrf_token cookie; from then on every unsafe
    call carries cookie and matching header together -- what the console's JS
    client does, done here for a headless one.
    """
    global _session
    if _session is None:
        _session = requests.Session()
    headers: Dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = _session.request(
            method, url, headers=headers, json=json_body, timeout=timeout
        )
    except requests.RequestException as exc:
        raise ApiUnreachableError(f"could not reach {url}: {exc}") from exc
    csrf = _session.cookies.get(CSRF_COOKIE)
    if csrf:
        _session.headers[CSRF_HEADER] = csrf
    try:
        body: Any = response.json() if response.content else None
    except ValueError:
        body = None
    return ApiResponse(status=response.status_code, headers=response.headers, body=body)


def _api_root(base_url: str, context_path: str) -> str:
    base = base_url.rstrip("/")
    trimmed = context_path.strip("/")
    return f"{base}/{trimmed}" if trimmed else base


def _detail(response: ApiResponse) -> str:
    """The API's error detail when it has one, else something honest."""
    body = response.body
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])
    if body:
        return json.dumps(body)[:200]
    return f"HTTP {response.status} with no body"


def _ensure_bootstrap(
    root: str,
    *,
    username: Optional[str],
    email: Optional[str],
    password: str,
    full_name: Optional[str],
    transport: Transport,
    timeout: float,
) -> bool:
    """Create the first admin when the instance needs one.

    Returns whether this run created it. A 403 from the create means the
    instance gained its first account between the check and the create --
    continue to login rather than fail, since the credentials must now match
    that existing account anyway.
    """
    status = transport("GET", f"{root}/api/auth/bootstrap", timeout=timeout)
    if status.status != 200:
        raise ApiError(f"bootstrap check failed: {_detail(status)}")
    if not (status.body or {}).get("required"):
        return False

    if not username or not email:
        raise ConfigError(
            "this instance needs its first account: pass --username and "
            "--email (plus the password) to bootstrap it"
        )

    payload: Dict[str, Any] = {
        "username": username,
        "email": email,
        "password": password,
    }
    if full_name:
        payload["full_name"] = full_name
    resp = transport(
        "POST", f"{root}/api/auth/bootstrap", json_body=payload, timeout=timeout
    )
    if resp.status in (200, 201):
        return True
    if resp.status == 403:
        return False
    if resp.status == 400:
        raise ConfigError(f"bootstrap rejected the admin identity: {_detail(resp)}")
    if resp.status == 409:
        raise ApiError("bootstrap raced another attempt; re-run this script")
    raise ApiError(f"bootstrap failed: {_detail(resp)}")


def _login(
    root: str,
    *,
    identity: str,
    password: str,
    transport: Transport,
    timeout: float,
) -> str:
    """Authenticate and return the access token from the response body."""
    resp = transport(
        "POST",
        f"{root}/api/auth/login",
        json_body={"username_or_email": identity, "password": password},
        timeout=timeout,
    )
    if resp.status == 200:
        token = (resp.body or {}).get("access_token")
        if not token:
            raise ApiError("login response carried no access_token")
        return str(token)
    if resp.status == 401:
        if str(resp.headers.get("X-MFA-Required", "")).lower() == "true":
            raise MfaRequiredError(
                f"the account {identity!r} has MFA enabled, which headless "
                "automation cannot answer. Use a dedicated admin account "
                "without MFA, or configure the client with a pre-minted "
                "credential."
            )
        raise AuthError(
            "login failed: invalid username/email or password "
            f"(identity {identity!r})"
        )
    if resp.status == 423:
        retry_after = resp.headers.get("Retry-After", "")
        wait = f"; retry in ~{retry_after}s" if retry_after else ""
        raise AccountLockedError(
            "the account is locked after repeated failed logins" + wait
        )
    if resp.status == 429:
        raise RateLimitedError(
            "login is rate limited (5/minute); wait a minute and re-run"
        )
    raise ApiError(f"login failed: {_detail(resp)}")


def _ensure_surface(
    root: str, *, token: str, transport: Transport, timeout: float
) -> Tuple[bool, str]:
    """Open the surface when it is closed; never touch it when already open.

    Returns (enabled_by_this_run, the surface's mount path).
    """
    resp = transport("GET", f"{root}/api/mcp/surface", token=token, timeout=timeout)
    if resp.status == 403:
        raise ApiError(
            "the MCP surface settings need an account with the integrations "
            "write permission"
        )
    if resp.status != 200:
        raise ApiError(f"could not read the MCP surface state: {_detail(resp)}")
    body = resp.body or {}
    mcp_path = str(body.get("path") or DEFAULT_MCP_PATH)
    if body.get("enabled"):
        return False, mcp_path
    put = transport(
        "PUT",
        f"{root}/api/mcp/surface",
        token=token,
        json_body={"enabled": True},
        timeout=timeout,
    )
    if put.status != 200:
        raise ApiError(f"could not enable the MCP surface: {_detail(put)}")
    return True, mcp_path


def _mint(
    root: str,
    *,
    token: str,
    label: str,
    expires_in_days: Optional[int],
    transport: Transport,
    timeout: float,
) -> Dict[str, Any]:
    """Mint one credential. Re-runs mint an additional revocable credential."""
    payload: Dict[str, Any] = {"label": label}
    if expires_in_days:
        payload["expires_in_days"] = expires_in_days
    resp = transport(
        "POST",
        f"{root}/api/mcp/surface/credentials",
        token=token,
        json_body=payload,
        timeout=timeout,
    )
    if resp.status not in (200, 201):
        raise ApiError(f"credential mint failed: {_detail(resp)}")
    body = resp.body or {}
    minted = body.get("token")
    if not minted:
        raise ApiError("credential mint response carried no token")
    credential = body.get("credential") or {}
    return {"token": str(minted), "credential_id": credential.get("credential_id")}


def client_config(
    base_url: str, context_path: str, mcp_path: str, token: str
) -> Dict[str, Any]:
    """A ready-to-paste streamable-HTTP MCP client entry."""
    return {
        "mcpServers": {
            "vigil": {
                "url": f"{_api_root(base_url, context_path)}{mcp_path}",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    }


def onboard(
    base_url: str,
    *,
    username: Optional[str],
    email: Optional[str],
    password: Optional[str],
    label: str,
    full_name: Optional[str] = None,
    expires_in_days: Optional[int] = None,
    context_path: str = "",
    timeout: float = DEFAULT_TIMEOUT,
    transport: Transport = requests_transport,
) -> Dict[str, Any]:
    """Run the four-step chain; return the result payload.

    ``bootstrapped`` and ``surface_enabled`` are true when this run performed
    the action -- both false on a re-run, which is the idempotency signal. The
    token lives only in the returned dict and whatever the caller prints;
    nothing here touches the filesystem.
    """
    identity = username or email
    if not identity or not password:
        raise ConfigError(
            "no login identity: pass --username/--email/--password or set "
            "VIGIL_BOOTSTRAP_ADMIN_USERNAME / _EMAIL / _PASSWORD"
        )
    root = _api_root(base_url, context_path)

    bootstrapped = _ensure_bootstrap(
        root,
        username=username,
        email=email,
        password=password,
        full_name=full_name,
        transport=transport,
        timeout=timeout,
    )
    access_token = _login(
        root,
        identity=identity,
        password=password,
        transport=transport,
        timeout=timeout,
    )
    enabled_now, mcp_path = _ensure_surface(
        root, token=access_token, transport=transport, timeout=timeout
    )
    minted = _mint(
        root,
        token=access_token,
        label=label,
        expires_in_days=expires_in_days,
        transport=transport,
        timeout=timeout,
    )
    return {
        "bootstrapped": bootstrapped,
        "surface_enabled": enabled_now,
        "mcp_token": minted["token"],
        "credential_id": minted["credential_id"],
        "client_config": client_config(
            base_url, context_path, mcp_path, minted["token"]
        ),
    }


class _ArgumentParser(argparse.ArgumentParser):
    """Exit EXIT_CONFIG on usage errors so every non-zero code is documented."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        raise SystemExit(EXIT_CONFIG)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = _ArgumentParser(
        description="Take an empty Vigil instance to a working MCP credential, "
        "without a browser.",
        epilog="exit codes: 0 ok; 1 configuration; 2 bad credentials; "
        "3 MFA required; 4 account locked; 5 rate limited; 6 unreachable; "
        "7 unexpected API response",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Vigil API root (default: %(default)s)",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help="name for the minted credential (default: %(default)s)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("VIGIL_BOOTSTRAP_ADMIN_USERNAME"),
        help="admin username (env: VIGIL_BOOTSTRAP_ADMIN_USERNAME)",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("VIGIL_BOOTSTRAP_ADMIN_EMAIL"),
        help="admin email, required when bootstrapping (env: "
        "VIGIL_BOOTSTRAP_ADMIN_EMAIL)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("VIGIL_BOOTSTRAP_ADMIN_PASSWORD"),
        help="admin password -- prefer the env var; argv is visible in ps (env: "
        "VIGIL_BOOTSTRAP_ADMIN_PASSWORD)",
    )
    parser.add_argument(
        "--full-name",
        default=os.environ.get("VIGIL_BOOTSTRAP_ADMIN_FULL_NAME"),
        help="display name for the bootstrapped account",
    )
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="credential lifetime in days (default: no expiry)",
    )
    parser.add_argument(
        "--context-path",
        default=os.environ.get("VIGIL_CONTEXT_PATH", ""),
        help="reverse-proxy context path the API is mounted under (env: "
        "VIGIL_CONTEXT_PATH)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="per-request timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one JSON object on stdout, for CI capture",
    )
    return parser.parse_args(argv)


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport: Transport = requests_transport,
) -> int:
    args = parse_args(argv)
    try:
        result = onboard(
            args.base_url,
            username=args.username,
            email=args.email,
            password=args.password,
            label=args.label,
            full_name=args.full_name,
            expires_in_days=args.expires_in_days,
            context_path=args.context_path,
            timeout=args.timeout,
            transport=transport,
        )
    except OnboardError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code

    if args.json:
        # One object, once -- the CI capture. Everything else stays on stderr.
        print(json.dumps(result, indent=2))
        return EXIT_OK

    steps = [
        "bootstrap: "
        + (
            "created the first admin"
            if result["bootstrapped"]
            else "account already existed"
        ),
        "login: ok",
        "MCP surface: "
        + ("enabled" if result["surface_enabled"] else "already enabled"),
        "credential: minted -- shown once below, never stored",
    ]
    for line in steps:
        print(line, file=sys.stderr)
    # The token appears exactly once: inside the pasteable config block.
    print(json.dumps(result["client_config"], indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

"""CA-bundle trust for spawned MCP servers.

The tool servers run on httpx, which reads ``SSL_CERT_FILE`` / ``SSL_CERT_DIR``
and ignores ``REQUESTS_CA_BUNDLE`` / ``CURL_CA_BUNDLE`` — the names an operator
would have used to trust an internal CA while the servers ran on requests. An
on-prem MISP, PAN-OS or CAPE behind a private or inspecting CA would start
failing verification on nothing but a library swap, so the legacy names are
honored as aliases. A resolved *file* path is also exported as
``NODE_EXTRA_CA_CERTS`` so npx servers pick up the same bundle; Node has no
directory equivalent, so a capath is left as ``SSL_CERT_DIR`` only.

Forwarding also has to be explicit rather than inherited: ``stdio_client``
narrows the child environment to ``HOME``, ``LOGNAME``, ``PATH``, ``SHELL``,
``TERM``, ``USER`` plus the server's own ``env`` block, so a bundle set in the
backend's environment never reaches a server spawned that way.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# The SDK's DEFAULT_INHERITED_ENV_VARS, mirrored for the (supported) case where
# the mcp package is not installed. When the SDK is present it is authoritative:
# stdio_client re-applies get_default_environment() at spawn time regardless of
# what we pass, so the names must not drift from what it narrows to.
_SDK_POSIX_DEFAULTS = ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
_SDK_WINDOWS_DEFAULTS = (
    "APPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "USERNAME",
    "USERPROFILE",
)

_sdk_default_environment: Optional[Callable[[], Dict[str, str]]]
try:
    from mcp.client.stdio import get_default_environment as _sdk_default_environment
except ImportError:  # pragma: no cover - only when the mcp package is absent
    _sdk_default_environment = None

# Highest precedence first. The httpx-native names win, so an operator who has
# already moved on is never overridden by a stale requests-era value.
_BUNDLE_VARS = (
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


def default_child_env() -> Dict[str, str]:
    """The environment names a spawned MCP server may inherit unprompted.

    The SDK's safe-to-inherit set (``HOME``/``PATH``/... — never credentials)
    plus the CA bundle. This is the *base* of a child's environment: everything
    else must arrive through the server's own declared config env or an
    explicit ``required_env_vars`` opt-in, never through ``os.environ``
    wholesale.
    """
    if _sdk_default_environment is not None:
        env = _sdk_default_environment()
    else:  # pragma: no cover - only when the mcp package is absent
        names = (
            _SDK_WINDOWS_DEFAULTS if sys.platform == "win32" else _SDK_POSIX_DEFAULTS
        )
        env = {
            key: os.environ[key]  # noqa: ENV001 - child env boundary
            for key in names
            if os.environ.get(key)  # noqa: ENV001 - child env boundary
        }
    return {**env, **ca_bundle_env()}


def ca_bundle_env() -> Dict[str, str]:
    """The CA-bundle entries to merge into a spawned MCP server's environment.

    Empty when no bundle is configured, which leaves httpx on certifi.
    """
    for var in _BUNDLE_VARS:
        value = os.environ.get(var)  # noqa: ENV001 - MCP child process env
        if not value:
            continue
        if not os.path.exists(value):
            logger.warning(
                "%s points at %s, which does not exist — MCP tool servers will "
                "fall back to the certifi bundle",
                var,
                value,
            )
            return {}
        # httpx checks SSL_CERT_FILE before SSL_CERT_DIR, and cafile vs capath
        # are not interchangeable, so route by what the path actually is.
        if os.path.isdir(value):
            return {"SSL_CERT_DIR": value}
        return {"SSL_CERT_FILE": value, "NODE_EXTRA_CA_CERTS": value}
    return {}

"""Fixture builders for the warden tests.

Warden consumes the edge test fixtures' key material the same way the
control-plane tests do — every test builds its own keypairs and trust root
in-process, so no secret material ships in the repo. The clock is a
``FakeClock``: mode-machine deadlines (grace window, pack expiry) are
stepped explicitly, never slept.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
from datetime import datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.unit.edge.helpers import NOW as EDGE_NOW
from tests.unit.edge.helpers import default_root, policy_doc, sign_policy

WARDEN_NOW = EDGE_NOW


class FakeClock:
    """A controllable clock for expiry and grace-window tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or WARDEN_NOW

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs: Any) -> None:
        self._now += timedelta(**kwargs)


def make_policy_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def make_root(policy_key: Ed25519PrivateKey) -> dict:
    """A baked-in trust root whose ``policies`` role trusts ``policy_key``."""
    return default_root(policy_keys=[policy_key])


def make_pack_bytes(policy_key: Ed25519PrivateKey, **overrides: Any) -> bytes:
    """A pack that verifies against ``make_root([policy_key])``."""
    return sign_policy(policy_doc(**overrides), [policy_key])


def policy_response_doc(pack_bytes: bytes) -> dict[str, Any]:
    """The GET /api/v1/edge/policy body for a signed pack.

    Mirrors the control plane's response: the verified payload hash it
    records is sha256 over the decoded payload bytes (``policy_fingerprint``).
    """
    envelope = json.loads(pack_bytes)
    payload = base64.b64decode(envelope["payload"])
    doc = json.loads(payload)
    return {
        "policy_version": doc["policy_version"],
        "envelope": envelope,
        "payload_hash": hashlib.sha256(payload).hexdigest(),
        "not_before": doc["not_before"],
        "not_after": doc["not_after"],
    }


def free_port() -> int:
    """A TCP port that is free right now (bind, read, release)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def free_ports(count: int) -> tuple[int, ...]:
    """``count`` distinct ports, bound simultaneously so they cannot collide."""
    socks = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(count)]
    try:
        for sock in socks:
            sock.bind(("127.0.0.1", 0))
        return tuple(int(sock.getsockname()[1]) for sock in socks)
    finally:
        for sock in socks:
            sock.close()


__all__ = [
    "FakeClock",
    "WARDEN_NOW",
    "free_port",
    "free_ports",
    "make_pack_bytes",
    "make_policy_key",
    "make_root",
    "policy_response_doc",
]

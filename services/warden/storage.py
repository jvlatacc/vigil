"""Warden's local state: credentials and the verified policy, on disk.

Everything Warden persists lives under the 0700 data dir; every file is
0600 and written atomically (tmp file + rename, the Medic heartbeat
pattern). There is deliberately no other state: no database, no Redis —
if the process dies, these files plus the journal are the whole world.

A stored policy is never trusted on reload: it is re-verified against the
baked-in trust root exactly like a fresh fetch (verify-before-trust), so a
tampered disk is a refusal, not an authority. That is why this module
stores the raw response document and does not parse it here.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREDENTIALS_FILE = "credentials.json"
_POLICY_FILE = "policy.json"


class PolicyStore:
    """Credentials and the verified policy document, 0600, atomic."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._ensure_private_dir()

    def _ensure_private_dir(self) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        os.chmod(self._base, 0o700)

    def _write_atomic(self, name: str, payload: bytes) -> None:
        target = self._base / name
        tmp = self._base / f".{name}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp, target)
            os.chmod(target, 0o600)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _read_json(self, name: str) -> dict[str, Any] | None:
        """Return the parsed file, or None when absent or unreadable.

        A corrupt file reads as absent: the caller re-fetches and
        re-verifies from the control plane, which is always safe — nothing
        here is authority, it is a cache of authority.
        """
        path = self._base / name
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.error("warden store: cannot read %s: %s", path, exc)
            return None
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            logger.error("warden store: %s is not valid JSON: %s", path, exc)
            return None
        if not isinstance(doc, dict):
            logger.error("warden store: %s is not a JSON object", path)
            return None
        return doc

    # -- credentials -------------------------------------------------------

    def save_credentials(self, node_id: str, token: str) -> None:
        self._write_atomic(
            _CREDENTIALS_FILE,
            json.dumps(
                {"node_id": node_id, "token": token}, separators=(",", ":")
            ).encode(),
        )

    def load_credentials(self) -> tuple[str, str] | None:
        doc = self._read_json(_CREDENTIALS_FILE)
        if doc is None:
            return None
        node_id = doc.get("node_id")
        token = doc.get("token")
        if not isinstance(node_id, str) or not isinstance(token, str) or not token:
            return None
        return node_id, token

    # -- verified policy -----------------------------------------------------

    def save_policy(self, doc: dict[str, Any]) -> None:
        """Persist the verified policy response for reload and audit."""
        self._write_atomic(_POLICY_FILE, json.dumps(doc, indent=2).encode())

    def load_policy(self) -> dict[str, Any] | None:
        return self._read_json(_POLICY_FILE)

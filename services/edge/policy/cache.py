"""The bundle cache: verify, activate atomically, retain for rollback.

Boot: reload the persisted state, re-verifying both current and previous
bundles against the trust store — a trust-root change or a tampered file
demotes rather than trusts. Sync: every candidate goes through the full
refuse-early verification before it can replace the active bundle; activation
is atomic (tmp file + os.replace, then a state.json pointing at it). The
previous bundle is retained for rollback, but rollback is an explicit human
decision — the cache never auto-rewinds (offline actions are imported and
reported, never silently undone).

An expired current bundle is never extended: effective_tier() falls to Tier 0
while the node keeps observing and journaling.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.edge.gate.tiers import AutonomyTier, tier_label
from services.edge.policy.envelope import TrustRoot, Verification, verify_bundle
from services.edge.policy.model import Bundle

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

_BUNDLES_DIR = "bundles"
_STATE_FILE = "state.json"


@dataclass(frozen=True)
class CacheState:
    current: Bundle | None
    previous: Bundle | None


class BundleCache:
    def __init__(
        self,
        data_dir: Path,
        trust_root: TrustRoot,
        *,
        node_labels: Mapping[str, str],
        edge_version: str,
    ) -> None:
        self.data_dir = data_dir
        self.trust_root = trust_root
        self.node_labels = dict(node_labels)
        self.edge_version = edge_version
        self._current: Bundle | None = None
        self._previous: Bundle | None = None
        self._envelope_path: Path | None = None
        self._previous_envelope_path: Path | None = None

    # -- sync-time API ---------------------------------------------------

    def verify_and_activate(
        self, envelope: Mapping[str, Any], *, now: datetime
    ) -> Verification:
        """Verify a candidate; on success activate atomically and retain the
        previous bundle. Refusals leave the active bundle untouched — the
        caller logs the code and keeps the last-known-good policy."""
        verification = verify_bundle(
            envelope,
            self.trust_root,
            now=now,
            edge_version=self.edge_version,
            node_labels=self.node_labels,
            current=self._current,
        )
        if not verification.accepted or verification.bundle is None:
            logger.warning(
                "bundle refused (%s): %s — keeping last-known-good policy",
                verification.code,
                verification.detail,
            )
            return verification
        bundle = verification.bundle
        path = self._persist_envelope(envelope, bundle)
        previous = self._current
        previous_path = self._envelope_path
        self._current = bundle
        self._envelope_path = path
        self._previous = previous
        self._previous_envelope_path = previous_path
        self._write_state(now=now)
        logger.info(
            "bundle activated: %s v%s (%s), previous v%s retained",
            bundle.bundle_id,
            bundle.version,
            tier_label(bundle.autonomy_tier),
            previous.version if previous else None,
        )
        return verification

    # -- boot-time API ---------------------------------------------------

    def load_persisted(self, *, now: datetime) -> CacheState:
        """Reload persisted bundles at boot, re-verifying each against the
        CURRENT trust store. The newest verified bundle becomes current; if
        the persisted current fails (trust change, tamper), the previous one
        is tried; if both fail, the node runs Tier 0 until a fresh pull."""
        state_path = self.data_dir / _STATE_FILE
        if not state_path.exists():
            return CacheState(current=None, previous=None)
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError) as exc:
            logger.error(
                "cache state unreadable (%s): %s — starting Tier 0", state_path, exc
            )
            return CacheState(current=None, previous=None)

        if state.get("revoked_at") is not None:
            # Revocation beats allowance — including across a restart: a
            # rebooted node must not resurrect its persisted bundle and
            # resume acting. Only a freshly pulled verified bundle
            # (new credential, new state file) restores autonomy.
            logger.error(
                "node revoked at %s — persisted bundles refused, running Tier 0",
                state["revoked_at"],
            )
            return CacheState(current=None, previous=None)

        entries = [
            ("current", state.get("current")),
            ("previous", state.get("previous")),
        ]
        loaded: dict[str, tuple[Bundle, Path]] = {}
        for role, entry in entries:
            if not isinstance(entry, dict):
                continue
            loaded_entry = self._load_and_verify_entry(entry, now=now)
            if loaded_entry is not None:
                loaded[role] = loaded_entry

        current = loaded.get("current") or loaded.get("previous")
        previous_entry = loaded.get("previous")
        if (
            current is not None
            and previous_entry is not None
            and current[0] is not previous_entry[0]
        ):
            self._current, self._envelope_path = current
            self._previous, self._previous_envelope_path = previous_entry
        else:
            self._current, self._envelope_path = current or (None, None)
            self._previous, self._previous_envelope_path = None, None
        return CacheState(current=self._current, previous=self._previous)

    def _load_and_verify_entry(
        self, entry: dict[str, Any], *, now: datetime
    ) -> tuple[Bundle, Path] | None:
        path_value = entry.get("path")
        if not isinstance(path_value, str):
            return None
        path = Path(path_value)
        try:
            envelope = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            logger.error("persisted bundle %s unreadable: %s", path, exc)
            return None
        verification = verify_bundle(
            envelope,
            self.trust_root,
            now=now,
            edge_version=self.edge_version,
            node_labels=self.node_labels,
            current=None,  # each persisted entry verifies standalone at boot
        )
        if not verification.accepted or verification.bundle is None:
            logger.error(
                "persisted bundle %s no longer trustworthy (%s) — refusing it",
                path,
                verification.code,
            )
            return None
        return verification.bundle, path

    # -- query API -------------------------------------------------------

    @property
    def current(self) -> Bundle | None:
        return self._current

    @property
    def previous(self) -> Bundle | None:
        return self._previous

    def effective_tier(self, now: datetime) -> AutonomyTier:
        """No bundle, or an expired one, is Tier 0 — never silently extended."""
        if self._current is None:
            return AutonomyTier.TIER_0
        return self._current.effective_tier(now)

    def revoke(self, *, now: datetime) -> None:
        """Kill the active bundles for a revoked node — now and after any
        restart (the state file marks the revocation). A revoked node's
        credential is dead server-side, so no pull can re-arm it; the only
        path back is fresh enrollment and a new verified bundle."""
        self._current = None
        self._previous = None
        self._envelope_path = None
        self._previous_envelope_path = None
        state_path = self.data_dir / _STATE_FILE
        state = {"revoked_at": now.isoformat()}
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, sort_keys=True))
        os.replace(tmp, state_path)
        logger.warning("node revoked: bundle autonomy withdrawn (Tier 0)")

    # -- persistence -----------------------------------------------------

    def _persist_envelope(self, envelope: Mapping[str, Any], bundle: Bundle) -> Path:
        bundles_dir = self.data_dir / _BUNDLES_DIR
        bundles_dir.mkdir(parents=True, exist_ok=True)
        path = bundles_dir / f"{bundle.bundle_id}.v{bundle.version}.json"
        payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload)
        os.replace(tmp, path)  # atomic on POSIX: a crash never half-writes a bundle
        return path

    def _write_state(self, *, now: datetime) -> None:
        state: dict[str, Any] = {
            "activated_at": now.isoformat(),
            "current": None,
            "previous": None,
        }
        if self._current is not None and self._envelope_path is not None:
            state["current"] = {
                "bundle_id": self._current.bundle_id,
                "version": self._current.version,
                "path": str(self._envelope_path),
            }
        if self._previous is not None and self._previous_envelope_path is not None:
            state["previous"] = {
                "bundle_id": self._previous.bundle_id,
                "version": self._previous.version,
                "path": str(self._previous_envelope_path),
            }
        state_path = self.data_dir / _STATE_FILE
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        os.replace(tmp, state_path)

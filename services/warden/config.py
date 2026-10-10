"""Warden's process configuration.

The edge runtime has no Settings stack — no pydantic-settings, no DB overlay,
no secrets manager. The environment is the config channel, the same way the
enrollment token arrives. Nothing here can widen the signed autonomy envelope:
that lives in the policy pack (core/edge/policy.py), by design — config
configures the process, never the authority.

Every variable Warden reads:

==============================  =====================================================
``WARDEN_CONTROL_PLANE_URL``    Base URL of the control plane (default
                                ``http://127.0.0.1:6987``).
``WARDEN_NODE_ID``              Node identity, minted at enrollment.
``WARDEN_ENROLLMENT_TOKEN``     One-time operator-issued enrollment token.
``WARDEN_SEGMENT_LABELS``       Comma-separated segment labels (e.g. ``dmz,edge``).
``WARDEN_DATA_DIR``             0700 state dir (default ``/var/lib/vigil-warden``).
``WARDEN_TRUST_ROOT_PATH``      Baked-in trust root envelope to verify packs.
``WARDEN_SYNC_INTERVAL_SECONDS``  Policy sync cadence (default 60).
``WARDEN_SYNC_TIMEOUT_SECONDS``   Per-attempt HTTP timeout (default 10).
``WARDEN_MISSED_SYNCS_THRESHOLD`` Consecutive misses that leave SYNCED (default 3).
``WARDEN_GRACE_WINDOW_SECONDS``   DEGRADED dwell time before AUTONOMOUS (default 900).
``WARDEN_SENTINEL_TOKEN``       Local webhook bearer; unset = receiver fail-closed.
``WARDEN_SENTINEL_PORT``        Local alert receiver (default 8091).
``WARDEN_HEALTH_PORT``          Health listener (default 9092).
``WARDEN_METRICS_PORT``         Prometheus listener (default 9093).
``WARDEN_BIND_HOST``            Bind address for all listeners (default loopback).
``WARDEN_MAX_ALERT_QUEUE``      Bounded alert queue depth (default 1000).
``WARDEN_MAX_ALERT_BATCH``      Max alerts per sentinel push (default 100).
``WARDEN_MAX_ALERT_BYTES``      Max body size per push (default 1 MiB).
``WARDEN_SELF_ADDRESSES``       Comma-separated addresses/IPs of this node.
``WARDEN_GATEWAY_ADDRESSES``    Comma-separated gateway IPs/networks.
``WARDEN_CONTROL_PLANE_ADDRESSES``  Comma-separated control-plane IPs/networks.
``WARDEN_DNS_RESOLVERS``        Comma-separated resolver IPs.
``WARDEN_SLM_MODEL_PATH``       Optional GGUF model file for local SLM triage;
                                verified by sha256 against the signed pack's
                                model_manifest before load. Never shipped in
                                the repo or the image.
``WARDEN_LOG_LEVEL``            ``DEBUG|INFO|WARNING|ERROR`` (default ``INFO``).
==============================  =====================================================

The four address groups feed the protected-target guard at enforcement time
(core/edge/target_guard.py). They are node configuration — the operator's own
view of the segment — never alert data; a rule can never nominate a protected
target. This file sits on the no-ambient-state ratchet's ``ENV_EXEMPT_FILES``:
reading the environment is the point of :meth:`WardenConfig.from_env`.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.edge.enrollment import EnrollmentTokenError, validate_node_id

DEFAULT_CONTROL_PLANE_URL = "http://127.0.0.1:6987"
DEFAULT_DATA_DIR = "/var/lib/vigil-warden"

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class WardenConfig:
    """Everything the Warden process reads; see the module docstring."""

    control_plane_url: str = DEFAULT_CONTROL_PLANE_URL
    data_dir: Path = Path(DEFAULT_DATA_DIR)
    node_id: str | None = None
    enrollment_token: str | None = None
    segment_labels: tuple[str, ...] = ()
    trust_root_path: Path | None = None
    sync_interval_seconds: float = 60.0
    sync_timeout_seconds: float = 10.0
    missed_syncs_threshold: int = 3
    grace_window_seconds: float = 900.0
    sentinel_token: str | None = None
    sentinel_port: int = 8091
    health_port: int = 9092
    metrics_port: int = 9093
    bind_host: str = "127.0.0.1"
    max_alert_queue: int = 1000
    max_alert_batch: int = 100
    max_alert_bytes: int = 1024 * 1024
    self_addresses: tuple[str, ...] = ()
    gateway_addresses: tuple[str, ...] = ()
    control_plane_addresses: tuple[str, ...] = ()
    dns_resolvers: tuple[str, ...] = ()
    slm_model_path: Path | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> WardenConfig:
        """Build the config from the environment (or a mapping, for tests)."""
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = env.get(name)
            return value if value not in (None, "") else None

        def get_float(name: str, default: float) -> float:
            raw = get(name)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError as exc:
                raise ValueError(f"{name}={raw!r} is not a number") from exc

        def get_int(name: str, default: int) -> int:
            raw = get(name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"{name}={raw!r} is not an integer") from exc

        def get_addresses(name: str) -> tuple[str, ...]:
            raw = get(name)
            if raw is None:
                return ()
            return tuple(part.strip() for part in raw.split(",") if part.strip())

        def get_labels() -> tuple[str, ...]:
            return get_addresses("WARDEN_SEGMENT_LABELS")

        data_dir = get("WARDEN_DATA_DIR")
        trust_root_path = get("WARDEN_TRUST_ROOT_PATH")
        slm_model_path = get("WARDEN_SLM_MODEL_PATH")
        return cls(
            control_plane_url=get("WARDEN_CONTROL_PLANE_URL")
            or DEFAULT_CONTROL_PLANE_URL,
            data_dir=Path(data_dir) if data_dir else Path(DEFAULT_DATA_DIR),
            node_id=get("WARDEN_NODE_ID"),
            enrollment_token=get("WARDEN_ENROLLMENT_TOKEN"),
            segment_labels=get_labels(),
            trust_root_path=Path(trust_root_path) if trust_root_path else None,
            slm_model_path=Path(slm_model_path) if slm_model_path else None,
            sync_interval_seconds=get_float("WARDEN_SYNC_INTERVAL_SECONDS", 60.0),
            sync_timeout_seconds=get_float("WARDEN_SYNC_TIMEOUT_SECONDS", 10.0),
            missed_syncs_threshold=get_int("WARDEN_MISSED_SYNCS_THRESHOLD", 3),
            grace_window_seconds=get_float("WARDEN_GRACE_WINDOW_SECONDS", 900.0),
            sentinel_token=get("WARDEN_SENTINEL_TOKEN"),
            sentinel_port=get_int("WARDEN_SENTINEL_PORT", 8091),
            health_port=get_int("WARDEN_HEALTH_PORT", 9092),
            metrics_port=get_int("WARDEN_METRICS_PORT", 9093),
            bind_host=get("WARDEN_BIND_HOST") or "127.0.0.1",
            max_alert_queue=get_int("WARDEN_MAX_ALERT_QUEUE", 1000),
            max_alert_batch=get_int("WARDEN_MAX_ALERT_BATCH", 100),
            max_alert_bytes=get_int("WARDEN_MAX_ALERT_BYTES", 1024 * 1024),
            self_addresses=get_addresses("WARDEN_SELF_ADDRESSES"),
            gateway_addresses=get_addresses("WARDEN_GATEWAY_ADDRESSES"),
            control_plane_addresses=get_addresses("WARDEN_CONTROL_PLANE_ADDRESSES"),
            dns_resolvers=get_addresses("WARDEN_DNS_RESOLVERS"),
            log_level=(get("WARDEN_LOG_LEVEL") or "INFO").upper(),
        )

    def validate(self) -> tuple[str, ...]:
        """Return every problem that must stop the process from starting.

        The autonomy envelope is deliberately absent — it is signed into the
        pack, not a knob here. Nothing validated below can loosen authority.
        """
        problems: list[str] = []
        url = self.control_plane_url
        if (
            not (url.startswith("http://") or url.startswith("https://"))
            or len(url) < 8
        ):
            problems.append("WARDEN_CONTROL_PLANE_URL must be an http(s) base URL")
        if self.node_id is not None:
            try:
                validate_node_id(self.node_id)
            except EnrollmentTokenError as exc:
                problems.append(f"WARDEN_NODE_ID invalid: {exc}")
        if self.trust_root_path is None:
            problems.append(
                "WARDEN_TRUST_ROOT_PATH is required: without a baked-in trust "
                "root no policy pack can verify, so the node could never sync"
            )
        if self.sync_interval_seconds <= 0:
            problems.append("WARDEN_SYNC_INTERVAL_SECONDS must be positive")
        if self.sync_timeout_seconds <= 0:
            problems.append("WARDEN_SYNC_TIMEOUT_SECONDS must be positive")
        if self.missed_syncs_threshold < 1:
            problems.append("WARDEN_MISSED_SYNCS_THRESHOLD must be at least 1")
        if self.grace_window_seconds < 0:
            problems.append("WARDEN_GRACE_WINDOW_SECONDS must not be negative")
        ports = {
            "WARDEN_SENTINEL_PORT": self.sentinel_port,
            "WARDEN_HEALTH_PORT": self.health_port,
            "WARDEN_METRICS_PORT": self.metrics_port,
        }
        for name, port in ports.items():
            if not 1 <= port <= 65535:
                problems.append(f"{name} must be a valid port")
        if len(set(ports.values())) != len(ports):
            problems.append(
                "WARDEN_SENTINEL_PORT, WARDEN_HEALTH_PORT and "
                "WARDEN_METRICS_PORT must be distinct"
            )
        if self.max_alert_queue < 1:
            problems.append("WARDEN_MAX_ALERT_QUEUE must be at least 1")
        if self.max_alert_batch < 1:
            problems.append("WARDEN_MAX_ALERT_BATCH must be at least 1")
        if self.max_alert_bytes < 1:
            problems.append("WARDEN_MAX_ALERT_BYTES must be at least 1")
        if not self.bind_host:
            problems.append("WARDEN_BIND_HOST must not be empty")
        if self.log_level not in _LOG_LEVELS:
            problems.append(
                "WARDEN_LOG_LEVEL must be one of %s" % ", ".join(_LOG_LEVELS)
            )
        for name, addresses in (
            ("WARDEN_SELF_ADDRESSES", self.self_addresses),
            ("WARDEN_GATEWAY_ADDRESSES", self.gateway_addresses),
            ("WARDEN_CONTROL_PLANE_ADDRESSES", self.control_plane_addresses),
            ("WARDEN_DNS_RESOLVERS", self.dns_resolvers),
        ):
            for entry in addresses:
                try:
                    _parse_address_entry(entry)
                except ValueError as exc:
                    problems.append(f"{name} entry {entry!r} invalid: {exc}")
        return tuple(problems)


def _parse_address_entry(entry: str) -> None:
    """Parse an address entry the way the target guard will at enforcement.

    Mirrors core/edge/target_guard.py's network parsing so a bad operator
    address fails at startup, not on the first alert. Kept in sync by that
    module's tests.
    """
    if "/" in entry:
        ipaddress.ip_network(entry, strict=True)
    else:
        ipaddress.ip_address(entry)

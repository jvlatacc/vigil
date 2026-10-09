"""Settings the edge daemon reads from its environment (prefix ``VIGIL_EDGE_``).

Pure functions over a mapping, the Medic pattern: only the CLI entry point
touches the process environment. Thresholds and caps are deliberately absent
from here — they live in the signed bundle, where changing them is a reviewed
commit plus a signature (design spec, "Configuration — the ratchet-compliant
set").
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from services.edge import __version__

ENABLED_VAR = "VIGIL_EDGE_ENABLED"
NODE_ID_VAR = "VIGIL_EDGE_NODE_ID"
MODE_VAR = "VIGIL_EDGE_MODE"
CONTROL_URL_VAR = "VIGIL_EDGE_CONTROL_URL"
ENROLLMENT_TOKEN_VAR = "VIGIL_EDGE_ENROLLMENT_TOKEN"
SEGMENT_SCOPE_VAR = "VIGIL_EDGE_SEGMENT_SCOPE"
CREDENTIAL_FILE_VAR = "VIGIL_EDGE_CREDENTIAL_FILE"
DATA_DIR_VAR = "VIGIL_EDGE_DATA_DIR"
TRUST_STORE_VAR = "VIGIL_EDGE_TRUST_STORE"
MODEL_VAR = "VIGIL_EDGE_MODEL"
MODEL_DIGEST_VAR = "VIGIL_EDGE_MODEL_DIGEST"
MODEL_URL_VAR = "VIGIL_EDGE_OLLAMA_URL"
HEALTH_PORT_VAR = "VIGIL_EDGE_HEALTH_PORT"
NODE_LABELS_VAR = "VIGIL_EDGE_NODE_LABELS"
EVE_PATH_VAR = "VIGIL_EDGE_EVE_PATH"
JOURNAL_MAX_BYTES_VAR = "VIGIL_EDGE_JOURNAL_MAX_BYTES"
K8S_API_URL_VAR = "VIGIL_EDGE_K8S_API_URL"
K8S_TOKEN_FILE_VAR = "VIGIL_EDGE_K8S_TOKEN_FILE"
K8S_CA_FILE_VAR = "VIGIL_EDGE_K8S_CA_FILE"
REAPER_INTERVAL_VAR = "VIGIL_EDGE_REAPER_INTERVAL_SECONDS"

DEFAULT_K8S_TOKEN_FILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
DEFAULT_K8S_CA_FILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
SYNC_INTERVAL_VAR = "VIGIL_EDGE_SYNC_INTERVAL_SECONDS"
SYNC_BATCH_VAR = "VIGIL_EDGE_SYNC_BATCH_SIZE"
SYNC_TIMEOUT_VAR = "VIGIL_EDGE_SYNC_TIMEOUT_SECONDS"

DEFAULT_JOURNAL_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_SYNC_INTERVAL_SECONDS = 30.0
DEFAULT_SYNC_BATCH_SIZE = 250
DEFAULT_SYNC_TIMEOUT_SECONDS = 10.0
#: Wire contract: the control plane's batch bound (core.edge.events
#: MAX_EVENTS_PER_BATCH). Restated here because services.edge cannot import
#: core — the two constants are pinned equal by test_protocol.py.
WIRE_MAX_EVENTS_PER_BATCH = 500

MODES = ("gateway", "cluster")

_TRUE = {"true", "1", "yes", "on"}


def flag_value(env: Mapping[str, str]) -> str | None:
    return env.get(ENABLED_VAR)


def is_enabled(env: Mapping[str, str]) -> bool:
    """The master switch. Anything not clearly "on" is off: fail safe."""
    return (flag_value(env) or "").strip().lower() in _TRUE


class ConfigError(ValueError):
    """The environment is recognisably wrong (bad mode, unparsable labels)."""


@dataclass(frozen=True)
class EdgeConfig:
    """One edge node's settings. Syntax problems raise in ``from_env``;
    semantic problems (a missing node id on an enabled daemon) are collected
    by :meth:`validate` so the CLI can report them all at once."""

    node_id: str = ""
    mode: str = "gateway"
    control_url: str = "https://vigil.internal"
    enrollment_token: str = ""
    segment_scope: dict[str, str] = field(default_factory=dict)
    credential_file: Path = Path("/var/lib/vigil-edge/credential")
    data_dir: Path = Path("/var/lib/vigil-edge")
    trust_store: Path = Path("/etc/vigil-edge/trust-root.dsse.json")
    model: str | None = "qwen2.5:1.5b"
    model_digest: str = ""
    model_url: str = "http://localhost:11434"
    health_port: int = 9091
    node_labels: dict[str, str] = field(default_factory=dict)
    eve_path: Path | None = None
    journal_max_bytes: int = DEFAULT_JOURNAL_MAX_BYTES
    # Cluster mode's containment. None = no API server configured, the
    # NetworkPolicy executor is not installed. Token/CA default to the pod's
    # own service-account mount.
    k8s_api_url: str | None = None
    k8s_token_file: Path = DEFAULT_K8S_TOKEN_FILE
    k8s_ca_file: Path = DEFAULT_K8S_CA_FILE
    reaper_interval_seconds: int = 60
    sync_interval_seconds: float = DEFAULT_SYNC_INTERVAL_SECONDS
    sync_batch_size: int = DEFAULT_SYNC_BATCH_SIZE
    sync_timeout_seconds: float = DEFAULT_SYNC_TIMEOUT_SECONDS
    edge_version: str = __version__

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EdgeConfig:
        """Parse ``VIGIL_EDGE_*``. Raises ConfigError for values that are
        recognisably wrong; call :meth:`validate` for values that are missing."""
        mode = (env.get(MODE_VAR) or "gateway").strip().lower()
        if mode not in MODES:
            raise ConfigError(f"{MODE_VAR} must be one of {MODES}, got {mode!r}")

        raw_port = (env.get(HEALTH_PORT_VAR) or "9091").strip()
        try:
            health_port = int(raw_port)
        except ValueError as exc:
            raise ConfigError(
                f"{HEALTH_PORT_VAR} must be an integer, got {raw_port!r}"
            ) from exc

        raw_labels = (env.get(NODE_LABELS_VAR) or "{}").strip()
        try:
            parsed_labels = json.loads(raw_labels)
        except ValueError as exc:
            raise ConfigError(f"{NODE_LABELS_VAR} is not JSON: {exc}") from exc
        if not isinstance(parsed_labels, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed_labels.items()
        ):
            raise ConfigError(
                f"{NODE_LABELS_VAR} must be a JSON object of string -> string"
            )

        # Absent -> the repo's local-model default; present-but-empty -> the
        # advisor is deliberately off.
        raw_model = env.get(MODEL_VAR)
        model = "qwen2.5:1.5b" if raw_model is None else raw_model.strip()
        eve_path = (env.get(EVE_PATH_VAR) or "").strip()

        # Cluster mode's API server: explicit env wins; otherwise the pod's
        # own service environment. Neither present -> the NetworkPolicy
        # executor is not installed and dispatch records no_executor.
        k8s_api_url = (env.get(K8S_API_URL_VAR) or "").strip()
        if not k8s_api_url:
            host = (env.get("KUBERNETES_SERVICE_HOST") or "").strip()
            port = (env.get("KUBERNETES_SERVICE_PORT_HTTPS") or "443").strip()
            if host:
                k8s_api_url = f"https://{host}:{port}"

        raw_scope = (env.get(SEGMENT_SCOPE_VAR) or "").strip()
        parsed_scope: dict[str, str] = {}
        if raw_scope:
            try:
                scope_json = json.loads(raw_scope)
            except ValueError as exc:
                raise ConfigError(f"{SEGMENT_SCOPE_VAR} is not JSON: {exc}") from exc
            if not isinstance(scope_json, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in scope_json.items()
            ):
                raise ConfigError(
                    f"{SEGMENT_SCOPE_VAR} must be a JSON object of string -> string"
                )
            parsed_scope = dict(scope_json)

        raw_interval = (env.get(SYNC_INTERVAL_VAR) or "").strip()
        sync_interval_seconds = DEFAULT_SYNC_INTERVAL_SECONDS
        if raw_interval:
            try:
                sync_interval_seconds = float(raw_interval)
            except ValueError as exc:
                raise ConfigError(
                    f"{SYNC_INTERVAL_VAR} must be a number of seconds, got {raw_interval!r}"
                ) from exc
            if sync_interval_seconds <= 0:
                raise ConfigError(
                    f"{SYNC_INTERVAL_VAR} must be positive, got {sync_interval_seconds}"
                )

        raw_batch = (env.get(SYNC_BATCH_VAR) or "").strip()
        sync_batch_size = DEFAULT_SYNC_BATCH_SIZE
        if raw_batch:
            try:
                sync_batch_size = int(raw_batch)
            except ValueError as exc:
                raise ConfigError(
                    f"{SYNC_BATCH_VAR} must be an integer, got {raw_batch!r}"
                ) from exc
            if not 1 <= sync_batch_size <= WIRE_MAX_EVENTS_PER_BATCH:
                raise ConfigError(
                    f"{SYNC_BATCH_VAR} must be 1-{WIRE_MAX_EVENTS_PER_BATCH}, "
                    f"got {sync_batch_size}"
                )

        raw_timeout = (env.get(SYNC_TIMEOUT_VAR) or "").strip()
        sync_timeout_seconds = DEFAULT_SYNC_TIMEOUT_SECONDS
        if raw_timeout:
            try:
                sync_timeout_seconds = float(raw_timeout)
            except ValueError as exc:
                raise ConfigError(
                    f"{SYNC_TIMEOUT_VAR} must be a number of seconds, got {raw_timeout!r}"
                ) from exc
            if sync_timeout_seconds <= 0:
                raise ConfigError(
                    f"{SYNC_TIMEOUT_VAR} must be positive, got {sync_timeout_seconds}"
                )

        raw_journal_max = (env.get(JOURNAL_MAX_BYTES_VAR) or "").strip()
        journal_max_bytes = DEFAULT_JOURNAL_MAX_BYTES
        if raw_journal_max:
            try:
                journal_max_bytes = int(raw_journal_max)
            except ValueError as exc:
                raise ConfigError(
                    f"{JOURNAL_MAX_BYTES_VAR} must be an integer byte count, got {raw_journal_max!r}"
                ) from exc
            if journal_max_bytes <= 0:
                raise ConfigError(
                    f"{JOURNAL_MAX_BYTES_VAR} must be positive, got {journal_max_bytes}"
                )

        raw_reaper = (env.get(REAPER_INTERVAL_VAR) or "").strip()
        reaper_interval = 60
        if raw_reaper:
            try:
                reaper_interval = int(raw_reaper)
            except ValueError as exc:
                raise ConfigError(
                    f"{REAPER_INTERVAL_VAR} must be an integer seconds count, got {raw_reaper!r}"
                ) from exc
            if reaper_interval <= 0:
                raise ConfigError(
                    f"{REAPER_INTERVAL_VAR} must be positive, got {reaper_interval}"
                )

        return cls(
            node_id=(env.get(NODE_ID_VAR) or "").strip(),
            mode=mode,
            control_url=(env.get(CONTROL_URL_VAR) or "").strip()
            or "https://vigil.internal",
            enrollment_token=env.get(ENROLLMENT_TOKEN_VAR) or "",
            credential_file=Path(
                env.get(CREDENTIAL_FILE_VAR) or "/var/lib/vigil-edge/credential"
            ),
            data_dir=Path(env.get(DATA_DIR_VAR) or "/var/lib/vigil-edge"),
            trust_store=Path(
                env.get(TRUST_STORE_VAR) or "/etc/vigil-edge/trust-root.dsse.json"
            ),
            model=model or None,
            model_digest=(env.get(MODEL_DIGEST_VAR) or "").strip(),
            model_url=(env.get(MODEL_URL_VAR) or "").strip()
            or "http://localhost:11434",
            health_port=health_port,
            node_labels=dict(parsed_labels),
            eve_path=Path(eve_path) if eve_path else None,
            journal_max_bytes=journal_max_bytes,
            k8s_api_url=k8s_api_url or None,
            k8s_token_file=Path(env.get(K8S_TOKEN_FILE_VAR) or DEFAULT_K8S_TOKEN_FILE),
            k8s_ca_file=Path(env.get(K8S_CA_FILE_VAR) or DEFAULT_K8S_CA_FILE),
            reaper_interval_seconds=reaper_interval,
            segment_scope=parsed_scope,
            sync_interval_seconds=sync_interval_seconds,
            sync_batch_size=sync_batch_size,
            sync_timeout_seconds=sync_timeout_seconds,
        )

    def validate(self) -> list[str]:
        """Problems that should stop an enabled daemon from starting."""
        problems: list[str] = []
        if not self.node_id:
            problems.append(f"{NODE_ID_VAR} is required for an enabled edge daemon")
        if self.mode not in MODES:
            problems.append(f"{MODE_VAR} must be one of {MODES}, got {self.mode!r}")
        if not 1 <= self.health_port <= 65535:
            problems.append(
                f"{HEALTH_PORT_VAR} must be 1-65535, got {self.health_port}"
            )
        if self.mode == "cluster" and not self.k8s_api_url:
            problems.append(
                f"{K8S_API_URL_VAR} (or KUBERNETES_SERVICE_HOST) is required in cluster mode"
            )
        return problems

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

DEFAULT_JOURNAL_MAX_BYTES = 64 * 1024 * 1024

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
        return problems

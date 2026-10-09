"""CEP runtime configuration, loaded from the documented env keys.

The keys and their defaults are documented in ``env.example`` (Streaming CEP
section); the defaults here must match that file exactly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env key; unset or empty falls back to the default."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUTHY


def _env_int(name: str, default: int, *, minimum: int) -> int:
    """Parse an integer env key.

    Garbage falls back to the default, and a value below ``minimum`` is
    clamped with a warning: the bounds are load-bearing (an unbounded CEP
    queue would defeat the drop design), so a nonsense value must not
    silently widen them.
    """
    raw = os.environ.get(name)
    value = default
    if raw is not None and raw.strip():
        try:
            value = int(raw.strip())
        except ValueError:
            logger.warning("Invalid %s=%r; using default %d", name, raw, default)
    if value < minimum:
        logger.warning("%s=%d below minimum %d; clamping", name, value, minimum)
        return minimum
    return value


@dataclass(frozen=True)
class CepConfig:
    """Runtime configuration for the in-process CEP engine."""

    enabled: bool = True
    queue_max: int = 1000
    snapshot_interval_s: int = 60
    graph_max_nodes: int = 10_000
    graph_max_edges: int = 50_000
    rules_path: str = "data/cep_rules"

    @classmethod
    def from_env(cls) -> "CepConfig":
        """Read the documented ``CEP_*`` env keys with the documented defaults."""
        return cls(
            enabled=_env_bool("CEP_ENABLED", True),
            queue_max=_env_int("CEP_QUEUE_MAX", 1000, minimum=1),
            snapshot_interval_s=_env_int("CEP_SNAPSHOT_INTERVAL_S", 60, minimum=1),
            graph_max_nodes=_env_int("CEP_GRAPH_MAX_NODES", 10_000, minimum=1),
            graph_max_edges=_env_int("CEP_GRAPH_MAX_EDGES", 50_000, minimum=1),
            rules_path=(
                os.environ.get("CEP_RULES_PATH", "").strip() or "data/cep_rules"
            ),
        )

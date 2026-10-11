"""CEP engine configuration, bridged from the process Settings.

The CEP_* env keys are documented in env.example and parsed as pydantic
Settings fields on core.config.Settings — the same channel every other
daemon knob uses (see DaemonConfig). This dataclass is the engine's typed
view of them, carrying the clamps the drop design relies on.

Parsing is strict by repo convention: a malformed value (e.g.
CEP_QUEUE_MAX="abc") fails Settings validation at startup, exactly as a
malformed DAEMON_TRIAGE_TIMEOUT does. The clamps below narrow, never
widen, the bounds: a misconfigured unbounded queue would defeat the
drop-newest design, so a value under the floor becomes the floor.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import get_settings


@dataclass
class CepConfig:
    """The engine's typed configuration, bridged from Settings."""

    enabled: bool = True
    queue_max: int = 1000
    snapshot_interval_s: int = 60
    graph_max_nodes: int = 10000
    graph_max_edges: int = 50000
    rules_path: str = "data/cep_rules"

    @classmethod
    def from_env(cls) -> "CepConfig":
        """Bridge from Settings (env-documented CEP_* keys), clamping the
        minimums: queue capacity below 1 cannot hold work, and a snapshot
        interval or graph cap below 1 disables the bounded-state guarantees
        rather than the engine — so both narrow to their floor."""
        settings = get_settings()
        return cls(
            enabled=settings.cep_enabled,
            queue_max=max(1, settings.cep_queue_max),
            snapshot_interval_s=max(1, settings.cep_snapshot_interval_s),
            graph_max_nodes=max(1, settings.cep_graph_max_nodes),
            graph_max_edges=max(1, settings.cep_graph_max_edges),
            # An empty path is an unset default, not a directory name.
            rules_path=settings.cep_rules_path or "data/cep_rules",
        )

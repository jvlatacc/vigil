"""Shared helpers for the deception (honey-routing) spine tests.

Imported by full package path (``tests.unit.deception.fixtures``), the way
``tests/unit/detections/fixtures`` is. Two layers, mirroring the house split:

- Pure-unit: the decision function, the approval gate, the recon predicate's
  deterministic halves, and an in-memory fake of the corroboration service
  let every boundary run without a database.
- ``external_service``-marked: the real lease rows, probe rows, approval
  rows and DryRun steering against the throwaway Postgres the unit conftest
  provisions — the durable half a fake cannot testify about.
"""

ATTACKER = "203.0.113.7"
VICTIM = "10.0.4.25"


def recon_finding(**overrides):
    """A recon-shaped finding the predicate should act on."""
    finding = {
        "finding_id": "find-001",
        "category": "recon",
        "severity": "low",
        "recommended_action": "investigate",
        "triage_confidence": 0.62,
        "mitre_predictions": {"T1046": 0.9, "T1018": 0.4},
        "entity_context": {
            "src_ips": [ATTACKER],
            "dst_ips": [VICTIM],
            "ports": [445, 3389],
        },
    }
    finding.update(overrides)
    return finding


class FakeProbeSignals:
    """The corroboration half of DeceptionSignalService, in memory."""

    def __init__(self, config=None, corroborated=True, kill_switch=False):
        from core.deception.config import DeceptionConfig

        self.config = config or DeceptionConfig(enabled=True)
        self.corroborated = corroborated
        self.kill_switch = kill_switch
        self.recorded = []

    def record_probe(self, source_ip, finding_id, evidence, now=None):
        self.recorded.append((source_ip, finding_id, evidence))

    def is_corroborated(self, source_ip, now=None):
        return self.corroborated

    def kill_switch_active(self, now=None):
        return self.kill_switch

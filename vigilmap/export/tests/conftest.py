"""Repo-root path setup and fixture row builders for the exporter tests.

The repo root goes on sys.path so both ``core.memory`` (the drift guard's
canonical side) and the ``vigilmap`` namespace resolve without an install,
from any working directory.

The fixture scenario mirrors the spec's demo story: two hunts over one
campaign — a phishing lure, C2 resolution, a compromised host — with verdicts
of four outcomes, a zero-subject verdict (the schema keeps that legitimate),
gaps, and per-source stances. Rows carry defanged values the way threat intel
writes them, so normalization is exercised on every path.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

T_FIRST = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
T_LAST = datetime(2026, 9, 14, 18, 30, tzinfo=timezone.utc)
T_CONCLUDED = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


def sighting_row(
    row_id: int,
    entity_key: str,
    source_system: str,
    inv: str = "h-002",
    first_seen: Any = T_FIRST,
    last_seen: Any = T_LAST,
    concluded_at: Any = T_CONCLUDED,
) -> Dict[str, Any]:
    return {
        "id": row_id,
        "entity_key": entity_key,
        "investigation_kind": "hunt",
        # Raw id: the transform prefixes the minted node id itself.
        "investigation_id": inv,
        "source_system": source_system,
        "hit_count": 3,
        "attacker_influenceable": False,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "concluded_at": concluded_at,
    }


def verdict_row(
    row_id: int,
    investigation_id: str,
    outcome: str,
    statement: str,
    subjects: List[str],
    techniques: Any = None,
    rationale: str = "evidence gathered across sources",
) -> Dict[str, Any]:
    return {
        "id": row_id,
        "investigation_kind": "hunt",
        "investigation_id": investigation_id,
        "hypothesis_id": f"hyp-{row_id}",
        "statement": statement,
        "outcome": outcome,
        "rationale": rationale,
        "subject_entities": subjects,
        "attacker_influenceable_only": False,
        "trust": "agent",
        "first_seen": T_FIRST,
        "last_seen": T_LAST,
        "window_source": "observed",
        "concluded_at": T_CONCLUDED,
        "techniques": techniques,
    }


def gap_row(
    row_id: int,
    investigation_id: str,
    subjects: List[str],
    disposition: str = "deprioritised",
) -> Dict[str, Any]:
    return {
        "id": row_id,
        "investigation_kind": "hunt",
        "investigation_id": investigation_id,
        "hypothesis_id": f"gap-hyp-{row_id}",
        "statement": "Was the staging archive exfiltrated?",
        "disposition": disposition,
        "reason": "budget exhausted before the archive question",
        "subject_entities": subjects,
        "concluded_at": T_CONCLUDED,
    }


def source_row(
    verdict_id: int, source_system: str, stance: str, source_tier: str = "telemetry"
) -> Dict[str, Any]:
    return {
        "verdict_id": verdict_id,
        "source_system": source_system,
        "stance": stance,
        "source_tier": source_tier,
    }


@pytest.fixture
def rows() -> Dict[str, List[Dict[str, Any]]]:
    """The fixture scenario: two hunts, four sightings, four verdicts, one gap."""
    return {
        "sightings": [
            sighting_row(1, "domain:evildomain[.]com", "wazuh"),
            sighting_row(2, "ip:203.0.113.7", "edr"),
            sighting_row(3, "email:billing@vendor.example", "phishfeed", inv="h-001"),
            sighting_row(4, "url:hxxp://evildomain[.]com/payload", "proxy"),
        ],
        "verdicts": [
            verdict_row(
                1,
                "h-002",
                "proven",
                "Ransomware pre-staging via the lure domain and C2 resolution",
                ["domain:evildomain[.]com", "ip:203.0.113.7", "user:j.wilson"],
                techniques=["T1566", "T1071"],
            ),
            verdict_row(
                2,
                "h-001",
                "disproven",
                "The lure was vendor billing correspondence, not a phishing lure",
                ["email:billing@vendor.example"],
                techniques=[],
            ),
            verdict_row(
                3,
                "h-002",
                "inconclusive",
                "Any lateral movement at all",  # names no subject, by design
                [],
                techniques=None,
            ),
            verdict_row(
                4,
                "h-001",
                "handed_off",
                "Compromised workstation handed to response",
                ["host:WS-0403"],
                techniques=["T1078"],
            ),
        ],
        "verdict_sources": [
            source_row(1, "wazuh", "supports"),
            source_row(1, "edr", "supports"),
            source_row(1, "wazuh", "supports"),  # duplicate — one link, not two
            source_row(2, "phishfeed", "weakens", "feed"),
        ],
        "gaps": [gap_row(1, "h-002", ["host:WS-0403"])],
    }

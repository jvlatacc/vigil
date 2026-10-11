"""Unit tests for the CEP pattern engine (spec AC 2 + bounded state).

The sequence tests use a rule mirroring the spec's ransomware example:
an EDR step (T1486) and a SIEM step (T1486/T1070) on one host inside a
600 s window, 300 s gaps. All timestamps are explicit event times — the
engine sequences on event time, so the tests are deterministic without a
frozen clock; the wall/monotonic clocks are only monkeypatched for the
TTL and sweeper tests that legitimately own them.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import pytest

import core.cep.engine as engine_module
from core.cep.engine import CORROBORATION_BONUS, CepEngine, SequenceMatch
from core.cep.normalize import NormalizedFinding
from core.cep.rules import CepRule, Step

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def _ransomware_rule(**overrides: Any) -> CepRule:
    """The spec's ransomware-staging-2src contract as a CepRule."""
    values: Dict[str, Any] = {
        "id": "ransomware-staging-2src",
        "entity_key_fields": ("host",),
        "window_seconds": 600,
        "steps": (
            Step(
                sources=("crowdstrike", "sentinelone"),
                techniques=("T1486",),
                max_gap_seconds=300,
            ),
            Step(
                sources=("splunk", "elastic", "opensearch"),
                techniques=("T1486", "T1070"),
                max_gap_seconds=300,
            ),
        ),
        "action_type": "isolate_host",
        "target_field": "host",
        "base_confidence": 0.82,
    }
    values.update(overrides)
    return CepRule(**values)


def _evt(
    finding_id: Optional[str],
    source: str,
    ts: Optional[datetime],
    *,
    host: Optional[str] = "WKS-1",
    techniques: Tuple[str, ...] = ("T1486",),
    severity: Optional[str] = None,
) -> NormalizedFinding:
    return NormalizedFinding(
        finding_id=finding_id,
        data_source=source,
        severity=severity,
        host=host,
        techniques=techniques,
        timestamp=ts,
    )


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


class TestSequenceMatching:
    def test_in_window_two_source_sequence_fires_exactly_one_match(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        first = engine.on_event(_evt("edr-1", "crowdstrike", _at(0), severity="high"))
        assert first == []  # partial sequence: no match yet

        matches = engine.on_event(
            _evt("siem-1", "splunk", _at(120), severity="critical")
        )

        assert len(matches) == 1
        match = matches[0]
        assert isinstance(match, SequenceMatch)
        assert match.rule_id == "ransomware-staging-2src"
        assert match.action_type == "isolate_host"
        assert match.target_field == "host"
        assert match.entities == {"host": "WKS-1"}
        assert match.entity_key == "host=WKS-1"
        assert match.finding_ids == ("edr-1", "siem-1")
        assert match.sources == ("crowdstrike", "splunk")
        # base 0.82 + corroboration 0.10 (two distinct sources).
        assert match.confidence == pytest.approx(0.92)
        assert match.started_at == pytest.approx(_at(0).timestamp())
        assert match.completed_at == pytest.approx(_at(120).timestamp())
        assert match.window_bucket == int(_at(0).timestamp() // 600)
        assert match.graph_path is None  # entity graph lands in the sibling PR
        # The consumed machine is gone: a third event cannot re-fire it.
        assert engine.counts()["machines"] == 0

    def test_same_source_sequence_gets_no_corroboration_bonus(self) -> None:
        rule = _ransomware_rule(
            id="same-source",
            steps=(
                Step(
                    sources=("crowdstrike",), techniques=("T1486",), max_gap_seconds=300
                ),
                Step(
                    sources=("crowdstrike",), techniques=("T1486",), max_gap_seconds=300
                ),
            ),
        )
        engine = CepEngine([rule])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        (match,) = engine.on_event(_evt("edr-2", "crowdstrike", _at(60)))

        assert match.confidence == rule.base_confidence

    def test_gap_overshoot_does_not_match(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        matches = engine.on_event(_evt("siem-1", "splunk", _at(301)))

        assert matches == []  # gap 301 s > 300 s: the SIEM event came too late
        # The machine kept waiting, and a fresh attempt re-anchors from the
        # latest EDR event — the stale anchor never produces a match.
        engine.on_event(_evt("edr-2", "crowdstrike", _at(450)))
        (match,) = engine.on_event(_evt("siem-2", "splunk", _at(500)))
        assert match.finding_ids == ("edr-2", "siem-2")

    def test_whole_sequence_expiry_does_not_match(self) -> None:
        # Three steps whose per-step gaps all hold but whose total span
        # exceeds the 600 s window: the first gap is wide (500 s) so the
        # window, not a step gap, is what rejects the final event.
        rule = _ransomware_rule(
            id="three-step",
            steps=(
                Step(
                    sources=("crowdstrike",), techniques=("T1486",), max_gap_seconds=500
                ),
                Step(sources=("splunk",), techniques=("T1486",), max_gap_seconds=300),
                Step(sources=("elastic",), techniques=("T1070",), max_gap_seconds=300),
            ),
        )
        engine = CepEngine([rule])

        engine.on_event(_evt("a", "crowdstrike", _at(0)))
        engine.on_event(_evt("b", "splunk", _at(450)))
        matches = engine.on_event(_evt("c", "elastic", _at(701)))
        assert matches == []  # gap 251 s holds, but 701 s from anchor > 600 s

        # Boundary: exactly the window is inside it.
        engine2 = CepEngine([rule])
        engine2.on_event(_evt("a", "crowdstrike", _at(0)))
        engine2.on_event(_evt("b", "splunk", _at(450)))
        (match,) = engine2.on_event(
            _evt("c", "elastic", _at(600), techniques=("T1070",))
        )
        assert match.finding_ids == ("a", "b", "c")

    def test_cross_entity_keys_do_not_bleed(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-a", "crowdstrike", _at(0), host="HOST-A"))
        engine.on_event(_evt("edr-b", "crowdstrike", _at(0), host="HOST-B"))
        match_a, match_b = engine.on_event(
            _evt("siem-a", "splunk", _at(100), host="HOST-A")
        ) + engine.on_event(_evt("siem-b", "splunk", _at(100), host="HOST-B"))

        assert match_a.entity_key == "host=HOST-A"
        assert match_a.finding_ids == ("edr-a", "siem-a")
        assert match_b.entity_key == "host=HOST-B"
        assert match_b.finding_ids == ("edr-b", "siem-b")

    def test_missing_key_field_skips_rule(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        assert engine.on_event(_evt("edr-1", "crowdstrike", _at(0), host=None)) == []
        assert engine.counts()["machines"] == 0

    def test_re_delivery_of_the_same_finding_id_is_idempotent(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        # The poller re-delivers the same finding (cursor replay): it must
        # not shape state twice.
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        assert engine.counts()["machines"] == 1

        engine.on_event(_evt("siem-1", "splunk", _at(120)))
        # Replay the whole sequence after completion: no second match.
        assert engine.on_event(_evt("edr-1", "crowdstrike", _at(0))) == []
        assert engine.on_event(_evt("siem-1", "splunk", _at(120))) == []

    def test_one_event_advances_one_step(self) -> None:
        # Both steps accept the same profile: a single event must not jump
        # the machine two steps.
        rule = _ransomware_rule(
            id="overlap",
            steps=(
                Step(sources=("crowdstrike",), techniques=("T1486",)),
                Step(sources=("crowdstrike",), techniques=("T1486",)),
            ),
        )
        engine = CepEngine([rule])

        assert engine.on_event(_evt("edr-1", "crowdstrike", _at(0))) == []
        (match,) = engine.on_event(_evt("edr-2", "crowdstrike", _at(60)))
        assert match.finding_ids == ("edr-1", "edr-2")

    def test_step0_match_reanchors_to_the_latest_attempt(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        # A second EDR event inside the window re-anchors: the sequence now
        # starts from the latest attempt, not the first.
        engine.on_event(_evt("edr-2", "crowdstrike", _at(500)))
        (match,) = engine.on_event(_evt("siem-1", "splunk", _at(550)))

        assert match.finding_ids == ("edr-2", "siem-1")
        assert match.started_at == pytest.approx(_at(500).timestamp())

    def test_out_of_order_event_does_not_extend_sequence(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(100)))
        # The SIEM event's source timestamp precedes the EDR step's: poll
        # lag reordered the evidence, and the engine refuses to fire on it.
        assert engine.on_event(_evt("siem-1", "splunk", _at(50))) == []
        assert engine.counts()["machines"] == 1  # machine kept waiting

    def test_events_without_timestamp_sequence_on_receive_time(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        engine.on_event(_evt("edr-1", "crowdstrike", None))
        (match,) = engine.on_event(_evt("siem-1", "splunk", None))

        assert match.finding_ids == ("edr-1", "siem-1")

    def test_severity_floor_blocks_step(self) -> None:
        rule = _ransomware_rule(
            steps=(
                Step(
                    sources=("crowdstrike",), techniques=("T1486",), min_severity="high"
                ),
                Step(sources=("splunk",), techniques=("T1486",)),
            ),
        )
        engine = CepEngine([rule])

        # A medium finding never opens a machine with a high floor.
        assert (
            engine.on_event(_evt("edr-low", "crowdstrike", _at(0), severity="medium"))
            == []
        )
        assert engine.counts()["machines"] == 0

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0), severity="critical"))
        # Step 2 declares no floor: the low-severity SIEM event completes
        # the sequence the high floor gated at step 1.
        (match,) = engine.on_event(_evt("siem-1", "splunk", _at(60), severity="low"))
        assert match.finding_ids == ("edr-1", "siem-1")


class TestBoundedState:
    def test_lru_cap_evicts_the_oldest_machine(self) -> None:
        rule = _ransomware_rule(id="lru")
        engine = CepEngine([rule], max_machines_per_rule=3)

        for i in range(5):
            engine.on_event(_evt(f"edr-{i}", "crowdstrike", _at(i), host=f"H{i}"))

        assert engine.counts()["machines"] == 3
        state = engine.serialize_machines()
        # The two least recently touched anchors (H0, H1) were shed.
        assert set(state["machines"]["lru"]) == {
            "host=H2",
            "host=H3",
            "host=H4",
        }

    def test_lru_touch_keeps_active_machines(self) -> None:
        rule = _ransomware_rule(id="lru")
        engine = CepEngine([rule], max_machines_per_rule=2)

        engine.on_event(_evt("edr-0", "crowdstrike", _at(0), host="H0"))
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0), host="H1"))
        # A second EDR event re-anchors H0's machine — an LRU touch that
        # moves it to the newest end, so the next insert sheds H1 instead.
        engine.on_event(_evt("edr-0b", "crowdstrike", _at(100), host="H0"))
        engine.on_event(_evt("edr-2", "crowdstrike", _at(150), host="H2"))

        assert engine.counts()["machines"] == 2
        assert set(engine.serialize_machines()["machines"]["lru"]) == {
            "host=H0",
            "host=H2",
        }
        # The touched machine's state survived the eviction pressure.
        (match,) = engine.on_event(_evt("siem-0", "splunk", _at(200), host="H0"))
        assert match.finding_ids == ("edr-0b", "siem-0")

    def test_sweeper_evicts_idle_machines_and_stale_seen_ids(self, monkeypatch) -> None:
        engine = CepEngine(
            [_ransomware_rule()], machine_idle_ttl_s=60.0, seen_ttl_s=60.0
        )
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        assert engine.counts() == {"machines": 1, "seen_ids": 1}

        # Both clocks jump past the TTLs; the sweeper must reclaim both.
        real_mono, real_wall = engine_module._now_mono(), engine_module._now_wall()
        monkeypatch.setattr(engine_module, "_now_mono", lambda: real_mono + 61.0)
        monkeypatch.setattr(engine_module, "_now_wall", lambda: real_wall + 61.0)

        result = engine.sweep()

        assert result == {"machines_evicted": 1, "seen_ids_evicted": 1}
        assert engine.counts() == {"machines": 0, "seen_ids": 0}

    async def test_run_sweeper_loop_reclaims_periodically(self, monkeypatch) -> None:
        engine = CepEngine(
            [_ransomware_rule()],
            machine_idle_ttl_s=60.0,
            sweep_interval_s=0.01,
        )
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        real_mono = engine_module._now_mono()
        monkeypatch.setattr(engine_module, "_now_mono", lambda: real_mono + 61.0)

        task = asyncio.create_task(engine.run_sweeper())
        try:
            await asyncio.sleep(0.05)
        finally:
            task.cancel()

        assert engine.counts()["machines"] == 0

    def test_property_style_stress_keeps_state_bounded(self, monkeypatch) -> None:
        rng = random.Random(20261009)
        rule = _ransomware_rule(id="stress")
        engine = CepEngine([rule], max_machines_per_rule=100)

        hosts = [f"H{i}" for i in range(40)]
        sources = ("crowdstrike", "sentinelone", "splunk", "elastic")
        clock = [_at(0).timestamp()]

        def fake_wall() -> float:
            return clock[0]

        monkeypatch.setattr(engine_module, "_now_wall", fake_wall)

        for i in range(3000):
            clock[0] += rng.randint(-30, 120)  # event time drifts forward
            host = rng.choice(hosts)
            source = rng.choice(sources)
            step_one = source in ("crowdstrike", "sentinelone")
            engine.on_event(
                _evt(
                    f"f{i}",
                    source,
                    datetime.fromtimestamp(clock[0], tz=timezone.utc),
                    host=host,
                    techniques=("T1486",) if step_one else ("T1070",),
                )
            )
            assert engine.counts()["machines"] <= 100

        # Past the TTLs, the sweeper reclaims everything the run left.
        monkeypatch.setattr(engine_module, "_now_wall", lambda: clock[0] + 10_000)
        real_mono = engine_module._now_mono()
        monkeypatch.setattr(engine_module, "_now_mono", lambda: real_mono + 10_000)
        engine.sweep()
        assert engine.counts() == {"machines": 0, "seen_ids": 0}


class TestSnapshotHooks:
    def test_serialize_is_json_safe_and_restores(self) -> None:
        rule = _ransomware_rule()
        engine = CepEngine([rule])
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))

        payload = engine.serialize_machines()
        json.dumps(payload)  # must not raise: the envelope rides JSONB
        assert set(payload) == {"machines", "seen_ids"}
        machine = payload["machines"]["ransomware-staging-2src"]["host=WKS-1"]
        assert machine["progress"] == 1
        assert machine["finding_ids"] == ["edr-1"]

        # A fresh engine (the restart) restores and completes the sequence.
        restored = CepEngine([rule])
        restored.restore_machines(payload)
        (match,) = restored.on_event(_evt("siem-1", "splunk", _at(120)))
        assert match.finding_ids == ("edr-1", "siem-1")
        # The restored seen-id table still swallows the pre-snapshot event.
        assert restored.on_event(_evt("edr-1", "crowdstrike", _at(0))) == []

    def test_restore_rejects_a_structurally_wrong_payload(self) -> None:
        engine = CepEngine([_ransomware_rule()])

        with pytest.raises(ValueError, match="machines"):
            engine.restore_machines({"unexpected": True})

    def test_restore_skips_unknown_rules_and_malformed_entries(self) -> None:
        engine = CepEngine([_ransomware_rule()])
        payload = {
            "machines": {
                "left-the-pack": {"host=X": {"progress": 1}},
                "ransomware-staging-2src": {
                    "host=OK": {
                        "anchor": 1.0,
                        "progress": 1,
                        "last": 1.0,
                        "finding_ids": ["edr-1"],
                        "sources": ["crowdstrike"],
                    },
                    "host=BAD": {"progress": "nine"},
                    "host=WORSE": "not a mapping",
                },
            },
            "seen_ids": {"edr-1": 9e9, 42: "not-a-string"},
        }

        engine.restore_machines(payload)

        machines = engine.serialize_machines()["machines"]
        assert list(machines["ransomware-staging-2src"]) == ["host=OK"]
        assert engine.counts()["seen_ids"] == 1

    def test_restore_replaces_existing_state(self) -> None:
        engine = CepEngine([_ransomware_rule()])
        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))

        engine.restore_machines({"machines": {}, "seen_ids": {}})

        assert engine.counts() == {"machines": 0, "seen_ids": 0}


class TestEngineContract:
    def test_disabled_rules_are_not_tracked(self) -> None:
        rule = _ransomware_rule(enabled=False)
        engine = CepEngine([rule])

        assert engine.on_event(_evt("edr-1", "crowdstrike", _at(0))) == []
        # The event rides the seen-set (dedup is engine-wide), but no
        # machine ever opens for a disabled rule.
        assert engine.counts() == {"machines": 0, "seen_ids": 1}

    def test_duplicate_rule_ids_are_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="duplicate rule id"):
            CepEngine([_ransomware_rule(), _ransomware_rule()])

    def test_one_event_can_fire_several_rules(self) -> None:
        edr_rule = _ransomware_rule(id="rule-edr")
        wide_rule = _ransomware_rule(
            id="rule-wide",
            steps=(
                Step(sources=("crowdstrike", "sentinelone", "splunk")),
                Step(sources=("crowdstrike", "sentinelone", "splunk")),
            ),
        )
        engine = CepEngine([edr_rule, wide_rule])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        matches = engine.on_event(_evt("siem-1", "splunk", _at(60)))

        assert {match.rule_id for match in matches} == {"rule-edr", "rule-wide"}

    def test_confidence_is_clamped_to_one(self) -> None:
        rule = _ransomware_rule(id="hot", base_confidence=0.99)
        engine = CepEngine([rule])

        engine.on_event(_evt("edr-1", "crowdstrike", _at(0)))
        (match,) = engine.on_event(_evt("siem-1", "splunk", _at(60)))

        assert match.confidence == pytest.approx(min(1.0, 0.99 + CORROBORATION_BONUS))

    def test_on_event_never_raises(self, monkeypatch) -> None:
        engine = CepEngine([_ransomware_rule()])

        # A finding with nothing in it is skipped, not fatal.
        assert engine.on_event(NormalizedFinding()) == []

        # An internal fault is contained at the engine boundary: the spec's
        # never-raises contract, with the tee's circuit deciding what next.

        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("engine fault")

        monkeypatch.setattr(engine, "_advance_rule", boom)
        assert engine.on_event(_evt("edr-1", "crowdstrike", _at(0))) == []

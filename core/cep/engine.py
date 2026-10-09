"""Keyed pattern engine: per-rule, per-entity sequence state machines.

For every rule, the engine keeps one machine per entity key (the rule's
``entity_key_fields`` values): a machine opens when step 0 matches, advances
one step per event while the gap to the previous step and the whole-sequence
window hold, and emits exactly one :class:`SequenceMatch` when the last step
completes. Machines are dicts — amortized O(1) per event — bounded three
ways: lazy event-time expiry on arrival, a periodic sweeper that evicts idle
machines and stale seen-ids, and an LRU cap per rule that sheds the oldest
partial state under sustained pressure (the same trade the tap's
drop-newest makes at queue level).

Sequencing runs on **event time**: the source's timestamp when the finding
carries one, else the engine's receive time (the honest fallback — the
normalizer never fabricates, but the engine must place every event on a
timeline to sequence it). Two clock domains live here, each in its own lane:

- event time (source timestamp or receive time) drives all gap/window
  decisions and what a match reports;
- a monotonic idle clock drives sweeper eviction only (a machine not
  advanced within twice its window is stale by construction — poll lag can
  make a legal completion arrive late, so the idle bound is deliberately
  looser than the window, and exactness at the boundary is not promised);
- the seen-set persists across restarts, so it expires on wall-epoch time.

``on_event`` never blocks and never raises (spec engine contract): an
unexpected fault is logged and skipped, and the tee's consecutive-error
circuit decides whether to pause the engine. It is not thread-safe by
design — the daemon is a single asyncio loop and this runs synchronously in
the tap's drain path.

Snapshot contract (shared with the entity-graph PR): the snapshot payload
envelope is versioned JSONB ``{engine_version, graph, machines, seen_ids}``;
the graph PR owns the envelope and the graph section. This engine owns the
``machines`` and ``seen_ids`` sections and exposes them through
:meth:`CepEngine.serialize_machines` / :meth:`CepEngine.restore_machines`
— pure, JSON-safe hooks the integration PR assembles into the envelope.
The engine does not import ``core.cep.graph`` or ``core.cep.snapshot``:
those land in the sibling PR and are wired by the integration PR.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.cep.normalize import NormalizedFinding
from core.cep.rules import CepRule, Step, meets_floor

logger = logging.getLogger(__name__)

# Envelope assembler hint (the integration PR stamps the payload row).
CEP_ENGINE_VERSION = 1

# Corroboration bonus, in the additive spirit of correlate_alerts
# (core.response.autonomous_response_service): a sequence confirmed by two
# or more distinct data sources is worth +0.10 confidence.
CORROBORATION_BONUS = 0.10

DEFAULT_MAX_MACHINES_PER_RULE = 1000
DEFAULT_SWEEP_INTERVAL_SECONDS = 30.0


def _now_wall() -> float:
    """Wall-epoch now — the seen-set's clock (it must survive restarts)."""
    return time.time()


def _now_mono() -> float:
    """Monotonic now — the machines' idle clock (immune to wall adjustments)."""
    return time.monotonic()


def _epoch(value: datetime) -> float:
    """Unix epoch seconds for a source timestamp; naive datetimes are read
    as UTC (the daemon's data is UTC throughout — the adapters emit ISO
    strings with and without a zone, and both mean the same clock)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).timestamp()
    return value.timestamp()


@dataclass(frozen=True)
class SequenceMatch:
    """A completed sequence: the audit-shaped record the bridge converts
    into one approval-gated action (integration PR).

    ``finding_ids`` and ``sources`` are the contributing evidence in step
    order (a finding without an id contributes to the sequence but records
    no id). ``confidence`` is the rule's base plus the corroboration bonus
    when two or more distinct sources contributed, clamped to [0, 1].
    ``graph_path`` is reserved for the entity-graph integration (the graph
    lands in the sibling PR); it is ``None`` until that wiring exists.
    """

    rule_id: str
    action_type: str
    target_field: str
    entity_key: str
    entities: Dict[str, str]
    finding_ids: Tuple[str, ...]
    sources: Tuple[str, ...]
    confidence: float
    started_at: float
    completed_at: float
    window_bucket: int
    graph_path: Optional[Tuple[str, ...]] = None


@dataclass
class _Machine:
    """One open partial sequence. Internal to the engine."""

    anchor: float
    progress: int  # steps matched so far; the next step is steps[progress]
    last: float  # event time of the most recent matched step
    finding_ids: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    touched_mono: float = field(default_factory=_now_mono)


class CepEngine:
    """Advances declarative rules over normalized findings; emits matches.

    Constructed with already-validated :class:`CepRule` objects (the loader
    owns pack validation); disabled rules are not tracked.
    """

    def __init__(
        self,
        rules: Sequence[CepRule],
        *,
        max_machines_per_rule: int = DEFAULT_MAX_MACHINES_PER_RULE,
        machine_idle_ttl_s: Optional[float] = None,
        seen_ttl_s: Optional[float] = None,
        sweep_interval_s: float = DEFAULT_SWEEP_INTERVAL_SECONDS,
    ) -> None:
        self._rules: "OrderedDict[str, CepRule]" = OrderedDict()
        for rule in rules:
            if not rule.enabled:
                logger.info("CEP rule %s is disabled; not tracking", rule.id)
                continue
            if rule.id in self._rules:
                raise ValueError(f"duplicate rule id '{rule.id}'")
            self._rules[rule.id] = rule

        max_window = max(
            (rule.window_seconds for rule in self._rules.values()), default=0
        )
        self._max_machines = max(1, max_machines_per_rule)
        # Idle eviction bound: twice the longest window covers poll lag; a
        # machine idle longer than that cannot be part of a live sequence.
        self._machine_idle_ttl = (
            machine_idle_ttl_s
            if machine_idle_ttl_s is not None
            else max(2.0 * max_window, 60.0)
        )
        # Seen-ids outlive the longest window so a re-delivered finding can
        # never re-enter a sequence it already shaped.
        self._seen_ttl = (
            seen_ttl_s if seen_ttl_s is not None else max(3600.0, 2.0 * max_window)
        )
        self._sweep_interval_s = sweep_interval_s

        # rule id -> entity key -> machine, insertion-ordered for LRU.
        self._machines: Dict[str, "OrderedDict[str, _Machine]"] = {
            rule.id: OrderedDict() for rule in self._rules.values()
        }
        # finding id -> wall-epoch expiry.
        self._seen: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Event path
    # ------------------------------------------------------------------

    def on_event(self, event: NormalizedFinding) -> List[SequenceMatch]:
        """Advance every rule's machines for one normalized finding.

        Never blocks, never raises: an internal fault is logged and the
        event skipped, leaving the spine and the other rules untouched.
        """
        try:
            return self._on_event(event)
        except Exception:
            logger.exception(
                "CEP engine: event evaluation failed; event skipped " "(finding_id=%s)",
                event.finding_id,
            )
            return []

    def _on_event(self, event: NormalizedFinding) -> List[SequenceMatch]:
        if event.finding_id:
            now = _now_wall()
            expiry = self._seen.get(event.finding_id)
            if expiry is not None and expiry > now:
                return []  # re-delivery: this finding already shaped state
            self._seen[event.finding_id] = now + self._seen_ttl

        epoch = _epoch(event.timestamp) if event.timestamp is not None else _now_wall()
        matches: List[SequenceMatch] = []
        for rule in self._rules.values():
            match = self._advance_rule(rule, event, epoch)
            if match is not None:
                matches.append(match)
        return matches

    def _advance_rule(
        self, rule: CepRule, event: NormalizedFinding, epoch: float
    ) -> Optional[SequenceMatch]:
        values: List[str] = []
        for field_name in rule.entity_key_fields:
            value = getattr(event, field_name)
            if not value:
                return None  # a key field is absent: this rule never keys
            values.append(value)
        key = ",".join(
            f"{name}={value}" for name, value in zip(rule.entity_key_fields, values)
        )
        machines = self._machines[rule.id]

        state = machines.get(key)
        if state is not None and self._timed_out(rule, state, epoch):
            del machines[key]
            state = None

        if state is not None:
            advanced = self._advance_open(rule, state, event, epoch, key)
            if advanced is _MATCHED:
                del machines[key]  # consumed: a completed sequence fires once
                return self._build_match(rule, state, values, key, epoch)
            if advanced is _ADVANCED:
                machines.move_to_end(key)  # LRU touch
                return None
            # The event did not fit the pending step — wrong profile, or the
            # gap/window bounds refused it. The machine keeps waiting: only
            # a step-0 match re-anchors it (the latest attempt wins).
            if not self._step_matches(rule.steps[0], event):
                return None
            del machines[key]  # replaced by the fresh anchor below
        elif not self._step_matches(rule.steps[0], event):
            return None  # a fresh machine only opens on a step-0 match

        machines[key] = _Machine(
            anchor=epoch,
            progress=1,
            last=epoch,
            finding_ids=[event.finding_id] if event.finding_id else [],
            sources=[event.data_source] if event.data_source else [],
        )
        machines.move_to_end(key)
        self._trim(rule, machines)
        return None

    def _advance_open(
        self,
        rule: CepRule,
        state: _Machine,
        event: NormalizedFinding,
        epoch: float,
        key: str,
    ) -> int:
        """Try to advance the open machine by one step.

        Returns _MATCHED when the final step completed, _ADVANCED when a
        mid-sequence step matched, _REJECTED when the time bounds broke the
        sequence, _NO_MATCH when the event does not fit the pending step.
        One event advances at most one step per machine.
        """
        step = rule.steps[state.progress]
        if not self._step_matches(step, event):
            return _NO_MATCH
        gap = epoch - state.last
        if gap < 0:
            # Out-of-order evidence: a step whose source timestamp precedes
            # the last matched step does not extend the sequence. The
            # re-anchor path still catches genuine restarts.
            logger.debug("CEP rule %s: out-of-order event on %s rejected", rule.id, key)
            return _REJECTED
        # The spec contract attaches the gap limit to the step being left —
        # "max gap to the NEXT step" — so steps[progress - 1].max_gap_seconds
        # governs the gap into the pending step (the final step's limit is
        # dead config; the sequence completes on its event).
        governing_gap = rule.steps[state.progress - 1].max_gap_seconds
        if gap > governing_gap:
            logger.debug(
                "CEP rule %s: gap %.0fs exceeds %.0fs on %s",
                rule.id,
                gap,
                governing_gap,
                key,
            )
            return _REJECTED
        if epoch - state.anchor > rule.window_seconds:
            logger.debug("CEP rule %s: sequence exceeded window on %s", rule.id, key)
            return _REJECTED

        state.progress += 1
        state.last = epoch
        state.touched_mono = _now_mono()
        if event.finding_id:
            state.finding_ids.append(event.finding_id)
        if event.data_source and event.data_source not in state.sources:
            state.sources.append(event.data_source)
        return _MATCHED if state.progress == len(rule.steps) else _ADVANCED

    def _timed_out(self, rule: CepRule, state: _Machine, epoch: float) -> bool:
        """Lazy event-time expiry: the whole-sequence window passed."""
        return epoch - state.anchor > rule.window_seconds

    def _trim(self, rule: CepRule, machines: "OrderedDict[str, _Machine]") -> None:
        while len(machines) > self._max_machines:
            key, _ = machines.popitem(last=False)  # least recently touched
            logger.warning(
                "CEP rule %s: machine LRU cap (%d) reached; evicted %s",
                rule.id,
                self._max_machines,
                key,
            )

    @staticmethod
    def _step_matches(step: Step, event: NormalizedFinding) -> bool:
        if step.sources is not None and (
            event.data_source is None or event.data_source not in step.sources
        ):
            return False
        if step.techniques is not None and not any(
            technique in step.techniques for technique in event.techniques
        ):
            return False
        return meets_floor(event.severity, step.min_severity)

    def _build_match(
        self,
        rule: CepRule,
        state: _Machine,
        values: Sequence[str],
        key: str,
        completed: float,
    ) -> SequenceMatch:
        distinct = {source for source in state.sources if source}
        confidence = rule.base_confidence + (
            CORROBORATION_BONUS if len(distinct) >= 2 else 0.0
        )
        confidence = round(min(1.0, max(0.0, confidence)), 6)
        return SequenceMatch(
            rule_id=rule.id,
            action_type=rule.action_type,
            target_field=rule.target_field,
            entity_key=key,
            entities=dict(zip(rule.entity_key_fields, values)),
            finding_ids=tuple(state.finding_ids),
            sources=tuple(state.sources),
            confidence=confidence,
            started_at=state.anchor,
            completed_at=completed,
            window_bucket=int(state.anchor // rule.window_seconds),
        )

    # ------------------------------------------------------------------
    # Bounded state
    # ------------------------------------------------------------------

    def sweep(self) -> Dict[str, int]:
        """Evict idle machines and expired seen-ids. Returns the counts."""
        now_mono = _now_mono()
        machines_evicted = 0
        for rule_id, machines in self._machines.items():
            stale = [
                key
                for key, machine in machines.items()
                if now_mono - machine.touched_mono > self._machine_idle_ttl
            ]
            for key in stale:
                del machines[key]
            machines_evicted += len(stale)

        now_wall = _now_wall()
        expired_ids = [
            finding_id
            for finding_id, expiry in self._seen.items()
            if expiry <= now_wall
        ]
        for finding_id in expired_ids:
            del self._seen[finding_id]

        if machines_evicted or expired_ids:
            logger.debug(
                "CEP sweeper: %d machine(s), %d seen-id(s) evicted",
                machines_evicted,
                len(expired_ids),
            )
        return {
            "machines_evicted": machines_evicted,
            "seen_ids_evicted": len(expired_ids),
        }

    async def run_sweeper(self) -> None:
        """The periodic sweeper task: expiry + housekeeping loop.

        Never exits on its own except via cancellation; a sweeper fault is
        logged and retried next interval (unbounded state is the failure
        mode that matters, so the loop survives transient errors).
        """
        while True:
            await asyncio.sleep(self._sweep_interval_s)
            try:
                self.sweep()
            except Exception:
                logger.exception("CEP sweeper failed; retrying next interval")

    def counts(self) -> Dict[str, int]:
        """Live state sizes, for the daemon's metrics wiring (spec AC 8)."""
        return {
            "machines": sum(len(m) for m in self._machines.values()),
            "seen_ids": len(self._seen),
        }

    # ------------------------------------------------------------------
    # Snapshot hooks (shared contract with the entity-graph PR)
    # ------------------------------------------------------------------

    def serialize_machines(self) -> Dict[str, Any]:
        """The engine-owned sections of the snapshot payload: a JSON-safe
        dict of ``{"machines": ..., "seen_ids": ...}``.

        The integration PR assembles the versioned envelope
        ``{engine_version, graph, machines, seen_ids}`` — this hook fills
        the ``machines`` and ``seen_ids`` sections; the graph PR owns the
        ``graph`` section. Machines carry event-time epochs (floats), so
        the payload is JSON-safe by construction.
        """
        return {
            "machines": {
                rule_id: {
                    key: {
                        "anchor": machine.anchor,
                        "progress": machine.progress,
                        "last": machine.last,
                        "finding_ids": list(machine.finding_ids),
                        "sources": list(machine.sources),
                    }
                    for key, machine in machines.items()
                }
                for rule_id, machines in self._machines.items()
                if machines
            },
            "seen_ids": dict(self._seen),
        }

    def restore_machines(self, state: Mapping[str, Any]) -> None:
        """Boot-time inverse of :meth:`serialize_machines`.

        Replaces in-memory machine and seen-id state (call before the tap
        starts feeding events). The envelope shape is strict (a non-mapping
        raises — a structurally wrong payload is a programming error);
        individual entries are tolerant — a machine whose rule left the
        pack, or an entry that fails validation, is logged and skipped so
        one corrupt row cannot keep the daemon from booting.
        """
        machines_raw = state.get("machines")
        seen_raw = state.get("seen_ids")
        if not isinstance(machines_raw, Mapping) or not isinstance(seen_raw, Mapping):
            raise ValueError(
                "CEP snapshot state must be a mapping with 'machines' and "
                "'seen_ids' sections"
            )

        restored_machines: Dict[str, "OrderedDict[str, _Machine]"] = {
            rule.id: OrderedDict() for rule in self._rules.values()
        }
        for rule_id, entries in machines_raw.items():
            rule = self._rules.get(str(rule_id))
            if rule is None or not isinstance(entries, Mapping):
                logger.warning(
                    "CEP snapshot: skipping machines for unknown rule %r",
                    rule_id,
                )
                continue
            bucket = restored_machines[rule.id]
            for key, raw in entries.items():
                machine = self._restore_machine(rule, str(key), raw)
                if machine is not None:
                    bucket[str(key)] = machine

        restored_seen: Dict[str, float] = {}
        for finding_id, expiry in seen_raw.items():
            if isinstance(finding_id, str) and isinstance(expiry, (int, float)):
                restored_seen[finding_id] = float(expiry)
            else:
                logger.warning(
                    "CEP snapshot: skipping malformed seen-id entry %r",
                    finding_id,
                )

        self._machines = restored_machines
        self._seen = restored_seen
        logger.info(
            "CEP snapshot restored: %d machine(s), %d seen-id(s)",
            sum(len(m) for m in self._machines.values()),
            len(self._seen),
        )

    def _restore_machine(self, rule: CepRule, key: str, raw: Any) -> Optional[_Machine]:
        if not isinstance(raw, Mapping):
            logger.warning("CEP snapshot: malformed machine %r (%s)", key, rule.id)
            return None
        try:
            progress = int(raw["progress"])
            anchor = float(raw["anchor"])
            last = float(raw["last"])
            finding_ids = [str(fid) for fid in raw.get("finding_ids", [])]
            sources = [str(source) for source in raw.get("sources", [])]
        except (KeyError, TypeError, ValueError):
            logger.warning("CEP snapshot: malformed machine %r (%s)", key, rule.id)
            return None
        if not 1 <= progress < len(rule.steps):
            logger.warning(
                "CEP snapshot: machine %r (%s) has out-of-range progress %d; "
                "skipping",
                key,
                rule.id,
                progress,
            )
            return None
        return _Machine(
            anchor=anchor,
            progress=progress,
            last=last,
            finding_ids=finding_ids,
            sources=sources,
        )


# _advance_open's return codes — ints so the hot path avoids attribute lookups.
_MATCHED, _ADVANCED, _REJECTED, _NO_MATCH = range(4)

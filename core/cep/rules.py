"""Declarative rule schema + YAML loader for the CEP pattern engine.

A rule is an ordered sequence of ``Step`` profiles anchored to one entity
key: EDR sees the behavior first, a SIEM corroborates it on the same host,
and the completed sequence becomes a ``SequenceMatch`` (``core.cep.engine``)
that the integration layer hands to the approval gate. Nothing here knows
about approval or execution — a rule only *declares* an ``action_type``
string; the loader validates it against ``core.response``'s ``ActionType``
values so a typo'd action cannot silently produce an unexecutable row.

Severity floors use the codebase's canonical vocabulary. Two precedents
agree on it: the daemon processor accepts exactly these four lowercase
values (``services/daemon/processor.py``, the triage sanitizer), and
``core.cases.case_automation_service._SEVERITY_ORDER`` ranks them
``low < medium < high < critical``. A finding whose severity is absent or
outside that vocabulary never meets a floor — the normalizer's rule that
missing means absent, never fabricated.

The loader is strict by repo convention (the same strictness
``core.cep.config`` applies to ``CEP_*`` env parsing): an unknown key, an
action type the response domain cannot execute, a single-step rule, or a
duplicate rule id raises ``RuleValidationError`` naming the file and field.
A malformed pack fails at boot, not the first time an analyst wonders why
nothing fired.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

import yaml

from core.response.approval_service import ActionType

logger = logging.getLogger(__name__)

# The entity fields NormalizedFinding can carry (core.cep.normalize). Rule
# keys and targets are validated against these because they are the only
# entity names the normalizer can ever produce.
ENTITY_FIELDS: Tuple[str, ...] = ("host", "user", "src_ip", "dest_ip")

# Canonical severity vocabulary, ascending. See the module docstring for the
# two codebase precedents this duplicates deliberately (a stable 4-entry
# constant beats a cross-domain import of case_automation_service).
SEVERITY_ORDER: Tuple[str, ...] = ("low", "medium", "high", "critical")

# A step with none of sources/techniques/min_severity matches every finding —
# a deliberate wildcard for "any further activity" steps. Nothing in the
# shipped pack relies on it.
_DEFAULT_MAX_GAP_SECONDS = 600

_ALLOWED_STEP_KEYS = frozenset(
    {"sources", "techniques", "min_severity", "max_gap_seconds"}
)
_ALLOWED_RULE_KEYS = frozenset(
    {
        "id",
        "entity_key_fields",
        "window_seconds",
        "steps",
        "action_type",
        "target_field",
        "base_confidence",
        "enabled",
    }
)


class RuleValidationError(ValueError):
    """A rule pack is malformed; the message names the file and the field."""


@dataclass(frozen=True)
class Step:
    """One ordered stage of a rule: the profile a finding must present.

    Every match criterion is optional; a step with none matches any finding
    (a wildcard step). ``sources`` filters on the normalized ``data_source``
    (the lowercase names the ingestion adapters set, e.g. ``"crowdstrike"``);
    ``techniques`` matches MITRE technique ids on the normalized finding;
    ``min_severity`` is a floor against :data:`SEVERITY_ORDER`.
    """

    sources: Optional[Tuple[str, ...]] = None
    techniques: Optional[Tuple[str, ...]] = None
    min_severity: Optional[str] = None
    # Seconds allowed between this step's matching event and the NEXT
    # step's event (the spec contract: "max gap to the NEXT step"). The
    # final step's value is dead config — the sequence completes on its
    # event.
    max_gap_seconds: int = _DEFAULT_MAX_GAP_SECONDS


@dataclass(frozen=True)
class CepRule:
    """A complete declarative sequence rule (spec rule contract).

    ``entity_key_fields`` names the normalized fields whose values key the
    per-entity state machine; every field must be present on an event for
    the event to enter this rule's machines (absent means skip — the engine
    never keys on a partial entity). ``target_field`` must be one of the key
    fields: the containment target is the entity the sequence was correlated
    about, so a target outside the key would not be pinned by the match.
    """

    id: str
    entity_key_fields: Tuple[str, ...]
    window_seconds: int
    steps: Tuple[Step, ...]
    action_type: str
    target_field: str
    base_confidence: float
    enabled: bool = True


def meets_floor(severity: Optional[str], floor: Optional[str]) -> bool:
    """Whether ``severity`` meets the ``min_severity`` floor.

    Pure and conservative: an absent severity meets no floor (a step that
    declares one simply does not fire on severity-less findings), and an
    unknown severity string is treated the same as absent — the vocabulary
    is closed, so guessing a rank would fabricate signal.
    """
    if floor is None:
        return True
    if severity is None:
        return False
    try:
        return SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index(floor)
    except ValueError:
        return False


def _rule_from_mapping(mapping: Any, *, source: str) -> CepRule:
    """Parse and validate one rule mapping. Raises RuleValidationError."""
    if not isinstance(mapping, Mapping):
        raise RuleValidationError(
            f"{source}: expected a mapping (one rule per file), got "
            f"{type(mapping).__name__}"
        )

    unknown = sorted(set(mapping) - _ALLOWED_RULE_KEYS)
    if unknown:
        raise RuleValidationError(
            f"{source}: unknown key(s) {', '.join(unknown)}; allowed: "
            f"{', '.join(sorted(_ALLOWED_RULE_KEYS))}"
        )

    for required in (
        "id",
        "entity_key_fields",
        "window_seconds",
        "steps",
        "action_type",
        "target_field",
        "base_confidence",
    ):
        if required not in mapping:
            raise RuleValidationError(f"{source}: missing required key '{required}'")

    rule_id = mapping["id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise RuleValidationError(f"{source}: 'id' must be a non-empty string")

    key_fields = _key_fields(mapping["entity_key_fields"], source=source)
    window = _window(mapping["window_seconds"], source=source)
    steps = _steps(mapping["steps"], source=source)
    action = _action_type(mapping["action_type"], source=source)
    target = mapping["target_field"]
    if not isinstance(target, str) or target not in key_fields:
        raise RuleValidationError(
            f"{source}: 'target_field' must be one of entity_key_fields "
            f"({', '.join(key_fields)}); got {target!r}"
        )
    base = _base_confidence(mapping["base_confidence"], source=source)
    enabled = mapping.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RuleValidationError(
            f"{source}: 'enabled' must be a bool, got {type(enabled).__name__}"
        )

    return CepRule(
        id=rule_id.strip(),
        entity_key_fields=key_fields,
        window_seconds=window,
        steps=steps,
        action_type=action,
        target_field=target,
        base_confidence=base,
        enabled=enabled,
    )


def _key_fields(raw: Any, *, source: str) -> Tuple[str, ...]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise RuleValidationError(
            f"{source}: 'entity_key_fields' must be a non-empty list of "
            f"{', '.join(ENTITY_FIELDS)}"
        )
    fields: List[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in ENTITY_FIELDS:
            raise RuleValidationError(
                f"{source}: 'entity_key_fields' entries must be among "
                f"{', '.join(ENTITY_FIELDS)}; got {item!r}"
            )
        if item in fields:
            raise RuleValidationError(f"{source}: 'entity_key_fields' repeats {item!r}")
        fields.append(item)
    return tuple(fields)


def _window(raw: Any, *, source: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise RuleValidationError(
            f"{source}: 'window_seconds' must be an integer >= 1, got {raw!r}"
        )
    return raw


def _action_type(raw: Any, *, source: str) -> str:
    valid = {action.value for action in ActionType}
    if not isinstance(raw, str) or raw not in valid:
        raise RuleValidationError(
            f"{source}: 'action_type' must be one of "
            f"{', '.join(sorted(valid))}; got {raw!r}"
        )
    return raw


def _base_confidence(raw: Any, *, source: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RuleValidationError(
            f"{source}: 'base_confidence' must be a number in [0, 1], got {raw!r}"
        )
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise RuleValidationError(
            f"{source}: 'base_confidence' must be in [0, 1], got {value}"
        )
    return value


def _steps(raw: Any, *, source: str) -> Tuple[Step, ...]:
    if not isinstance(raw, (list, tuple)):
        raise RuleValidationError(f"{source}: 'steps' must be a list of step mappings")
    if len(raw) < 2:
        raise RuleValidationError(
            f"{source}: a rule needs at least 2 steps (a compound sequence), "
            f"got {len(raw)}"
        )
    return tuple(_step(item, source=source, index=i) for i, item in enumerate(raw))


def _step(raw: Any, *, source: str, index: int) -> Step:
    label = f"{source}: steps[{index}]"
    if not isinstance(raw, Mapping):
        raise RuleValidationError(f"{label} must be a mapping")

    unknown = sorted(set(raw) - _ALLOWED_STEP_KEYS)
    if unknown:
        raise RuleValidationError(
            f"{label}: unknown key(s) {', '.join(unknown)}; allowed: "
            f"{', '.join(sorted(_ALLOWED_STEP_KEYS))}"
        )

    sources = _string_tuple(raw.get("sources"), label=label, field="sources")
    techniques = _string_tuple(raw.get("techniques"), label=label, field="techniques")

    min_severity = raw.get("min_severity")
    if min_severity is not None:
        if not isinstance(min_severity, str) or min_severity not in SEVERITY_ORDER:
            raise RuleValidationError(
                f"{label}: 'min_severity' must be one of "
                f"{', '.join(SEVERITY_ORDER)}; got {min_severity!r}"
            )

    max_gap = raw.get("max_gap_seconds", _DEFAULT_MAX_GAP_SECONDS)
    if isinstance(max_gap, bool) or not isinstance(max_gap, int) or max_gap < 0:
        raise RuleValidationError(
            f"{label}: 'max_gap_seconds' must be an integer >= 0, got {max_gap!r}"
        )

    return Step(
        sources=sources,
        techniques=techniques,
        min_severity=min_severity,
        max_gap_seconds=max_gap,
    )


def _string_tuple(raw: Any, *, label: str, field: str) -> Optional[Tuple[str, ...]]:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise RuleValidationError(
            f"{label}: '{field}' must be a list of strings, got "
            f"{type(raw).__name__}"
        )
    values: List[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise RuleValidationError(
                f"{label}: '{field}' entries must be non-empty strings; "
                f"got {item!r}"
            )
        values.append(item.strip())
    return tuple(values)


def load_rules(path: str | Path) -> Tuple[CepRule, ...]:
    """Load a rule pack directory (``*.yaml`` / ``*.yml``, one rule per file,
    sorted by filename) into validated :class:`CepRule` objects.

    Pure file IO + parsing: no settings access (the caller passes
    ``CepConfig.rules_path``), no engine construction. Disabled rules load
    with ``enabled=False`` — the engine decides whether to track them.

    Raises :class:`RuleValidationError` for a missing/non-directory path, an
    unreadable or non-mapping file, any schema violation, or a duplicate
    rule id across the pack.
    """
    directory = Path(path)
    if not directory.is_dir():
        raise RuleValidationError(f"CEP rules path is not a directory: {directory}")

    files = sorted(
        (*directory.glob("*.yaml"), *directory.glob("*.yml")),
        key=lambda p: p.name,
    )

    rules: List[CepRule] = []
    seen_ids: dict = {}
    for file in files:
        try:
            raw = yaml.safe_load(file.read_text())
        except yaml.YAMLError as err:
            raise RuleValidationError(f"{file}: unparseable YAML: {err}") from err
        if raw is None:
            # An empty file ships no rule; skip it rather than fail the pack.
            logger.warning("CEP rule file %s is empty; skipping", file)
            continue
        try:
            rule = _rule_from_mapping(raw, source=str(file))
        except RuleValidationError as err:
            # Re-raise with the pack context attached; the message already
            # names the file via `source`.
            logger.debug("CEP rule file %s rejected: %s", file, err)
            raise
        if rule.id in seen_ids:
            raise RuleValidationError(
                f"{file}: duplicate rule id '{rule.id}' (first defined in "
                f"{seen_ids[rule.id]})"
            )
        seen_ids[rule.id] = str(file)
        rules.append(rule)

    logger.info("CEP rules loaded: %d rule(s) from %s", len(rules), directory)
    return tuple(rules)

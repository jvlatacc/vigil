"""Source-agnostic normalizer from raw finding dict to NormalizedFinding.

Findings arrive at the CEP tap pre-triage: whatever the source produced, in
the shape the ingestion adapters build (see ``core/integrations/*/adapter.py``
— ``entity_context`` lists, ``mitre_predictions`` as ``{technique: confidence}``).
This module is the engine's single view of that shape.

It is deliberately lightweight and conservative: a field that is absent,
empty, or unparseable is absent on the result — never a fabricated default —
because a sequence step that matched on an invented value is worse than a
step that does not fire (spec: steps whose fields are unmet do not fire).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedFinding:
    """The engine's view of one finding.

    Every field is what the source actually said: ``None`` means "not
    present", never "known empty". ``severity`` is provisional — the
    source's claim before AI triage runs.
    """

    finding_id: Optional[str] = None
    data_source: Optional[str] = None
    severity: Optional[str] = None
    host: Optional[str] = None
    user: Optional[str] = None
    src_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    techniques: Tuple[str, ...] = ()
    timestamp: Optional[datetime] = None


def _string(value: Any, *, lower: bool = False) -> Optional[str]:
    """A clean string from a scalar: str-typed, non-empty, stripped.

    Non-string values are skipped rather than coerced — a number or dict in
    an identity field is malformed input, and str()-coercing it would invent
    an entity that no source meant.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text.lower() if lower else text


def _first_str(values: Any) -> Optional[str]:
    """The first meaningful string in a list-like (or a bare string), else None."""
    if isinstance(values, str):
        return values.strip() or None
    if isinstance(values, (list, tuple)):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _entity(
    entity_context: Mapping[str, Any],
    plural_keys: Tuple[str, ...],
    singular_keys: Tuple[str, ...],
) -> Optional[str]:
    """First entity value from the adapter shapes: plural lists first, then
    the singular spellings — exactly the variants the daemon's processor and
    the ingestion adapters read."""
    for key in (*plural_keys, *singular_keys):
        value = _first_str(entity_context.get(key))
        if value:
            return value
    return None


def _techniques(finding: Mapping[str, Any]) -> Tuple[str, ...]:
    """MITRE technique ids, order-preserving and deduplicated.

    Accepts the canonical ``{technique_id: confidence}`` dict (keys only —
    confidences belong to triage, not to sequence matching) or a list of ids;
    anything else is treated as absent.
    """
    raw = finding.get("mitre_predictions")
    if isinstance(raw, Mapping):
        candidates: Tuple[Any, ...] = tuple(raw.keys())
    elif isinstance(raw, (list, tuple)):
        candidates = tuple(raw)
    else:
        return ()

    techniques: list = []
    seen: set = set()
    for candidate in candidates:
        technique = _string(candidate)
        if technique and technique not in seen:
            seen.add(technique)
            techniques.append(technique)
    return tuple(techniques)


def _timestamp(value: Any) -> Optional[datetime]:
    """Parse a finding timestamp: datetime passes through, an ISO string
    (with or without a ``Z``) parses, anything else is absent. Unparseable
    values log at debug and return None — never a fabricated "now"."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            logger.debug("CEP normalizer: unparseable timestamp %r", value[:64])
    return None


def normalize_finding(finding: Mapping[str, Any]) -> NormalizedFinding:
    """Map a raw finding dict (the daemon queue item's ``data``) to a
    NormalizedFinding. Pure: reads the mapping, returns a value."""
    entity_context_raw = finding.get("entity_context")
    entity_context: Mapping[str, Any] = (
        entity_context_raw if isinstance(entity_context_raw, Mapping) else {}
    )

    return NormalizedFinding(
        finding_id=_string(finding.get("finding_id")),
        data_source=_string(finding.get("data_source")),
        severity=_string(finding.get("severity"), lower=True),
        host=_entity(entity_context, ("hostnames",), ("hostname", "host")),
        user=_entity(entity_context, ("usernames", "users"), ("user",)),
        src_ip=_entity(entity_context, ("src_ips",), ("src_ip",)),
        dest_ip=_entity(entity_context, ("dest_ips", "dst_ips"), ("dst_ip", "dest_ip")),
        techniques=_techniques(finding),
        timestamp=_timestamp(finding.get("timestamp")),
    )

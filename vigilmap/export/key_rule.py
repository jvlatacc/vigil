"""The entity-key rule, stated where vigilmap needs it.

THE one rule (``core/memory/entity_keys.py``): defang, then case-fold —
except ``arn`` and ``aws_key``, whose casing is significant, so folding them
would make two principals one key and the join would still return rows, just
the wrong ones. Same rule as the hunt harness TypeScript mirror; a second
normalisation rule is exactly the drift the canonical module exists to prevent.

This module must not become a second rule. When the repo checkout is
importable, the public names below defer to core; the standalone copy is kept
under ``_copy_*`` names regardless, and ``test_key_rule_drift.py`` pins the
copy to core over a fixture table — so either half drifting fails loudly.
"""

from __future__ import annotations

import re
from typing import Tuple

__all__ = [
    "ENTITY_KEY_TYPES",
    "KEY_CASE_SENSITIVE_TYPES",
    "defang",
    "entity_key",
    "normalise_key",
]

# ---------------------------------------------------------------------------
# The stated copy. Always defined, so the drift guard can exercise it even
# where core is importable. Copied from core/memory/entity_keys.py and
# core/memory/recall_contract.py; if you are editing this block, you are
# editing the rule — stop, and edit the canonical one instead.
# ---------------------------------------------------------------------------

# core/memory/recall_contract.py — the entity types a key may name, and the
# half that case-folding must not touch.
_COPY_ENTITY_KEY_TYPES: Tuple[str, ...] = (
    "ip",
    "domain",
    "host",
    "url",
    "email",
    "hash",
    "arn",
    "aws_key",
    "user",
    "process",
    "cve",
)
_COPY_KEY_CASE_SENSITIVE_TYPES: Tuple[str, ...] = ("arn", "aws_key")

# core/memory/entity_keys.py — threat intel writes addresses defanged, so
# normalising first is cheaper than carrying defanged variants of every key.
_COPY_DEFANG: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[\.\]|\(\.\)|\{\.\}"), "."),
    (re.compile(r"\bh(?:xx)p", re.IGNORECASE), "http"),
    (re.compile(r"\[:\]"), ":"),
    (re.compile(r"\[at\]", re.IGNORECASE), "@"),
)


def _copy_defang(text: str) -> str:
    for pattern, replacement in _COPY_DEFANG:
        text = pattern.sub(replacement, text)
    return text


def _copy_entity_key(entity_type: str, value: str) -> str:
    """Return ``type:value``, or ``""`` when either half is absent."""
    kind = (entity_type or "").strip().lower()
    text = _copy_defang((value or "").strip())
    if not kind or not text:
        return ""
    if kind not in _COPY_KEY_CASE_SENSITIVE_TYPES:
        text = text.lower()
    return f"{kind}:{text}"


def _copy_normalise_key(key: str) -> str:
    """Normalise a stored-form ``type:value`` key the way the writer minted it.

    Splitting on the *first* colon keeps a URL or an IPv6 address whole:
    everything after the type belongs to the value.
    """
    kind, _, value = (key or "").strip().partition(":")
    return _copy_entity_key(kind, value)


# ---------------------------------------------------------------------------
# Public surface: core when it imports, the stated copy when it does not.
# ---------------------------------------------------------------------------

try:
    # Inside the repo checkout / venv: the canonical rule, no second mint.
    from core.memory.entity_keys import defang, entity_key, normalise_key
    from core.memory.recall_contract import (
        ENTITY_KEY_TYPES,
        KEY_CASE_SENSITIVE_TYPES,
    )

except ImportError:  # standalone: the stated copy above
    defang = _copy_defang
    entity_key = _copy_entity_key
    normalise_key = _copy_normalise_key
    ENTITY_KEY_TYPES = _COPY_ENTITY_KEY_TYPES
    KEY_CASE_SENSITIVE_TYPES = _COPY_KEY_CASE_SENSITIVE_TYPES

"""The drift guard: key_rule's stated copy may never diverge from core.

Runs where the import exists (repo CI, run from the repo root), which is the
only place the comparison means anything: a standalone copy has nothing to
drift against. The core imports at module level are deliberate — a broken path
must fail loudly here, not skip silently green.
"""

import core.memory.entity_keys as canonical
import core.memory.recall_contract as contract
from vigilmap.export import key_rule

# Defang variants, case handling, whitespace, and the empty cases — the table
# the spec names: "defang variants, ARN/aws_key casing, whitespace".
KEY_FIXTURES = [
    ("domain", "evildomain[.]com"),
    ("domain", "(.)evildomain{.}com"),
    ("domain", "  EvilDomain.COM  "),
    ("domain", "sub.evil-domain.co.uk"),
    ("url", "hxxp://evildomain[.]com/payload"),
    ("url", "hxp://short.example"),
    ("email", "billing[at]vendor[.]example"),
    ("email", "  Billing@Vendor.Example  "),
    ("ip", "203.0.113.7"),
    ("ip", "::1"),
    ("host", " WS-0403 "),
    ("user", "J.Wilson"),
    ("hash", "A" * 64),
    ("cve", "CVE-2026-1234"),
    ("process", "svchost.exe"),
    # The half that breaks silently: case-significant, so folding is drift.
    ("arn", "arn:aws:iam::123456789012:role/Admin"),
    ("arn", "arn:aws:iam::123456789012:role/admin"),
    ("aws_key", "AKIAIOSFODNN7EXAMPLE"),
    ("aws_key", "akiaiosfodnn7example"),
    # Absent halves mint the empty key, dropped by callers.
    ("domain", ""),
    ("", "nothing"),
    ("", ""),
]

DEFANG_FIXTURES = [
    "evildomain[.]com",
    "evildomain(.)com",
    "evildomain{.}com",
    "hxxp://phish.example",
    "HXP://short.example",
    "[:]simple",
    "billing[at]vendor.example",
    "  spaced out  ",
    "untouched.example",
]


def test_stated_copy_matches_canonical_entity_key():
    for kind, value in KEY_FIXTURES:
        assert key_rule._copy_entity_key(kind, value) == canonical.entity_key(
            kind, value
        ), f"drift on entity_key({kind!r}, {value!r})"


def test_stated_copy_matches_canonical_defang():
    for text in DEFANG_FIXTURES:
        assert key_rule._copy_defang(text) == canonical.defang(
            text
        ), f"drift on defang({text!r})"


def test_stated_copy_matches_canonical_normalise_key():
    for kind, value in KEY_FIXTURES:
        raw = f"{kind}:{value}"
        assert key_rule._copy_normalise_key(raw) == canonical.normalise_key(
            raw
        ), f"drift on normalise_key({raw!r})"


def test_vocabulary_constants_match_the_contract():
    assert key_rule.ENTITY_KEY_TYPES == contract.ENTITY_KEY_TYPES
    assert key_rule.KEY_CASE_SENSITIVE_TYPES == contract.KEY_CASE_SENSITIVE_TYPES


def test_public_names_defer_to_core():
    # When core imports, the public surface IS the canonical mint — no wrapper,
    # no re-implementation between vigilmap and the rule.
    assert key_rule.entity_key is canonical.entity_key
    assert key_rule.defang is canonical.defang
    assert key_rule.normalise_key is canonical.normalise_key


def test_case_significant_types_are_pinned():
    # The exception is the half that breaks silently; pin the behavior itself
    # so a coordinated drift of both copies still fails here. An ARN's own
    # "arn:" scheme is part of the value half, so the minted key repeats it —
    # canonical shape is arn:arn:aws:….
    assert (
        key_rule.entity_key("arn", "arn:aws:iam::123456789012:role/Admin")
        == "arn:arn:aws:iam::123456789012:role/Admin"
    )
    assert key_rule.entity_key("domain", "Evil[.]Com") == "domain:evil.com"
    assert key_rule.entity_key(
        "arn", "arn:aws:iam::123456789012:role/Admin"
    ) != key_rule.entity_key("arn", "arn:aws:iam::123456789012:role/admin")
    assert (
        key_rule.entity_key("aws_key", "AKIAIOSFODNN7EXAMPLE")
        == "aws_key:AKIAIOSFODNN7EXAMPLE"
    )

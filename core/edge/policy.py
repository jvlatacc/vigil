"""The containment-policy pack: what a Warden node may enforce, signed.

The pack is the payload of a DSSE envelope and is parsed only after that
envelope verifies (``core/edge/verify.py``). Parsing is strict — duplicate
keys and non-standard constants refused — and fails closed on every semantic
gate: window order, expiry, lifetime, rule/envelope agreement. The version
gate at the bottom of this module is the per-node anti-replay check: a node
holding vN refuses vN-1, and re-presented vN must hash to the bytes it held.

Style follows ``core/response/config.py``: dataclasses and pure functions, no
I/O, ``now`` always injected — never read from the clock mid-decision. The
decision function that consumes a parsed pack lands with the Warden runtime;
this module only defines what is signed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from core.edge.wire import parse_ts, strict_json_loads

HERE = Path(__file__).parent
_POLICY = Draft202012Validator(json.loads((HERE / "policy.schema.json").read_text()))

POLICY_FORMAT = "vigil.edge-policy/v1"

# Containment authority ages out fast: a node partitioned forever must run out
# of enforcement authority on its own, without waiting for a revocation that
# cannot reach it. The control plane re-issues fresh packs; the envelope's
# not_after is the safety net, this is the ceiling on how long that net is.
MAX_POLICY_LIFETIME_DAYS = 7


@dataclass(frozen=True)
class ModelManifest:
    """The optional local SLM, identified by content hash — never a URL.

    Warden verifies the on-disk model file against ``sha256`` before loading
    it; a mismatched or corrupted model refuses to load and triage falls back
    to rules-only.
    """

    name: str
    sha256: str
    format: str


@dataclass(frozen=True)
class EdgeAction:
    """What a matching rule does locally. v1 ships ``block_ip`` only."""

    type: str
    ttl_minutes: int


@dataclass(frozen=True)
class EdgeRule:
    """One local match-and-act rule from the pack."""

    rule_id: str
    indicator: str
    mitre: tuple[str, ...]
    min_local_confidence: float | None
    action: EdgeAction


@dataclass(frozen=True)
class AutonomyEnvelope:
    """The hard ceiling on local enforcement, signed into the pack.

    Never configurable at the edge and never DB-overridable — the lesson from
    the unsigned, remotely flippable autonomy knobs in ``core/response``
    (``force_manual_approval``, thresholds). Every field here is a limit the
    decision engine treats as hard.
    """

    allowed_actions: tuple[str, ...]
    max_actions_per_hour: int
    max_action_ttl_minutes: int
    require_reversible: bool
    confidence_floor: float
    allow_slm_decisions: bool


@dataclass(frozen=True)
class PolicyPack:
    """A verified, parsed containment-policy pack."""

    policy_version: int
    issued_at: datetime
    not_before: datetime
    not_after: datetime
    node_selectors: tuple[str, ...]
    autonomy_envelope: AutonomyEnvelope
    protected_targets: tuple[str, ...]
    rules: tuple[EdgeRule, ...]
    model_manifest: ModelManifest | None
    # sha256 of the exact payload bytes this pack was parsed from — what the
    # version gate compares on a same-version re-presentation.
    payload_hash: str

    def version_state(self) -> VersionState:
        """The per-node watermark this pack, once accepted, installs."""
        return VersionState(self.policy_version, self.payload_hash)


@dataclass
class ParsedPolicy:
    """A parsed pack, or the rejection classes it was refused with.

    ``errors`` is a list of (class, detail); the class is what callers record
    and alert on, the detail is for the operator reading the log.
    """

    pack: PolicyPack | None = None
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.pack is not None

    @property
    def codes(self) -> set[str]:
        return {code for code, _ in self.errors}


def policy_fingerprint(payload: bytes) -> str:
    """sha256 hex of pack payload bytes — the hash the version gate compares."""
    return hashlib.sha256(payload).hexdigest()


def _semantic_checks(doc: dict[str, Any], *, now: datetime) -> list[tuple[str, str]]:
    """The gates JSON schema cannot express, each with a recorded class.

    Runs after the schema pass, so the shapes below are guaranteed.
    """
    errs: list[tuple[str, str]] = []
    issued_at = parse_ts(doc["issued_at"])
    not_before = parse_ts(doc["not_before"])
    not_after = parse_ts(doc["not_after"])
    if not issued_at <= not_before:
        errs.append(("P-WINDOW", "issued_at must not be after not_before"))
    if not not_before <= not_after:
        errs.append(("P-WINDOW", "not_before must not be after not_after"))
    if (not_after - issued_at).days > MAX_POLICY_LIFETIME_DAYS:
        errs.append(
            (
                "P-LIFETIME",
                f"policy lifetime exceeds {MAX_POLICY_LIFETIME_DAYS} days",
            )
        )
    # Clock comparisons use the caller's now, which is why it is injected:
    # expiry must be judgeable against the verifying node's own view of time.
    if not_after <= now:
        errs.append(("P-EXPIRED", f"policy expired at {doc['not_after']}"))
    elif not_before > now:
        errs.append(("P-NOT-YET-VALID", f"policy opens at {doc['not_before']}"))
    envelope = doc["autonomy_envelope"]
    allowed = set(envelope["allowed_actions"])
    seen_rule_ids: set[str] = set()
    for rule in doc["rules"]:
        rule_id = rule["rule_id"]
        if rule_id in seen_rule_ids:
            errs.append(("P-RULE-ID", f"duplicate rule_id {rule_id}"))
            continue
        seen_rule_ids.add(rule_id)
        if rule["action"]["type"] not in allowed:
            errs.append(
                (
                    "P-RULE-UNENFORCEABLE",
                    f"rule {rule_id} acts {rule['action']['type']}, "
                    "which the envelope's allowlist never allows",
                )
            )
            continue
        if rule["action"]["ttl_minutes"] > envelope["max_action_ttl_minutes"]:
            errs.append(
                (
                    "P-RULE-TTL",
                    f"rule {rule_id} ttl {rule['action']['ttl_minutes']}m exceeds "
                    f"the envelope ceiling {envelope['max_action_ttl_minutes']}m",
                )
            )
    return errs


def _pack_from(doc: dict[str, Any], *, payload_hash: str) -> PolicyPack:
    manifest = doc.get("model_manifest")
    return PolicyPack(
        policy_version=doc["policy_version"],
        issued_at=parse_ts(doc["issued_at"]),
        not_before=parse_ts(doc["not_before"]),
        not_after=parse_ts(doc["not_after"]),
        node_selectors=tuple(doc["node_selectors"]),
        autonomy_envelope=AutonomyEnvelope(
            allowed_actions=tuple(doc["autonomy_envelope"]["allowed_actions"]),
            max_actions_per_hour=doc["autonomy_envelope"]["max_actions_per_hour"],
            max_action_ttl_minutes=doc["autonomy_envelope"]["max_action_ttl_minutes"],
            require_reversible=doc["autonomy_envelope"]["require_reversible"],
            confidence_floor=doc["autonomy_envelope"]["confidence_floor"],
            allow_slm_decisions=doc["autonomy_envelope"]["allow_slm_decisions"],
        ),
        protected_targets=tuple(doc["protected_targets"]),
        rules=tuple(
            EdgeRule(
                rule_id=rule["rule_id"],
                indicator=rule["match"]["indicator"],
                mitre=tuple(rule["match"].get("mitre", [])),
                min_local_confidence=rule["match"].get("min_local_confidence"),
                action=EdgeAction(
                    type=rule["action"]["type"],
                    ttl_minutes=rule["action"]["ttl_minutes"],
                ),
            )
            for rule in doc["rules"]
        ),
        model_manifest=(
            None
            if manifest is None
            else ModelManifest(
                name=manifest["name"],
                sha256=manifest["sha256"],
                format=manifest["format"],
            )
        ),
        payload_hash=payload_hash,
    )


def parse_policy(payload: bytes, *, now: datetime) -> ParsedPolicy:
    """Parse verified policy bytes — call only after the envelope verified.

    Fails closed: the returned ``ParsedPolicy`` either carries a pack, or the
    rejection classes that refused it. Nothing here trusts the input.
    """
    try:
        doc = strict_json_loads(payload)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return ParsedPolicy(errors=[("P-JSON", str(exc)[:120])])
    if not isinstance(doc, dict):
        return ParsedPolicy(
            errors=[("P-SCHEMA", "policy payload must be a JSON object")]
        )
    errors = list(_POLICY.iter_errors(doc))
    if errors:
        return ParsedPolicy(errors=[("P-SCHEMA", errors[0].message[:150])])
    errors = _semantic_checks(doc, now=now)
    if errors:
        return ParsedPolicy(errors=errors)
    return ParsedPolicy(pack=_pack_from(doc, payload_hash=policy_fingerprint(payload)))


@dataclass(frozen=True)
class VersionState:
    """The per-node version watermark: the highest accepted policy version and
    the exact payload hash it was accepted from (what ``PolicySync`` persists)."""

    version: int
    payload_hash: str

    @classmethod
    def from_pack(cls, pack: PolicyPack) -> VersionState:
        return cls(pack.policy_version, pack.payload_hash)


@dataclass
class VersionCheck:
    """The version gate's outcome: refuse, advance, or an exact resync.

    ``same_pack`` marks the byte-identical re-presentation of the stored
    version — a resync, not an update; a caller re-storing it is a no-op.
    """

    errors: list[tuple[str, str]] = field(default_factory=list)
    same_pack: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def codes(self) -> set[str]:
        return {code for code, _ in self.errors}


def check_policy_version(
    state: VersionState | None, candidate: VersionState
) -> VersionCheck:
    """Monotonic per-node version gate — the anti-replay check for packs.

    First pack on a node: accepted. A strictly newer version: accepted. The
    stored version re-presented byte-identical: accepted as ``same_pack``.
    Anything else refuses with a class: an older version is a replay of
    expired authority (a downgrade attack), and the same version with
    different bytes is either tampering or a signing fork — indistinguishable
    from the malicious case, so both refuse.
    """
    if state is None:
        return VersionCheck()
    if candidate.version < state.version:
        return VersionCheck(
            errors=[
                (
                    "P-VERSION-REPLAY",
                    f"v{candidate.version} is older than the stored v{state.version}",
                )
            ]
        )
    if candidate.version == state.version:
        if candidate.payload_hash == state.payload_hash:
            return VersionCheck(same_pack=True)
        return VersionCheck(
            errors=[
                (
                    "P-VERSION-FORK",
                    f"v{candidate.version} re-presented with different bytes "
                    f"(stored {state.payload_hash[:12]}, got {candidate.payload_hash[:12]})",
                )
            ]
        )
    return VersionCheck()


def load_policy_pack(
    data: bytes,
    root: dict,
    *,
    now: datetime,
    state: VersionState | None = None,
) -> ParsedPolicy:
    """The one-call path a policy sync uses: verify, parse, then version-gate.

    Envelope verification (``verify.verify_envelope``) runs on the raw bytes —
    a tampered, forged, or wrong-typed pack is refused before its payload is
    parsed — then the payload goes through ``parse_policy`` and, when the node
    already holds a pack, ``check_policy_version``. A refusal anywhere is a
    ``ParsedPolicy`` with rejection classes; the safe path and the refusing
    path are the same function, so a caller cannot skip a gate by accident.
    """
    from core.edge import EDGE_POLICY
    from core.edge.verify import verify_envelope

    verified = verify_envelope(data, root, expected={EDGE_POLICY}, now=now)
    if not verified.ok:
        return ParsedPolicy(errors=verified.errors)
    if verified.payload is None:  # pragma: no cover - verify_envelope guarantees this
        return ParsedPolicy(errors=[("S-INTERNAL", "verified payload missing")])
    parsed = parse_policy(verified.payload, now=now)
    if not parsed.ok or parsed.pack is None:
        return parsed
    version = check_policy_version(state, parsed.pack.version_state())
    if not version.ok:
        return ParsedPolicy(errors=version.errors)
    return parsed

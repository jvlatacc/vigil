"""Bundle-cache suite: atomic activation, prior-bundle retention, persisted
state re-verified at boot, tamper demotion, and the Tier-0 floor."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.edge.gate.tiers import AutonomyTier
from services.edge.policy.cache import BundleCache
from services.edge.policy.envelope import parse_trust_root
from services.edge.tests._fixtures import (
    EdgeSigner,
    bundle_payload,
    sign_envelope,
    trust_root_for,
)

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
LABELS = {"vigil.ai/edge-role": "gateway"}


@pytest.fixture()
def signer() -> EdgeSigner:
    return EdgeSigner()


@pytest.fixture()
def trust(signer: EdgeSigner):
    return parse_trust_root(trust_root_for(signer))


@pytest.fixture()
def cache(tmp_path: Path, trust) -> BundleCache:
    return BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")


def _envelope(signer: EdgeSigner, version: int):
    return sign_envelope(bundle_payload(version=version), signer)


def test_first_activation(cache: BundleCache, signer: EdgeSigner) -> None:
    result = cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    assert result.accepted
    assert cache.current is not None
    assert cache.current.version == 7
    assert cache.previous is None
    assert cache.effective_tier(NOW) == AutonomyTier.TIER_2


def test_upgrade_retains_previous(cache: BundleCache, signer: EdgeSigner) -> None:
    cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    cache.verify_and_activate(_envelope(signer, 8), now=NOW)
    assert cache.current is not None and cache.current.version == 8
    assert cache.previous is not None and cache.previous.version == 7


def test_refused_candidate_keeps_current(
    cache: BundleCache, signer: EdgeSigner
) -> None:
    cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    stranger = EdgeSigner(keyid="stranger")
    stranger_envelope = sign_envelope(bundle_payload(version=9), stranger)
    result = cache.verify_and_activate(stranger_envelope, now=NOW)
    assert not result.accepted
    assert result.code == "E-UNKNOWN-SIGNER"
    assert cache.current is not None and cache.current.version == 7


def test_expired_current_is_tier0_never_extended(
    cache: BundleCache, signer: EdgeSigner
) -> None:
    cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    later = datetime(2026, 10, 20, tzinfo=UTC)  # past expires_at 2026-10-16
    assert cache.effective_tier(later) == AutonomyTier.TIER_0
    # The bundle object is still the last-known-good one — only authority dropped.
    assert cache.current is not None


def test_persisted_state_roundtrip(tmp_path: Path, signer: EdgeSigner, trust) -> None:
    first = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    first.verify_and_activate(_envelope(signer, 7), now=NOW)
    first.verify_and_activate(_envelope(signer, 8), now=NOW)

    second = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    state = second.load_persisted(now=NOW)
    assert state.current is not None and state.current.version == 8
    assert state.previous is not None and state.previous.version == 7
    assert second.effective_tier(NOW) == AutonomyTier.TIER_2


def test_boot_falls_back_when_current_tampered(
    tmp_path: Path, signer: EdgeSigner, trust
) -> None:
    first = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    first.verify_and_activate(_envelope(signer, 7), now=NOW)
    first.verify_and_activate(_envelope(signer, 8), now=NOW)
    state = json.loads((tmp_path / "state.json").read_text())
    current_path = Path(state["current"]["path"])
    envelope = json.loads(current_path.read_text())
    raw = base64.b64decode(envelope["payload"])
    envelope["payload"] = base64.b64encode(bytes([raw[0] ^ 0x01]) + raw[1:]).decode()
    current_path.write_text(json.dumps(envelope))

    second = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    loaded = second.load_persisted(now=NOW)
    assert loaded.current is not None and loaded.current.version == 7
    assert loaded.previous is None


def test_boot_tier0_when_everything_untrusted(
    tmp_path: Path, signer: EdgeSigner, trust
) -> None:
    first = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    first.verify_and_activate(_envelope(signer, 7), now=NOW)

    # A rotated trust store no longer names the signer: boot must demote.
    stranger = EdgeSigner(keyid="new-key")
    rotated = parse_trust_root(trust_root_for(stranger))
    second = BundleCache(tmp_path, rotated, node_labels=LABELS, edge_version="1.0.0")
    state = second.load_persisted(now=NOW)
    assert state.current is None
    assert second.effective_tier(NOW) == AutonomyTier.TIER_0


def test_boot_without_state_is_tier0(tmp_path: Path, trust) -> None:
    cache = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    state = cache.load_persisted(now=NOW)
    assert state.current is None and state.previous is None
    assert cache.effective_tier(NOW) == AutonomyTier.TIER_0


def test_activation_persists_envelope_atomically(
    tmp_path: Path, signer: EdgeSigner, trust
) -> None:
    cache = BundleCache(tmp_path, trust, node_labels=LABELS, edge_version="1.0.0")
    cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    bundles = list((tmp_path / "bundles").glob("*.json"))
    assert len(bundles) == 1
    assert not list((tmp_path / "bundles").glob("*.tmp"))
    on_disk = json.loads(bundles[0].read_text())
    assert on_disk["payloadType"].endswith("bundle.v1+json")


def test_cache_rejects_scope_mismatch_at_activation(
    tmp_path: Path, signer: EdgeSigner, trust
) -> None:
    cache = BundleCache(
        tmp_path,
        trust,
        node_labels={"vigil.ai/edge-role": "worker"},
        edge_version="1.0.0",
    )
    result = cache.verify_and_activate(_envelope(signer, 7), now=NOW)
    assert not result.accepted
    assert result.code == "E-SCOPE"
    assert cache.current is None

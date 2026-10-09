"""Defense-loop suite: observation -> gate -> journal -> executor. Tier 0
journals only; a missing executor is recorded, never faked; caps exhausted
holds; state transitions are journaled. Async scenarios run under
``asyncio.run`` — the edge package carries no pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from services.edge.app.config import EdgeConfig
from services.edge.app.daemon import EdgeDaemon
from services.edge.app.states import OperatingState
from services.edge.executors.registry import ActionResult, BundleBound
from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_STATE,
)
from services.edge.tests._fixtures import (
    EdgeSigner,
    bundle_payload,
    make_observation,
    sign_envelope,
    trust_root_for,
)

LABELS = {"vigil.ai/edge-role": "gateway"}
NOW = datetime.now(UTC)


class FakeExecutor:
    name = "nftables"
    action_types = frozenset({"block_ip", "block_domain"})

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.applied: list[tuple[Any, int]] = []

    async def apply(
        self, action: Any, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        self.applied.append((action, ttl_seconds))
        if self.fail:
            return ActionResult(success=False, error="boom")
        return ActionResult(success=True, ref="vigil/edge/test")

    async def revert(self, ref: str) -> ActionResult:
        return ActionResult(success=True, ref=ref)


def make_daemon(tmp_path: Path, signer: EdgeSigner) -> EdgeDaemon:
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps(trust_root_for(signer)))
    config = EdgeConfig(
        node_id="gw-test",
        data_dir=tmp_path / "data",
        trust_store=trust_file,
        model=None,  # deterministic gate only — the advisor has its own suite
        node_labels=LABELS,
        journal_max_bytes=1 << 20,
    )
    daemon = EdgeDaemon(config)
    daemon._init_components()
    return daemon


def test_gateway_mode_wires_nftables_bundle_bound(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    daemon = make_daemon(tmp_path, signer)
    executor = daemon._executors.lookup("block_ip", "nftables")
    assert executor is not None
    assert isinstance(executor, BundleBound)
    # Only the mode's executor is registered: a k8s pair on a gateway has
    # no executor and must fall to the recorded-failure path.
    assert daemon._executors.lookup("block_ip", "k8s_networkpolicy") is None


def test_cluster_mode_wires_the_networkpolicy_executor_bundle_bound(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps(trust_root_for(signer)))
    config = EdgeConfig(
        node_id="node-test",
        mode="cluster",
        k8s_api_url="https://kubernetes.default.svc",
        data_dir=tmp_path / "data",
        trust_store=trust_file,
        model=None,
        node_labels=LABELS,
        journal_max_bytes=1 << 20,
    )
    daemon = EdgeDaemon(config)
    daemon._init_components()
    executor = daemon._executors.lookup("block_ip", "k8s_networkpolicy")
    assert executor is not None
    assert isinstance(executor, BundleBound)
    assert daemon._executors.lookup("block_ip", "nftables") is None


def activate(
    daemon: EdgeDaemon, signer: EdgeSigner, version: int = 7, **payload_overrides: Any
) -> None:
    """v7 stays valid until 2099-12-31 (execute tests run at real now); v8
    expires 2099-01-01 so the tier-0 test can pin a deterministic future
    clock regardless of the wall-clock date."""
    expires = "2099-12-31T00:00:00Z" if version == 7 else "2099-01-01T00:00:00Z"
    payload = bundle_payload(
        version=version,
        not_before="2020-01-01T00:00:00Z",
        expires_at=expires,
        **payload_overrides,
    )
    result = daemon._cache.verify_and_activate(sign_envelope(payload, signer), now=NOW)
    assert result.accepted, result.code


def test_no_bundle_journals_observation_only(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        await daemon.handle_observation(make_observation())
        records = daemon._journal.unacked()
        assert [r.kind for r in records] == [KIND_OBSERVATION]
        assert records[0].payload["reason"] == "no_bundle"

    asyncio.run(scenario())


def test_matching_observation_executes_and_journals(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        await daemon.handle_observation(make_observation())
        assert len(executor.applied) == 1
        action, ttl = executor.applied[0]
        assert action.action_type == "block_ip"
        assert action.target == "203.0.113.55"
        assert ttl == 900  # the bundle's default_block_ttl_seconds
        records = daemon._journal.unacked()
        assert [r.kind for r in records] == [KIND_DECISION]
        payload = records[0].payload
        assert payload["outcome"] == "execute"
        assert payload["execution"]["success"] is True
        assert payload["execution"]["ref"] == "vigil/edge/test"
        assert payload["rule_string"].startswith("edge.c2-egress-active")
        assert payload["actor"] == "edge:gw-test@v7"

    asyncio.run(scenario())


def test_failed_apply_is_journaled_and_consumes_no_cap(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        daemon._executors.register(FakeExecutor(fail=True))
        activate(daemon, signer)
        await daemon.handle_observation(make_observation())
        payload = daemon._journal.unacked()[-1].payload
        assert payload["outcome"] == "execute"
        assert payload["execution"]["success"] is False
        assert payload["execution"]["error"] == "boom"
        now = datetime.now(UTC)
        assert daemon._journal.executed_in_last_hour("block_ip", now) == 0
        assert daemon._journal.active_blocks(now) == 0

    asyncio.run(scenario())


def test_missing_executor_is_recorded_never_faked(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        # A bundle may name an executor this node does not have — a
        # cluster-mode bundle read on a gateway. The gateway daemon wires
        # only nftables, so the k8s pair must fail safe: recorded, never
        # faked, never silently dropped.
        activate(
            daemon,
            signer,
            allowed_actions=[
                {
                    "action_type": "block_ip",
                    "executor": "k8s_networkpolicy",
                    "params": {"namespaces": ["prod", "staging"]},
                }
            ],
        )
        await daemon.handle_observation(make_observation())
        records = daemon._journal.unacked()
        assert [r.kind for r in records] == [KIND_EXECUTE_FAILED]
        assert records[0].payload["reason"] == "no_executor_registered"
        assert records[0].payload["executor"] == "k8s_networkpolicy"
        assert records[0].payload["target"] == "203.0.113.55"
        assert records[0].payload["actor"] == "edge:gw-test@v7"

    asyncio.run(scenario())


def test_caps_exhausted_holds(tmp_path: Path, signer: EdgeSigner) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        payload = bundle_payload(
            version=7,
            not_before="2020-01-01T00:00:00Z",
            expires_at="2099-12-31T00:00:00Z",
        )
        payload["decision"] = {**payload["decision"], "max_actions_per_hour": 1}
        result = daemon._cache.verify_and_activate(
            sign_envelope(payload, signer), now=NOW
        )
        assert result.accepted, result.code
        await daemon.handle_observation(make_observation())
        await daemon.handle_observation(make_observation(dest_ip="203.0.113.56"))
        assert len(executor.applied) == 1
        payload = daemon._journal.unacked()[-1].payload
        assert payload["outcome"] == "hold"
        assert payload["reason"] == "cap_exhausted"

    asyncio.run(scenario())


def test_expired_bundle_is_tier0_journal_only(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer, version=8)  # expires 2099-01-01
        await daemon.handle_observation(
            make_observation(), now=datetime(2099, 1, 2, tzinfo=UTC)
        )
        assert executor.applied == []
        payload = daemon._journal.unacked()[-1].payload
        assert payload["outcome"] == "journal_only"
        assert payload["reason"] == "tier0"
        assert "tier=tier0" in payload["rule_string"]

    asyncio.run(scenario())


def test_no_rule_match_journals_only(tmp_path: Path, signer: EdgeSigner) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        await daemon.handle_observation(make_observation(dest_ip="8.8.8.8"))
        assert executor.applied == []
        payload = daemon._journal.unacked()[-1].payload
        assert payload["outcome"] == "journal_only"
        assert payload["reason"] == "no_rule_match"

    asyncio.run(scenario())


def test_state_transition_is_journaled(tmp_path: Path, signer: EdgeSigner) -> None:
    daemon = make_daemon(tmp_path, signer)
    daemon._record_state(OperatingState.RECONCILING, reason="link-restored")
    records = daemon._journal.unacked()
    assert [r.kind for r in records] == [KIND_STATE]
    assert records[0].payload["from"] == OperatingState.PARTITIONED.value
    assert records[0].payload["to"] == OperatingState.RECONCILING.value
    assert records[0].payload["reason"] == "link-restored"


def test_same_state_is_not_rejournaled(tmp_path: Path, signer: EdgeSigner) -> None:
    daemon = make_daemon(tmp_path, signer)
    daemon._record_state(OperatingState.PARTITIONED, reason="boot")
    assert daemon._journal.unacked() == []


@pytest.fixture()
def signer() -> EdgeSigner:
    return EdgeSigner()

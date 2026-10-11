"""The guard chain: ordered invariant, breaker, origin, quota (#944, D1).

Three layers, mirroring the repo's gate-test style:

1. The chain itself, with stub stores — the order of the checks, the
   rationale each outcome renders (#917 convention), which rejections feed
   the breaker, and that a rejection always forces the human path.
2. The sync bridge — a caller without an event loop gets the same verdict,
   bounded in time, and any failure of the chain answers GUARDS_UNAVAILABLE
   (fail closed), never "allow".
3. Origin trust as the chain reads it — verified at ingest, scoped for
   auto-response, and a stamp from an origin the index does not know cannot
   vouch.

The chain's stores are stubs here; the stores' own behaviour is their
slices' tests. The invariant's read seam is pointed at rules without a
database, the way ``test_guards_protected_assets`` does it.
"""

import asyncio
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from core.response import guards as guards_module
from core.response import protected_assets
from core.response.breaker import CLOSED, OPEN, BreakerStatus, open_state_rule
from core.response.config import decision_rule
from core.response.guards import (
    AUTO_RESPONSE_SCOPE,
    FindingOriginStatus,
    GuardChain,
    GuardState,
    evaluate_guards,
    evaluate_guards_sync,
    origin_statuses_for,
)
from core.response.guards_config import GuardConfig, GuardConfigError
from core.response.protected_assets import (
    ProtectedRule,
    invalidate_cache,
)
from core.response.quotas import QuotaState

pytestmark = pytest.mark.unit

DNS = ProtectedRule.validated(
    match_kind="ip",
    match_value="10.0.0.53",
    asset_class="dns",
    label="prod-dns-1",
)


@pytest.fixture(autouse=True)
def cold_cache():
    """Every test starts and ends with an empty protected-asset cache."""
    invalidate_cache()
    yield
    invalidate_cache()


def _index(monkeypatch, *rules):
    """Point the cache's read seam at rules without a database."""
    monkeypatch.setattr(
        protected_assets, "_read_active_rules", lambda *a, **k: tuple(rules)
    )


def _b64_public_key() -> str:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(public).decode()


def _config(**overrides) -> GuardConfig:
    return GuardConfig(**overrides)


class _StubBreaker:
    """The breaker as the chain sees it: scripted answers, recorded notes."""

    def __init__(self, answer=None, trip_rule=None):
        self.answer = answer or BreakerStatus(state=CLOSED)
        self.trip_rule = trip_rule
        self.invariant_notes = 0
        self.origin_notes = 0
        self.quota_trips = []
        self.state_reads = 0

    async def status(self):
        self.state_reads += 1
        return self.answer

    async def note_invariant_block(self):
        self.invariant_notes += 1
        return self.trip_rule

    async def note_origin_unverified(self):
        self.origin_notes += 1
        return self.trip_rule

    async def trip_on_quota(self, signal):
        self.quota_trips.append(signal)

    async def claim_escalation(self):
        return True


class _StubQuota:
    """The quota as the chain sees it: one scripted verdict, recorded calls."""

    def __init__(self, state=QuotaState.OK):
        self.state = state
        self.rule = {
            QuotaState.OK: decision_rule("response.quota_ok", True),
            QuotaState.SOFT_EXCEEDED: decision_rule(
                "response.quota_soft_exceeded", "global per-minute 30/30"
            ),
            QuotaState.HARD_EXCEEDED: decision_rule(
                "response.quota_hard_ceiling", "global per-hour 200/200"
            ),
        }[state]
        self.breaker_trip_reason = (
            "quota hard ceiling: global per-hour 200/200"
            if state is QuotaState.HARD_EXCEEDED
            else None
        )
        self.recorded = []
        self.checked = []

    async def record_and_check(self, action_type, ip, config):
        self.recorded.append((action_type, ip))
        return self

    async def check_only(self, action_type, ip, config):
        self.checked.append((action_type, ip))
        return self


async def _evaluate(
    monkeypatch,
    breaker=None,
    quota=None,
    *,
    action_type="isolate_host",
    ip="203.0.113.7",
    hostname=None,
    origins=(),
    rules=(),
    config=None,
    **kwargs,
):
    _index(monkeypatch, *rules)
    return await evaluate_guards(
        action_type,
        ip,
        hostname,
        origins,
        config or _config(),
        breaker or _StubBreaker(),
        quota or _StubQuota(),
        **kwargs,
    )


# --- 1. The chain ------------------------------------------------------------


class TestTheChain:
    async def test_an_allowed_action_renders_the_pass_rule(self, monkeypatch):
        breaker, quota = _StubBreaker(), _StubQuota()

        verdict = await _evaluate(monkeypatch, breaker, quota)

        assert verdict.state is GuardState.ALLOWED
        assert verdict.needs_human is False
        assert verdict.rule == "response.guards_passed=True"
        assert quota.recorded == [("isolate_host", "203.0.113.7")]

    async def test_a_protected_target_holds_before_the_breaker_is_read(
        self, monkeypatch
    ):
        breaker, quota = _StubBreaker(), _StubQuota()

        verdict = await _evaluate(
            monkeypatch, breaker, quota, ip="10.0.0.53", rules=(DNS,)
        )

        assert verdict.state is GuardState.PROTECTED_ASSET
        assert verdict.needs_human is True
        assert "response.protected_asset" in verdict.rule
        assert "10.0.0.53" in verdict.rule and "dns" in verdict.rule
        # Cheapest-and-most-specific first: the invariant answered, and the
        # shared state was never consulted.
        assert breaker.state_reads == 0
        assert quota.recorded == []
        # The hold feeds the probe counter (D4b) — someone may be probing.
        assert breaker.invariant_notes == 1

    async def test_an_invariant_probe_that_trips_the_breaker_announces_it(
        self, monkeypatch
    ):
        trip = decision_rule("response.breaker_trip", "invariant probe storm")
        breaker = _StubBreaker(trip_rule=trip)

        verdict = await _evaluate(
            monkeypatch, breaker, _StubQuota(), ip="10.0.0.53", rules=(DNS,)
        )

        assert verdict.state is GuardState.PROTECTED_ASSET
        assert verdict.tripped is True

    async def test_an_open_breaker_holds_before_the_origin_or_quota_gates(
        self, monkeypatch
    ):
        breaker = _StubBreaker(
            answer=BreakerStatus(state=OPEN, seconds_left=741, reason="quota")
        )
        quota = _StubQuota()

        verdict = await _evaluate(
            monkeypatch,
            breaker,
            quota,
            origins=(FindingOriginStatus("f-1", origin_verified=False),),
        )

        assert verdict.state is GuardState.BREAKER_OPEN
        assert verdict.needs_human is True
        assert verdict.rule == open_state_rule(741)
        assert quota.recorded == []
        # While OPEN the gate suspends everything — the unverified evidence
        # is not counted again (the flood counter already did its job).
        assert breaker.origin_notes == 0

    async def test_unverified_evidence_holds_and_feeds_the_flood_counter(
        self, monkeypatch
    ):
        breaker = _StubBreaker()

        verdict = await _evaluate(
            monkeypatch,
            breaker,
            _StubQuota(),
            origins=(FindingOriginStatus("f-1", origin_verified=False),),
        )

        assert verdict.state is GuardState.ORIGIN_UNVERIFIED
        assert verdict.needs_human is True
        assert verdict.rule == "response.origin_unverified=1"
        assert breaker.origin_notes == 1

    async def test_soft_quota_exceeded_holds_for_a_person_without_tripping(
        self, monkeypatch
    ):
        breaker, quota = _StubBreaker(), _StubQuota(QuotaState.SOFT_EXCEEDED)

        verdict = await _evaluate(monkeypatch, breaker, quota)

        assert verdict.state is GuardState.QUOTA_SOFT
        assert verdict.needs_human is True
        assert "response.quota_soft_exceeded" in verdict.rule
        assert breaker.quota_trips == []

    async def test_hard_quota_exceeded_trips_the_breaker(self, monkeypatch):
        breaker, quota = _StubBreaker(), _StubQuota(QuotaState.HARD_EXCEEDED)

        verdict = await _evaluate(monkeypatch, breaker, quota)

        assert verdict.state is GuardState.QUOTA_HARD
        assert verdict.needs_human is True
        assert "response.quota_hard_ceiling" in verdict.rule
        assert verdict.tripped is True
        assert len(breaker.quota_trips) == 1

    async def test_judging_without_spending_never_touches_the_counters(
        self, monkeypatch
    ):
        breaker, quota = _StubBreaker(), _StubQuota()

        verdict = await _evaluate(monkeypatch, breaker, quota, spend_quota=False)

        assert verdict.state is GuardState.ALLOWED
        assert quota.checked == [("isolate_host", "203.0.113.7")]
        assert quota.recorded == []

    async def test_the_order_is_invariant_then_breaker_then_origin_then_quota(
        self, monkeypatch
    ):
        # Everything wrong at once: the invariant is the gate that answers.
        breaker = _StubBreaker(answer=BreakerStatus(state=OPEN, seconds_left=900))
        quota = _StubQuota(QuotaState.HARD_EXCEEDED)

        verdict = await _evaluate(
            monkeypatch,
            breaker,
            quota,
            ip="10.0.0.53",
            rules=(DNS,),
            origins=(FindingOriginStatus("f-1", origin_verified=False),),
        )

        assert verdict.state is GuardState.PROTECTED_ASSET
        assert quota.recorded == []


# --- 2. The sync bridge -------------------------------------------------------


class TestSyncBridge:
    def test_a_caller_without_a_loop_gets_the_same_verdict(self, monkeypatch):
        _index(monkeypatch, DNS)

        verdict = evaluate_guards_sync(
            _config(),
            _StubBreaker(),
            _StubQuota(),
            "isolate_host",
            "203.0.113.7",
            None,
            (),
        )

        assert verdict.state is GuardState.ALLOWED
        assert verdict.needs_human is False

    def test_a_failure_inside_the_chain_fails_closed(self, monkeypatch):
        _index(monkeypatch)

        class _BrokenQuota(_StubQuota):
            async def record_and_check(self, action_type, ip, config):
                raise RuntimeError("redis exploded")

        verdict = evaluate_guards_sync(
            _config(),
            _StubBreaker(),
            _BrokenQuota(),
            "isolate_host",
            "203.0.113.7",
            None,
            (),
        )

        assert verdict.state is GuardState.GUARDS_UNAVAILABLE
        assert verdict.needs_human is True
        assert "response.guards_error" in verdict.rule
        assert "redis exploded" in verdict.rule

    def test_a_chain_that_cannot_finish_in_time_fails_closed(self, monkeypatch):
        _index(monkeypatch)

        class _HangingBreaker(_StubBreaker):
            async def status(self):
                await asyncio.sleep(60)
                return self.answer

        monkeypatch.setattr(guards_module, "GUARD_EVALUATION_TIMEOUT_SECONDS", 0.05)

        verdict = evaluate_guards_sync(
            _config(),
            _HangingBreaker(),
            _StubQuota(),
            "isolate_host",
            "203.0.113.7",
            None,
            (),
        )

        assert verdict.state is GuardState.GUARDS_UNAVAILABLE
        assert verdict.needs_human is True


# --- 3. GuardChain's own fail-closed contract --------------------------------


class TestGuardChain:
    def test_an_unbuildable_config_suspends_machine_speed(self, monkeypatch):
        def _raise():
            raise GuardConfigError("response.subnet_scope_prefix=0: expected 1-32")

        monkeypatch.setattr(guards_module.GuardConfig, "from_settings", _raise)
        chain = GuardChain()

        verdict = chain.evaluate_sync("isolate_host", "203.0.113.7", None, ())

        assert chain.available is False
        assert verdict.state is GuardState.GUARDS_UNAVAILABLE
        assert verdict.needs_human is True
        assert "response.guards_config" in verdict.rule

    def test_the_real_chain_fails_closed_without_its_stores(self, monkeypatch):
        # No database, no Redis: the invariant cannot be verified and the
        # breaker answers OPEN on a degraded read — the action waits for a
        # person either way. (No rules patched: the read seam raises.)
        chain = GuardChain()

        verdict = chain.evaluate_sync("isolate_host", "203.0.113.7", None, ())

        assert verdict.needs_human is True


# --- 4. Origin stamps as the chain reads them ---------------------------------


class TestOriginStamps:
    def test_a_finding_dict_reads_as_its_stamps(self):
        stamped = origin_statuses_for(
            {
                "finding_id": "f-1",
                "origin_verified": True,
                "origin_id": "sensor-edge-01",
            }
        )
        stampless = origin_statuses_for({"finding_id": "f-2"})

        assert stamped == (
            FindingOriginStatus(
                "f-1", origin_verified=True, origin_id="sensor-edge-01"
            ),
        )
        assert stampless == (FindingOriginStatus("f-2", origin_verified=False),)

    async def test_verified_evidence_from_a_registered_scoped_origin_passes(
        self, monkeypatch
    ):
        config = _config(
            trusted_origins=(
                {
                    "origin_id": "sensor-edge-01",
                    "public_key": _b64_public_key(),
                    "scope": AUTO_RESPONSE_SCOPE,
                    "enabled": True,
                },
            )
        )

        verdict = await _evaluate(
            monkeypatch,
            origins=(
                FindingOriginStatus(
                    "f-1", origin_verified=True, origin_id="sensor-edge-01"
                ),
            ),
            config=config,
        )

        assert verdict.state is GuardState.ALLOWED

    async def test_an_origin_scoped_away_from_auto_response_does_not_vouch(
        self, monkeypatch
    ):
        config = _config(
            trusted_origins=(
                {
                    "origin_id": "sensor-edge-01",
                    "public_key": _b64_public_key(),
                    "scope": "edge-ingest-only",
                    "enabled": True,
                },
            )
        )

        verdict = await _evaluate(
            monkeypatch,
            origins=(
                FindingOriginStatus(
                    "f-1", origin_verified=True, origin_id="sensor-edge-01"
                ),
            ),
            config=config,
        )

        assert verdict.state is GuardState.ORIGIN_UNVERIFIED

    async def test_a_stamp_from_an_unknown_origin_cannot_vouch(self, monkeypatch):
        # The origin was disabled and pruned after the stamp was made: the
        # index does not know it, so it reads as unverified — not as trusted.
        verdict = await _evaluate(
            monkeypatch,
            origins=(
                FindingOriginStatus(
                    "f-1", origin_verified=True, origin_id="removed-origin"
                ),
            ),
            config=_config(),
        )

        assert verdict.state is GuardState.ORIGIN_UNVERIFIED

    async def test_no_stamps_at_all_passes_the_origin_gate_vacuously(self, monkeypatch):
        # Direct service callers that predate the stamps: the gate judges
        # zero statuses. The daemon pipeline always supplies them.
        verdict = await _evaluate(monkeypatch)

        assert verdict.state is GuardState.ALLOWED

"""SLM triage tests: the four modes and the failure paths.

The acceptance criteria from the work item, each a test: dependency
absent → rules-only; stubbed-good model → ranking used and surfaced;
corrupted model file (sha256 mismatch) → refuses load, falls back
rules-only; envelope ``allow_slm_decisions=false`` → SLM output advisory
only, reflected in the journal's ``decision_rule``. No test loads a real
GGUF or touches a network: the model is a stub behind the loader seam,
and the dependency-absent path is forced hermetically by poisoning
``sys.modules``.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import respx

from core.edge.decision import (
    BELOW_CONFIDENCE_FLOOR,
    LocalTriage,
    decide_local_action,
)
from core.edge.envelope import budget_for
from core.edge.policy import (
    AutonomyEnvelope,
    EdgeAction,
    EdgeRule,
    ModelManifest,
    PolicyPack,
)
from core.edge.target_guard import TargetGuard
from services.warden.engine import match_alerts
from services.warden.triage import (
    DEPENDENCY_MISSING,
    FILE_MISSING,
    FORMAT_UNSUPPORTED,
    HASH_MISMATCH,
    LOAD_FAILED,
    NO_MANIFEST,
    NO_MODEL_PATH,
    READY,
    UNLOADED,
    FoldedTriage,
    LocalSlm,
    SlmDependencyMissing,
    SlmOpinion,
    _parse_confidence,
    fold_triage,
    render_decision_rule,
)
from tests.unit.warden.helpers import WARDEN_NOW
from tests.unit.warden.test_engine import (
    GOOD_ALERT,
    drive_to_autonomous,
    journal_records,
    make_loop,
)

MODEL_BYTES = b"fake-gguf-weights-for-tests"
MODEL_SHA256 = hashlib.sha256(MODEL_BYTES).hexdigest()
SENSOR_CONFIDENCE = 0.93
SLM_ANSWER = "0.97"


class StubModel:
    """A stubbed-good SLM: every prompt gets the same fixed answer."""

    def __init__(self, answer: str = SLM_ANSWER) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


class ExplodingModel:
    """A model that loads but fails the moment it is asked."""

    def complete(self, prompt: str) -> str:
        raise RuntimeError("inference blew up")


# ---------------------------------------------------------------------------
# Fixture builders — packs constructed directly (pure dataclasses)
# ---------------------------------------------------------------------------


def default_envelope(**overrides: Any) -> AutonomyEnvelope:
    fields: dict[str, Any] = dict(
        allowed_actions=("block_ip",),
        max_actions_per_hour=5,
        max_action_ttl_minutes=30,
        require_reversible=True,
        confidence_floor=0.90,
        allow_slm_decisions=False,
    )
    fields.update(overrides)
    return AutonomyEnvelope(**fields)


def default_rule() -> EdgeRule:
    return EdgeRule(
        rule_id="edge-001",
        indicator="ip",
        mitre=("T1071",),
        min_local_confidence=0.85,
        action=EdgeAction(type="block_ip", ttl_minutes=30),
    )


def make_pack(
    *,
    policy_version: int = 42,
    envelope: AutonomyEnvelope | None = None,
    manifest: ModelManifest | None = None,
) -> PolicyPack:
    return PolicyPack(
        policy_version=policy_version,
        issued_at=WARDEN_NOW,
        not_before=WARDEN_NOW,
        not_after=WARDEN_NOW + timedelta(days=1),
        node_selectors=("segment:dmz",),
        autonomy_envelope=envelope or default_envelope(),
        protected_targets=("self", "gateway", "control_plane", "dns_resolvers"),
        rules=(default_rule(),),
        model_manifest=manifest,
        payload_hash="0" * 64,
    )


def write_model_file(tmp_path: Path, content: bytes = MODEL_BYTES) -> Path:
    path = tmp_path / "security-slm-1b-q4.gguf"
    path.write_bytes(content)
    return path


def manifest_for(path: Path, *, fmt: str = "gguf") -> ModelManifest:
    return ModelManifest(
        name="security-slm-1b-q4",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        format=fmt,
    )


def ready_slm(tmp_path: Path, model: StubModel | ExplodingModel) -> LocalSlm:
    """A channel whose file verifies against its manifest and loads a stub."""
    path = write_model_file(tmp_path)
    slm = LocalSlm(path, loader=lambda _path: model)
    assert slm.reload_for_pack(make_pack(manifest=manifest_for(path))) == READY
    return slm


def pack_overrides_with_file_model() -> dict[str, Any]:
    """A ``model`` override whose manifest matches the on-disk fixture."""
    return {
        "model": {
            "name": "security-slm-1b-q4",
            "sha256": MODEL_SHA256,
            "format": "gguf",
        }
    }


# ---------------------------------------------------------------------------
# LocalSlm channel states
# ---------------------------------------------------------------------------


class TestChannelStates:
    def test_dependency_absent_falls_back_to_rules_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Poison the module so the lazy import cannot succeed, whatever the
        # host environment has installed — hermetic by construction.
        monkeypatch.setitem(sys.modules, "llama_cpp", None)
        path = write_model_file(tmp_path)
        slm = LocalSlm(path)  # the real default loader
        state = slm.reload_for_pack(make_pack(manifest=manifest_for(path)))
        assert state == DEPENDENCY_MISSING
        assert slm.rank(GOOD_ALERT, default_rule()) is None
        assert not slm.ready

    def test_dependency_absent_via_injected_loader(self, tmp_path: Path) -> None:
        def loader(path: Path) -> Any:
            raise SlmDependencyMissing("no llama_cpp in this venv")

        path = write_model_file(tmp_path)
        slm = LocalSlm(path, loader=loader)
        assert slm.reload_for_pack(make_pack(manifest=manifest_for(path))) == (
            DEPENDENCY_MISSING
        )
        assert slm.rank(GOOD_ALERT, default_rule()) is None

    def test_stubbed_good_model_loads_and_ranks(self, tmp_path: Path) -> None:
        slm = ready_slm(tmp_path, StubModel())
        opinion = slm.rank(GOOD_ALERT, default_rule())
        assert opinion is not None
        assert opinion.confidence == pytest.approx(0.97)
        assert opinion.rule_id == "edge-001"
        assert slm.status()["model_sha256"] == MODEL_SHA256

    def test_corrupted_model_file_refuses_load(self, tmp_path: Path) -> None:
        # A file whose bytes do not hash to the signed manifest: the
        # tampered/corrupted case. The loader must never be reached.
        path = write_model_file(tmp_path)
        calls: list[Path] = []

        def loader(path: Path) -> Any:
            calls.append(path)
            return StubModel()

        tampered_manifest = ModelManifest(
            name="security-slm-1b-q4",
            sha256=hashlib.sha256(b"not-the-bytes-on-disk").hexdigest(),
            format="gguf",
        )
        slm = LocalSlm(path, loader=loader)
        assert slm.reload_for_pack(make_pack(manifest=tampered_manifest)) == (
            HASH_MISMATCH
        )
        assert calls == []  # verified-before-load: never handed to the loader
        assert slm.rank(GOOD_ALERT, default_rule()) is None
        assert not slm.ready

    def test_missing_model_file_refuses_load(self, tmp_path: Path) -> None:
        manifest = ModelManifest(
            name="security-slm-1b-q4", sha256=MODEL_SHA256, format="gguf"
        )
        slm = LocalSlm(tmp_path / "absent.gguf", loader=lambda p: StubModel())
        assert slm.reload_for_pack(make_pack(manifest=manifest)) == FILE_MISSING
        assert slm.rank(GOOD_ALERT, default_rule()) is None

    def test_unsupported_format_refuses_load(self, tmp_path: Path) -> None:
        path = write_model_file(tmp_path)
        manifest = manifest_for(path, fmt="onnx")
        slm = LocalSlm(path, loader=lambda p: StubModel())
        assert slm.reload_for_pack(make_pack(manifest=manifest)) == (FORMAT_UNSUPPORTED)
        assert not slm.ready

    def test_load_failure_after_verification(self, tmp_path: Path) -> None:
        path = write_model_file(tmp_path)

        def loader(path: Path) -> Any:
            raise RuntimeError("ggml init failed")

        slm = LocalSlm(path, loader=loader)
        assert slm.reload_for_pack(make_pack(manifest=manifest_for(path))) == (
            LOAD_FAILED
        )
        assert slm.rank(GOOD_ALERT, default_rule()) is None

    def test_no_model_path_configured(self, tmp_path: Path) -> None:
        path = write_model_file(tmp_path)
        slm = LocalSlm(None, loader=lambda p: StubModel())
        assert slm.reload_for_pack(make_pack(manifest=manifest_for(path))) == (
            NO_MODEL_PATH
        )
        assert slm.rank(GOOD_ALERT, default_rule()) is None

    def test_pack_without_manifest_disables_a_ready_channel(
        self, tmp_path: Path
    ) -> None:
        slm = ready_slm(tmp_path, StubModel())
        assert slm.reload_for_pack(make_pack(manifest=None)) == NO_MANIFEST
        assert slm.rank(GOOD_ALERT, default_rule()) is None
        assert slm.status()["model_sha256"] is None

    def test_same_manifest_reload_is_idempotent(self, tmp_path: Path) -> None:
        # A successful sync re-presents the pack every tick; a multi-GB
        # model must not re-verify and reload each minute.
        path = write_model_file(tmp_path)
        calls = 0

        def loader(path: Path) -> Any:
            nonlocal calls
            calls += 1
            return StubModel()

        slm = LocalSlm(path, loader=loader)
        pack = make_pack(manifest=manifest_for(path))
        assert slm.reload_for_pack(pack) == READY
        assert slm.reload_for_pack(pack) == READY
        assert calls == 1

    def test_changed_manifest_reloads(self, tmp_path: Path) -> None:
        path = write_model_file(tmp_path)
        calls: list[Path] = []

        def loader(path: Path) -> Any:
            calls.append(path)
            return StubModel()

        slm = LocalSlm(path, loader=loader)
        first = make_pack(manifest=manifest_for(path))
        assert slm.reload_for_pack(first) == READY
        # A rotated pack names different model bytes on the same path: the
        # channel must not mistake the identical path for the same model.
        path.write_bytes(b"rotated-gguf-weights")
        rotated = make_pack(policy_version=43, manifest=manifest_for(path))
        assert slm.reload_for_pack(rotated) == READY
        assert calls == [path, path]

    def test_inference_failure_disables_the_channel(self, tmp_path: Path) -> None:
        slm = ready_slm(tmp_path, ExplodingModel())
        assert slm.rank(GOOD_ALERT, default_rule()) is None
        assert slm.status()["state"] == LOAD_FAILED
        # Disabled means disabled: no further opinions from a broken model.
        assert slm.rank(GOOD_ALERT, default_rule()) is None


class TestParseConfidence:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("0.93", 0.93),
            ("confident: 0.93", 0.93),
            ("1.0", 1.0),
            ("0", 0.0),
            ("-0.5", None),  # out of range, not a probability
            ("5.0", None),  # out of range never reads as high
            ("nan", None),  # the regex cannot match it at all
            ("no number here", None),
            ("", None),
        ],
    )
    def test_parse(self, text: str, expected: float | None) -> None:
        if expected is None:
            assert _parse_confidence(text) is None
        else:
            assert _parse_confidence(text) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# The authority fold — where the envelope's grant is applied
# ---------------------------------------------------------------------------


class TestFoldAuthority:
    def test_no_opinion_folds_to_sensor(self) -> None:
        folded = fold_triage(SENSOR_CONFIDENCE, None, default_envelope())
        assert folded.triage == LocalTriage(
            confidence=SENSOR_CONFIDENCE, source="sensor"
        )
        assert folded.opinion is None
        assert folded.deciding is False

    def test_advisory_when_envelope_disallows(self) -> None:
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.97)
        folded = fold_triage(SENSOR_CONFIDENCE, opinion, default_envelope())
        # The sensor confidence decides; the SLM ranking rides along.
        assert folded.triage == LocalTriage(
            confidence=SENSOR_CONFIDENCE, source="sensor"
        )
        assert folded.opinion is opinion
        assert folded.deciding is False

    def test_deciding_when_envelope_allows(self) -> None:
        envelope = default_envelope(allow_slm_decisions=True)
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.97)
        folded = fold_triage(SENSOR_CONFIDENCE, opinion, envelope)
        assert folded.triage == LocalTriage(confidence=0.97, source="slm")
        assert folded.deciding is True


class TestRenderDecisionRule:
    def test_advisory_annotation_appended(self) -> None:
        folded = FoldedTriage(
            triage=LocalTriage(confidence=0.5, source="sensor"),
            opinion=SlmOpinion(rule_id="edge-001", confidence=0.97),
            deciding=False,
        )
        rendered = render_decision_rule("edge-001 met (sensor 0.93)", folded)
        assert rendered == (
            "edge-001 met (sensor 0.93); slm advisory rank=0.97"
            " (advisory only, not deciding)"
        )

    def test_deciding_render_unchanged(self) -> None:
        # The ladder's render already names the slm confidence.
        folded = FoldedTriage(
            triage=LocalTriage(confidence=0.97, source="slm"),
            opinion=SlmOpinion(rule_id="edge-001", confidence=0.97),
            deciding=True,
        )
        assert render_decision_rule("edge-001 met (slm 0.97)", folded) == (
            "edge-001 met (slm 0.97)"
        )

    def test_no_opinion_render_unchanged(self) -> None:
        folded = FoldedTriage(
            triage=LocalTriage(confidence=0.93, source="sensor"),
            opinion=None,
            deciding=False,
        )
        assert render_decision_rule("edge-001 met (sensor 0.93)", folded) == (
            "edge-001 met (sensor 0.93)"
        )


# ---------------------------------------------------------------------------
# The ladder, fed folded triage — authority semantics unchanged
# ---------------------------------------------------------------------------


def decide_with_fold(pack: PolicyPack, folded: FoldedTriage) -> Any:
    """The full ladder over one folded candidate (guard before the cap)."""
    return decide_local_action(
        pack,
        pack.rules[0],
        folded.triage,
        "198.51.100.7",  # TEST-NET-2: never a protected target
        TargetGuard.from_pack(pack),
        budget_for(pack.autonomy_envelope),
        now=WARDEN_NOW,
    )


class TestLadderIntegration:
    def test_advisory_cannot_rescue_a_below_floor_refusal(self) -> None:
        # The SLM says 0.97 but the sensor says 0.80: the refusal stands —
        # on the sensor channel, named in the render — and the advisory
        # annotation rides along at journal-record time (engine surface).
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.97)
        folded = fold_triage(0.80, opinion, default_envelope())
        decision = decide_with_fold(make_pack(), folded)
        assert decision.allowed is False
        assert decision.code == BELOW_CONFIDENCE_FLOOR
        assert decision.decision_rule == (
            "edge.confidence_floor=0.90 not met (sensor 0.80)"
        )

    def test_advisory_sensor_pass_decides_on_the_sensor(self) -> None:
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.97)
        folded = fold_triage(SENSOR_CONFIDENCE, opinion, default_envelope())
        decision = decide_with_fold(make_pack(), folded)
        assert decision.allowed is True
        assert decision.triage_source == "sensor"
        assert decision.confidence == pytest.approx(SENSOR_CONFIDENCE)

    def test_deciding_mode_uses_the_slm_confidence(self) -> None:
        pack = make_pack(envelope=default_envelope(allow_slm_decisions=True))
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.97)
        folded = fold_triage(0.80, opinion, pack.autonomy_envelope)
        decision = decide_with_fold(pack, folded)
        assert decision.allowed is True
        assert decision.triage_source == "slm"
        assert decision.confidence == pytest.approx(0.97)
        assert "slm 0.97" in decision.decision_rule

    def test_deciding_mode_slm_low_confidence_refuses(self) -> None:
        pack = make_pack(envelope=default_envelope(allow_slm_decisions=True))
        opinion = SlmOpinion(rule_id="edge-001", confidence=0.50)
        folded = fold_triage(SENSOR_CONFIDENCE, opinion, pack.autonomy_envelope)
        decision = decide_with_fold(pack, folded)
        assert decision.allowed is False
        assert decision.code == BELOW_CONFIDENCE_FLOOR


# ---------------------------------------------------------------------------
# Through the loop — the journal and metrics surfaces
# ---------------------------------------------------------------------------


def slm_metrics(metrics: Any) -> dict[str, float]:
    text = metrics.render().decode()
    counts: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("warden_slm_opinions_total{"):
            outcome = line.split('outcome="')[1].split('"')[0]
            counts[outcome] = float(line.rsplit(" ", 1)[1])
    return counts


class TestEngineWiring:
    @respx.mock
    async def test_advisory_ranking_surfaced_in_the_journal(
        self, tmp_path: Path
    ) -> None:
        # Default signed envelope (allow_slm_decisions=false): the model
        # ranks, the sensor confidence decides, and the journal's
        # decision_rule reflects exactly that.
        slm = LocalSlm(write_model_file(tmp_path), loader=lambda p: StubModel())
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, slm=slm, pack_overrides=pack_overrides_with_file_model()
        )
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        rule_text = records[0]["decision_rule"]
        assert "sensor 0.93" in rule_text  # the deciding channel
        assert "slm advisory rank=0.97" in rule_text  # the advisory channel
        assert "advisory only, not deciding" in rule_text

    @respx.mock
    async def test_hash_mismatch_pack_keeps_the_loop_rules_only(
        self, tmp_path: Path
    ) -> None:
        # The pack's manifest names bytes the on-disk file does not have
        # (the default fixture manifest): the channel refuses to load, and
        # triage proceeds rules-only — the alert still decides on sensor
        # confidence with no advisory annotation.
        slm = LocalSlm(write_model_file(tmp_path), loader=lambda p: StubModel())
        loop, sentinel, journal, clock, _registry = make_loop(tmp_path, slm=slm)
        await drive_to_autonomous(loop, clock)
        assert loop.status()["slm"]["state"] == HASH_MISMATCH

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        assert "sensor 0.93" in records[0]["decision_rule"]
        assert "advisory" not in records[0]["decision_rule"]
        assert slm_metrics(loop._deps.metrics) == {"unavailable": 1.0}

    @respx.mock
    async def test_deciding_pack_surfaces_slm_confidence_in_the_journal(
        self, tmp_path: Path
    ) -> None:
        envelope = {
            "allowed_actions": ["block_ip"],
            "max_actions_per_hour": 5,
            "max_action_ttl_minutes": 30,
            "require_reversible": True,
            "confidence_floor": 0.90,
            "allow_slm_decisions": True,
        }
        # The sensor says 0.93 and the SLM 0.80: with the signed grant the
        # SLM's confidence IS the decision confidence — and 0.80 < floor
        # 0.90 refuses, proving the slm channel really drove the ladder.
        slm = LocalSlm(
            write_model_file(tmp_path), loader=lambda p: StubModel(answer="0.80")
        )
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path,
            slm=slm,
            pack_overrides={
                "envelope": envelope,
                **pack_overrides_with_file_model(),
            },
        )
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        # The wire's execution vocabulary has no "refused" — refusals are
        # non-enforcement records (action_type "none", executor
        # "decision") with the refusal code riding decision_rule.
        assert records[0]["action_type"] == "none"
        assert records[0]["execution"]["status"] == "failed"
        assert records[0]["execution"]["executor"] == "decision"
        assert "below-confidence-floor" in records[0]["decision_rule"]
        assert "slm 0.80" in records[0]["decision_rule"]
        assert slm_metrics(loop._deps.metrics) == {"deciding": 1.0}

    @respx.mock
    async def test_status_reports_channel_state_and_authority(
        self, tmp_path: Path
    ) -> None:
        slm = LocalSlm(write_model_file(tmp_path), loader=lambda p: StubModel())
        loop, _sentinel, _journal, clock, _registry = make_loop(
            tmp_path, slm=slm, pack_overrides=pack_overrides_with_file_model()
        )
        assert loop.status()["slm"]["state"] == UNLOADED

        await loop.tick()  # pack installs; the channel loads
        status = loop.status()["slm"]
        assert status["state"] == READY
        assert status["deciding"] is False  # the default signed envelope

    async def test_status_without_a_channel_is_none(self, tmp_path: Path) -> None:
        loop, _sentinel, _journal, _clock, _registry = make_loop(tmp_path)
        assert loop.status()["slm"] is None

    @respx.mock
    async def test_metrics_count_advisory_when_channel_ranks(
        self, tmp_path: Path
    ) -> None:
        slm = LocalSlm(write_model_file(tmp_path), loader=lambda p: StubModel())
        loop, sentinel, _journal, clock, _registry = make_loop(
            tmp_path, slm=slm, pack_overrides=pack_overrides_with_file_model()
        )
        await drive_to_autonomous(loop, clock)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert slm_metrics(loop._deps.metrics) == {"advisory": 1.0}


class TestMatchAlertsFold:
    def test_candidates_carry_folded_triage(self) -> None:
        candidates = match_alerts(make_pack(), dict(GOOD_ALERT))
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.rule.rule_id == "edge-001"
        assert candidate.target == "198.51.100.7"
        assert candidate.folded.triage.source == "sensor"
        assert candidate.folded.opinion is None

    def test_candidates_rank_through_a_ready_channel(self, tmp_path: Path) -> None:
        stub = StubModel()
        slm = ready_slm(tmp_path, stub)
        candidates = match_alerts(make_pack(), dict(GOOD_ALERT), slm)
        assert candidates[0].folded.opinion is not None
        assert candidates[0].folded.opinion.confidence == pytest.approx(0.97)
        assert candidates[0].folded.deciding is False  # default envelope
        assert stub.prompts  # the model was actually consulted

"""The optional local SLM triage channel: ranking, never silent authority.

Warden's rules are the decision floor; the optional quantized SLM
(llama.cpp, GGUF, 1B–3B) sharpens the *ranking* of what a rule matched.
The signed policy pack owns every bit of the SLM's authority: the pack's
``model_manifest`` names the exact model bytes (sha256 — never a URL),
and the pack's envelope decides whether SLM output may carry a decision
(``allow_slm_decisions``, default false). With it false the SLM output is
advisory ranking only — recorded in the journal's ``decision_rule``, but
the sensor confidence is what the ladder sees.

Failure is a downgrade, never a default-on:

- dependency absent (llama-cpp-python not installed) → rules-only
- no manifest in the pack, no model path configured, file missing → rules-only
- model file bytes mismatch the signed manifest → refuses to load → rules-only
- model file verified but the runtime fails to load it → rules-only
- inference raises or the answer is not a probability → no opinion, and the
  channel disables itself (a model that answers garbage is not "ready")
- out-of-range answers (5.0) are no opinion — out-of-range never reads as
  high, the ``approval_requirement`` precedent

The dependency is deliberately an opt-in extra (requirements.txt, commented
group, absent from requirements.lock): a native-build package must not land
in every image, and the import here is lazy so its absence is a state, not
a crash. Model files are never committed to the repo — an operator stages
the file named by the manifest, and the manifest's hash is the only trust.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from core.edge.decision import LocalTriage
from core.edge.policy import AutonomyEnvelope, EdgeRule, ModelManifest, PolicyPack

logger = logging.getLogger(__name__)

__all__ = [
    "DEPENDENCY_MISSING",
    "FILE_MISSING",
    "FORMAT_UNSUPPORTED",
    "HASH_MISMATCH",
    "LOAD_FAILED",
    "NO_MANIFEST",
    "NO_MODEL_PATH",
    "READY",
    "UNLOADED",
    "FoldedTriage",
    "LocalSlm",
    "SlmDependencyMissing",
    "SlmLoadFailed",
    "SlmModel",
    "SlmOpinion",
    "fold_triage",
    "render_decision_rule",
]

# Channel states — what the status payload and journal reasoning read.
# Every state but READY means the runtime is triaging rules-only.
UNLOADED = "unloaded"  # no pack installed yet
NO_MANIFEST = "no-manifest"  # this pack ships no model_manifest
NO_MODEL_PATH = "no-model-path"  # no WARDEN_SLM_MODEL_PATH configured
DEPENDENCY_MISSING = "dependency-missing"  # llama-cpp-python not installed
FILE_MISSING = "file-missing"  # nothing at the configured path
FORMAT_UNSUPPORTED = "format-unsupported"  # manifest names a format we cannot load
HASH_MISMATCH = "hash-mismatch"  # on-disk bytes differ from the signed manifest
LOAD_FAILED = "load-failed"  # verified bytes, but the runtime refused them
READY = "ready"

#: The only model format this runtime can load in v1.
SUPPORTED_MODEL_FORMAT = "gguf"


class SlmDependencyMissing(ImportError):
    """The optional llama-cpp-python dependency is not installed."""


class SlmLoadFailed(RuntimeError):
    """The model file verified but the runtime failed to load it."""


class SlmModel(Protocol):
    """A loaded SLM handle: one prompt in, raw completion text out."""

    def complete(self, prompt: str) -> str: ...


class _LlamaCppModel:
    """The llama.cpp adapter: greedy decode, a few tokens, one number back."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def complete(self, prompt: str) -> str:
        result = self._handle(prompt, max_tokens=16, temperature=0.0)
        return str(result["choices"][0]["text"])


def _load_llama_cpp(model_path: Path) -> SlmModel:
    """The default loader — the optional dependency, imported lazily.

    ImportError is a named state (DEPENDENCY_MISSING), and any construction
    failure after the bytes verified is another (LOAD_FAILED); neither may
    take triage down with it.
    """
    try:
        from llama_cpp import Llama  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SlmDependencyMissing(str(exc)) from exc
    try:
        handle = Llama(model_path=str(model_path), n_ctx=2048, verbose=False)
    except Exception as exc:
        raise SlmLoadFailed(str(exc)) from exc
    return _LlamaCppModel(handle)


# ---------------------------------------------------------------------------
# Pure functions — the decision-relevant surface, all I/O-free
# ---------------------------------------------------------------------------


def verify_model_file(path: Path, manifest: ModelManifest) -> str | None:
    """The on-disk model against the signed manifest, or why it refuses.

    Verify-before-load, the Medic trust_check ordering: the bytes are
    hashed and compared before anything imports or parses them. ``None``
    means the file may be handed to the loader.
    """
    if manifest.format != SUPPORTED_MODEL_FORMAT:
        return FORMAT_UNSUPPORTED
    if not path.is_file():
        return FILE_MISSING
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return LOAD_FAILED  # exists but unreadable: honestly a load failure
    if digest.hexdigest() != manifest.sha256.lower():
        return HASH_MISMATCH
    return None


def _score_prompt(alert: dict[str, Any], rule: EdgeRule) -> str:
    """The scoring prompt: only what the alert and the signed rule assert."""
    brief = {
        "alert": {
            key: alert.get(key) for key in ("indicator", "value", "mitre", "confidence")
        },
        "rule": {"rule_id": rule.rule_id, "mitre": list(rule.mitre)},
        "action": rule.action.type,
    }
    return (
        "Security triage: rate 0.0-1.0 how likely this alert requires the "
        f"rule's containment action ({rule.action.type}).\n"
        f"{json.dumps(brief, sort_keys=True)}\n"
        "Respond with only the number."
    )


def _parse_confidence(text: str) -> float | None:
    """The model's probability, or None when the output is not one.

    Strict on purpose: a non-float or out-of-range answer is no answer.
    The regex cannot match ``nan`` or ``inf``, and anything outside
    [0, 1] — including a negative — refuses, so a broken model can never
    read as a confident one.
    """
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    try:
        value = float(match.group(0))
    except ValueError:  # pragma: no cover - the regex guarantees a float
        return None
    if not 0.0 <= value <= 1.0:
        return None
    return value


@dataclass(frozen=True)
class SlmOpinion:
    """What the SLM concluded about one alert-rule match.

    Authority-blind by construction: it carries only the model's output.
    Whether it decides or ranks is the envelope's call, applied in
    :func:`fold_triage`.
    """

    rule_id: str
    confidence: float


@dataclass(frozen=True)
class FoldedTriage:
    """The triage a candidate hands the ladder, plus its advisory cargo.

    ``opinion`` rides along for the journal and metrics; ``deciding``
    says whether that opinion's confidence IS the decision confidence
    (signed opt-in) or advisory ranking beside the sensor's.
    """

    triage: LocalTriage
    opinion: SlmOpinion | None
    deciding: bool


def fold_triage(
    sensor_confidence: float,
    opinion: SlmOpinion | None,
    envelope: AutonomyEnvelope,
) -> FoldedTriage:
    """What the ladder sees for one candidate — the authority gate at runtime.

    The SLM's confidence becomes the decision confidence only when the
    signed envelope grants SLM decisions; otherwise the sensor confidence
    decides and the SLM ranking rides along as advisory. The ladder keeps
    its own SLM-authority rung as defense-in-depth behind this fold.
    """
    if opinion is None:
        return FoldedTriage(
            triage=LocalTriage(confidence=sensor_confidence, source="sensor"),
            opinion=None,
            deciding=False,
        )
    if envelope.allow_slm_decisions:
        return FoldedTriage(
            triage=LocalTriage(confidence=opinion.confidence, source="slm"),
            opinion=opinion,
            deciding=True,
        )
    return FoldedTriage(
        triage=LocalTriage(confidence=sensor_confidence, source="sensor"),
        opinion=opinion,
        deciding=False,
    )


def render_decision_rule(base: str, folded: FoldedTriage | None) -> str:
    """The journal's decision_rule: the ladder's render, plus advisory cargo.

    An advisory ranking is appended so an operator reading the journal
    sees both channels — and sees that the SLM did not decide. When the
    SLM did decide, the ladder's render already names the ``slm``
    confidence; annotating again would say it twice.
    """
    if folded is None or folded.opinion is None or folded.deciding:
        return base
    return (
        f"{base}; slm advisory rank={folded.opinion.confidence:.2f}"
        " (advisory only, not deciding)"
    )


# ---------------------------------------------------------------------------
# The component
# ---------------------------------------------------------------------------


class LocalSlm:
    """The optional on-device SLM channel, re-derived from every pack.

    Authority tracks the verified pack exactly: a pack install re-verifies
    the manifest (sha256 of the on-disk file, before load), a pack without
    a manifest disables the channel outright. A successful sync
    re-presents the same pack every tick, so a same-manifest reload is a
    no-op — a multi-GB model must not re-verify each minute. This object
    never raises: every failure is a named state and rules-only triage.
    """

    def __init__(
        self,
        model_path: Path | None,
        *,
        loader: Callable[[Path], SlmModel] = _load_llama_cpp,
    ) -> None:
        self._model_path = model_path
        self._loader = loader
        self._state = UNLOADED
        self._model: SlmModel | None = None
        self._loaded_sha256: str | None = None
        self._detail = "no pack installed yet"

    # ------------------------------------------------------------------
    # Pack lifecycle
    # ------------------------------------------------------------------

    def reload_for_pack(self, pack: PolicyPack) -> str:
        """(Re)verify and (re)load for this pack's manifest — or disable.

        Returns the resulting state; the loop calls this on every pack
        install, tests call it directly with constructed packs.
        """
        manifest = pack.model_manifest
        if manifest is None:
            self._disable(NO_MANIFEST, "pack ships no model manifest")
            return self._state
        if self._state == READY and self._loaded_sha256 == manifest.sha256:
            return self._state  # same signed manifest; keep the loaded model
        if self._model_path is None:
            self._disable(NO_MODEL_PATH, "no model file path configured")
            return self._state
        problem = verify_model_file(self._model_path, manifest)
        if problem is not None:
            self._disable(problem, f"model file at {self._model_path} refused")
            return self._state
        try:
            self._model = self._loader(self._model_path)
        except SlmDependencyMissing as exc:
            self._model = None
            self._state = DEPENDENCY_MISSING
            self._detail = str(exc)[:200]
            return self._state
        except Exception as exc:  # noqa: BLE001 - any load failure is rules-only
            self._model = None
            self._state = LOAD_FAILED
            self._detail = str(exc)[:200]
            return self._state
        self._state = READY
        self._loaded_sha256 = manifest.sha256
        self._detail = f"loaded {manifest.name} ({manifest.format})"
        logger.info(
            "warden slm triage ready: %s (%s) verified against manifest",
            manifest.name,
            manifest.format,
        )
        return self._state

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def rank(self, alert: dict[str, Any], rule: EdgeRule) -> SlmOpinion | None:
        """The SLM's confidence for one alert-rule match, or None.

        None is the honest "no opinion": channel disabled, inference
        failed, or the answer was not a probability. It never substitutes
        the sensor confidence and never reads as high — the fold decides
        what the ladder sees.
        """
        model = self._model
        if self._state != READY or model is None:
            return None
        try:
            answer = model.complete(_score_prompt(alert, rule))
        except Exception:  # noqa: BLE001 - a failed inference is a failed channel
            logger.exception("warden slm inference failed; disabling the channel")
            self._disable(LOAD_FAILED, "inference failed; channel disabled")
            return None
        confidence = _parse_confidence(answer)
        if confidence is None:
            logger.warning(
                "warden slm produced no usable confidence (%r); no opinion",
                answer[:60],
            )
            return None
        return SlmOpinion(rule_id=rule.rule_id, confidence=confidence)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._state == READY

    def status(self) -> dict[str, Any]:
        """Channel facts for the loop's status payload."""
        return {
            "state": self._state,
            "model_sha256": self._loaded_sha256 if self._state == READY else None,
            "detail": self._detail,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _disable(self, state: str, detail: str) -> None:
        """Drop the model and record why the channel is rules-only."""
        self._model = None
        self._loaded_sha256 = None
        self._state = state
        self._detail = detail

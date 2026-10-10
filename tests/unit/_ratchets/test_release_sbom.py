"""Every Vigil release must ship its SBOMs: generation, attestation, publication.

The release workflow inventories each published image (syft scan of the signed
index digest), attaches a keyless CycloneDX attestation to that same digest,
and publishes ten SBOM files plus checksums as release assets. Any of that
silently disappearing — a deleted step, an attestation re-keyed to a mutable
tag or to the config digest docker manifest inspect reports, an upload entry
dropped — recreates the gap this pipeline closed, so deleting SBOM support
fails CI here rather than surfacing in the next audit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RELEASE_WF = _REPO_ROOT / ".github" / "workflows" / "release.yml"

# Concrete pins: the action by full commit SHA (never a mutable tag), syft at
# the version the release SBOMs were validated against. Bumping either is a
# deliberate change and edits this ratchet with it.
_SYFT_ACTION_SHA = "66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c"  # v0.24.3
_SYFT_VERSION = "v1.54.1"
_NPM_GENERATOR = "@cyclonedx/cyclonedx-npm@6.0.1"

_BUILD_JOBS = ("build-backend", "build-daemon", "build-agent", "build-enforcer")
_BUILD_JOB_IMAGE = {
    "build-backend": "vigil-backend",
    "build-daemon": "vigil-daemon",
    "build-agent": "vigil-agent",
    "build-enforcer": "vigil-enforcer",
}
_NPM_SURFACES = (
    "clients/web",
    "clients/desktop",
    "services/agent",
    "infra/docker/mcp-packages",
)

# The ten SBOM documents every release publishes (each with a .sha256 sibling).
_EXPECTED_SBOM_STEMS = (
    "vigil-sbom-backend",
    "vigil-sbom-daemon",
    "vigil-sbom-agent",
    "vigil-sbom-enforcer",
    "vigil-sbom-python",
    "vigil-sbom-npm-web",
    "vigil-sbom-npm-desktop",
    "vigil-sbom-npm-agent",
    "vigil-sbom-npm-mcp-packages",
    "vigil-sbom-source",
)

_ATTEST_TYPE = "cyclonedx"  # verified against cosign 3.1.3: predicate alias for https://cyclonedx.org/bom


def _workflow() -> dict:
    raw = yaml.safe_load(_RELEASE_WF.read_text())
    assert isinstance(raw, dict) and isinstance(
        raw.get("jobs"), dict
    ), "release.yml does not parse into a workflow with jobs"
    return raw


def _steps(workflow: dict, job: str) -> list[dict]:
    steps = workflow["jobs"][job]["steps"]
    assert isinstance(steps, list), f"job {job} has no steps list"
    return [s for s in steps if isinstance(s, dict)]


def _step_named(workflow: dict, job: str, name: str) -> dict | None:
    return next((s for s in _steps(workflow, job) if s.get("name") == name), None)


@pytest.mark.unit
def test_workflow_exists():
    assert _RELEASE_WF.is_file()


@pytest.mark.unit
def test_build_jobs_plumb_the_signed_push_digest_as_output():
    """update-release must be able to key SBOMs to the digest cosign signed."""
    for job in _BUILD_JOBS:
        outputs = _workflow()["jobs"][job].get("outputs") or {}
        assert outputs.get("digest") == "${{ steps.push.outputs.digest }}", (
            f"{job} must expose its multi-arch index digest as the 'digest' job "
            "output — SBOMs and attestations key to the signed digest, never a tag"
        )


@pytest.mark.unit
@pytest.mark.parametrize("job", _BUILD_JOBS)
def test_build_job_installs_syft_sha_pinned(job: str):
    uses = [s.get("uses", "") for s in _steps(_workflow(), job)]
    syft_steps = [u for u in uses if "anchore/sbom-action" in u]
    assert syft_steps, f"{job} lost the syft install step"
    for u in syft_steps:
        assert u.startswith(f"anchore/sbom-action/download-syft@{_SYFT_ACTION_SHA}"), (
            f"{job}: anchore/sbom-action must be pinned to commit {_SYFT_ACTION_SHA} "
            f"(got {u!r}) — tag pins are mutable"
        )
    install = _step_named(_workflow(), job, "Install syft") or {}
    assert (
        install.get("with", {}).get("syft-version") == _SYFT_VERSION
    ), f"{job}: syft must stay pinned at {_SYFT_VERSION}"


@pytest.mark.unit
@pytest.mark.parametrize("job", _BUILD_JOBS)
def test_build_job_scans_the_signed_digest_and_attests_keylessly(job: str):
    image = _BUILD_JOB_IMAGE[job]

    scan = _step_named(_workflow(), job, "Generate image SBOM (CycloneDX)") or {}
    scan_run = scan.get("run") or ""
    stem = image.removeprefix("vigil-")
    assert 'syft scan "${IMAGE}@${DIGEST}"' in scan_run, (
        f"{job}: the SBOM scan must key to the same pushed index digest the sign "
        "step uses — never a tag, never a manifest-inspect config digest"
    )
    assert (
        f'-o "cyclonedx-json@1.6=vigil-sbom-{stem}-' in scan_run
    ), f"{job}: the scan must write the CycloneDX 1.6 file the attest step consumes"
    scan_env = scan.get("env") or {}
    assert scan_env.get("DIGEST") == "${{ steps.push.outputs.digest }}"

    attest = _step_named(_workflow(), job, "Attest SBOM (keyless)") or {}
    attest_run = " ".join((attest.get("run") or "").split())
    assert f"cosign attest --yes --type {_ATTEST_TYPE}" in attest_run, (
        f"{job}: the attestation must be cosign attest --yes --type {_ATTEST_TYPE} "
        "(cyclonedx is the installed cosign's alias for https://cyclonedx.org/bom)"
    )
    assert (
        '--predicate "vigil-sbom-' in attest_run
    ), f"{job}: the attestation predicate must be the generated SBOM file"
    assert (
        '"${IMAGE}@${DIGEST}"' in attest_run
    ), f"{job}: the attestation subject must mirror the sign step's subject"
    assert (
        "--key" not in attest_run
    ), f"{job}: attestation must stay keyless — no --key, GitHub OIDC via id-token: write"
    assert not scan.get("continue-on-error") and not attest.get(
        "continue-on-error"
    ), f"{job}: SBOM generation and attestation are release-blocking"


@pytest.mark.unit
def test_update_release_gates_on_and_consumes_the_build_digests():
    needs = _workflow()["jobs"]["update-release"]["needs"]
    for job in _BUILD_JOBS:
        assert (
            job in needs
        ), f"update-release must need {job} directly to read its digest output"


@pytest.mark.unit
def test_update_release_generates_source_side_sboms():
    gen = _step_named(_workflow(), "update-release", "Generate SBOMs (CycloneDX)") or {}
    run = gen.get("run") or ""
    assert run, "update-release lost the Generate SBOMs step"

    assert (
        "cyclonedx-py requirements requirements.lock" in run
    ), "the Python lock SBOM (cyclonedx-py on requirements.lock) went missing"
    assert "cyclonedx-bom==7.5.0" in _steps_runs(
        _workflow(), "update-release"
    ), "cyclonedx-py must come from the pinned cyclonedx-bom==7.5.0 install"

    assert "for proj in " in run, "the npm SBOM loop went missing"
    for surface in _NPM_SURFACES:
        assert surface in run, f"the npm SBOM loop must cover {surface}"
    assert (
        _NPM_GENERATOR in run and "--package-lock-only" in run
    ), f"npm SBOMs must use the pinned {_NPM_GENERATOR} in lockfile-only mode"

    assert "syft scan ." in run, (
        "the whole-source-tree syft scan (the only inventory covering the "
        "medic uv.lock) went missing"
    )

    for job, image in _BUILD_JOB_IMAGE.items():
        assert (
            f'syft scan "ghcr.io/vigil-soc/{image}@${{{{ needs.{job}.outputs.digest }}}}"'
            in run
        ), (
            f"the {image} release-asset SBOM must be regenerated from the plumbed "
            f"digest (needs.{job}.outputs.digest)"
        )


def _steps_runs(workflow: dict, job: str) -> str:
    return "\n".join(s.get("run") or "" for s in _steps(workflow, job))


@pytest.mark.unit
def test_update_release_writes_checksum_siblings():
    run = _steps_runs(_workflow(), "update-release")
    assert 'sha256sum "$(basename "$f")" > "${f}.sha256"' in run, (
        "the per-file .sha256 sibling generation went missing (bare file name "
        "inside, so sha256sum -c works as pasted)"
    )


@pytest.mark.unit
def test_update_release_uploads_every_sbom_and_checksum():
    upload = next(
        (
            s
            for s in _steps(_workflow(), "update-release")
            if "softprops/action-gh-release" in s.get("uses", "")
        ),
        None,
    )
    assert upload is not None, "the softprops release-upload step went missing"
    files = (upload.get("with", {}).get("files") or "").splitlines()
    sbom_files = [f.strip() for f in files if f.strip().startswith("sbom-dist/")]

    expected = {
        f"{stem}-${{{{ needs.version.outputs.version }}}}.cdx.json"
        for stem in _EXPECTED_SBOM_STEMS
    }
    expected |= {f"{f}.sha256" for f in expected}
    got = {f.split("/", 1)[1] for f in sbom_files}
    assert got == expected, (
        "the files: input must carry exactly the ten SBOM documents and their "
        f"checksums.\n  missing: {sorted(expected - got)}\n  extra: {sorted(got - expected)}"
    )


@pytest.mark.unit
def test_release_body_documents_attestation_verification():
    upload = next(
        (
            s
            for s in _steps(_workflow(), "update-release")
            if "softprops/action-gh-release" in s.get("uses", "")
        ),
        None,
    )
    body = (upload.get("with", {}).get("body") or "") if upload else ""
    assert (
        "cosign verify-attestation" in body and f"--type {_ATTEST_TYPE}" in body
    ), "the release body must include the copy-paste cosign verify-attestation one-liner"
    assert (
        "sha256sum -c" in body
    ), "the release body must document the checksum convention"


@pytest.mark.unit
def test_no_sbom_step_swallows_a_failure():
    """SBOM steps are release-blocking: a release ships with its SBOMs or fails."""
    offenders: list[str] = []
    for job_name, job in _workflow()["jobs"].items():
        for step in job.get("steps") or []:
            if not isinstance(step, dict) or not step.get("continue-on-error"):
                continue
            haystack = " ".join(
                str(step.get(k, "")) for k in ("name", "run", "uses")
            ).lower()
            if any(k in haystack for k in ("sbom", "syft", "cyclonedx", "attest")):
                offenders.append(f"{job_name}/{step.get('name')}")
    assert not offenders, f"SBOM steps must not set continue-on-error: {offenders}"

"""Contract tests for the fizzbait/ sample range datasets.

fizzbait/ is ingested by Vigil's S3 folder sync exactly as committed
(`POST /api/ingest/sync-s3-folder?prefix=fizzbait/`), so the folder carries
its own contract here:

- every line is a finding-shaped record with a stable ``finding_id`` (S3
  re-syncs dedupe on it, so a minted-on-ingest id would duplicate findings);
- labels are intact three ways: ``entity_context.label``, the directory
  split, and the ``cluster_id`` vocabulary (``benign-*`` vs ``c-<attack>-NNN``);
- the manifest agrees with disk (every file indexed, exact row counts);
- no file outgrows the in-memory S3 download path
  (``core/storage/s3_service.py`` ``get_file`` reads objects whole);
- no filename trips a ``.gitignore`` pattern that would silently drop the
  file from the repo (``*.log``, ``logs/``, ``*_config.json``, ``*_test.json``).

Spec: project blueprint "Fizzbait sample range datasets" (locked decisions
and the verification table live there).
"""

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIZZBAIT_DIR = REPO_ROOT / "fizzbait"
MANIFEST_PATH = FIZZBAIT_DIR / "manifest.yaml"

# Every dataset file stays comfortably under the in-memory S3 download path.
MAX_FILE_BYTES = 2 * 1024 * 1024

# Stable, sortable ids: f-<yyyymmdd>-<scenario>-<nnnn>. The scenario token
# must equal entity_context.scenario so ids stay self-describing.
FINDING_ID_RE = re.compile(r"^f-\d{8}-([a-z0-9_]+)-\d{4}$")

SCHEMA_VERSION = "1.0.0"
BENIGN_SEVERITIES = {"info", "low"}
MALICIOUS_SEVERITIES = {"medium", "high", "critical"}
BENIGN_FAMILIES = ("dns", "edr", "email", "firewall", "flow", "proxy")
MALICIOUS_SCENARIOS = (
    "c2_beaconing",
    "credential_brute_force",
    "dns_exfiltration",
    "lateral_movement_rdp",
    "phishing_initial_access",
    "port_scan",
    "powershell_encoded",
    "ransomware_staging",
)
REQUIRED_FIELDS = (
    "finding_id",
    "timestamp",
    "data_source",
    "severity",
    "status",
    "anomaly_score",
    "title",
    "description",
    "mitre_predictions",
    "entity_context",
    "cluster_id",
    "source_metadata",
)

# Spec-bounded row counts: benign families are the dense baselines, attack
# scenarios stay small and punchy.
BENIGN_ROW_RANGE = (300, 800)
MALICIOUS_ROW_RANGE = (100, 300)


def _dataset_files():
    return sorted((FIZZBAIT_DIR / "benign").glob("*.jsonl")) + sorted(
        (FIZZBAIT_DIR / "malicious").glob("*.jsonl")
    )


def _load_jsonl(path):
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise AssertionError(f"{path.name}:{lineno}: blank line in dataset")
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name}:{lineno}: {exc}") from exc
    return rows


def _rel(path):
    return f"{path.parent.name}/{path.name}"


@pytest.fixture(scope="module")
def records_by_file():
    if not FIZZBAIT_DIR.is_dir():
        raise AssertionError("fizzbait/ directory is missing from the repo root")
    files = _dataset_files()
    assert files, "no .jsonl dataset files found under fizzbait/"
    return {path: _load_jsonl(path) for path in files}


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST_PATH.is_file(), "fizzbait/manifest.yaml is missing"
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Parseability and record shape
# --------------------------------------------------------------------------


def test_layout_matches_spec(records_by_file):
    benign = {p.stem for p in (FIZZBAIT_DIR / "benign").glob("*.jsonl")}
    malicious = {p.stem for p in (FIZZBAIT_DIR / "malicious").glob("*.jsonl")}
    assert benign == set(BENIGN_FAMILIES), "benign/ families drifted from the spec"
    assert malicious == set(MALICIOUS_SCENARIOS), "malicious/ scenarios drifted"


def test_every_line_parses_and_carries_required_fields(records_by_file):
    for path, rows in records_by_file.items():
        for i, rec in enumerate(rows, 1):
            missing = [field for field in REQUIRED_FIELDS if field not in rec]
            assert not missing, f"{_rel(path)}:{i}: missing fields {missing}"


def test_finding_ids_match_convention_and_are_unique(records_by_file):
    seen = {}
    for path, rows in records_by_file.items():
        for i, rec in enumerate(rows, 1):
            fid = rec["finding_id"]
            match = FINDING_ID_RE.match(fid)
            assert (
                match
            ), f"{_rel(path)}:{i}: id {fid!r} breaks the stable-id convention"
            assert (
                fid not in seen
            ), f"{_rel(path)}:{i}: duplicate id {fid!r} (first seen in {seen[fid]})"
            seen[fid] = _rel(path)
            assert (
                match.group(1) == rec["entity_context"]["scenario"]
            ), f"{fid}: id scenario token differs from entity_context.scenario"


def test_timestamps_are_iso8601_utc(records_by_file):
    for path, rows in records_by_file.items():
        for i, rec in enumerate(rows, 1):
            ts = rec["timestamp"]
            assert isinstance(ts, str) and ts.endswith("Z"), f"{_rel(path)}:{i}: {ts!r}"
            try:
                datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as exc:
                raise AssertionError(f"{_rel(path)}:{i}: {ts!r}") from exc


def test_provenance_metadata_points_back_at_the_folder(records_by_file):
    for path, rows in records_by_file.items():
        rel = _rel(path)
        for i, rec in enumerate(rows, 1):
            meta = rec["source_metadata"]
            assert meta.get("dataset") == "fizzbait", f"{rel}:{i}"
            assert meta.get("file") == rel, f"{rel}:{i}"
            assert meta.get("schema_version") == SCHEMA_VERSION, f"{rel}:{i}"
            assert rec["status"] == "new", f"{rel}:{i}"


# --------------------------------------------------------------------------
# Label integrity
# --------------------------------------------------------------------------


def test_label_integrity_directory_matches_field(records_by_file):
    for path, rows in records_by_file.items():
        expected = path.parent.name  # "benign" | "malicious"
        for i, rec in enumerate(rows, 1):
            label = rec["entity_context"].get("label")
            assert label in {
                "benign",
                "malicious",
            }, f"{_rel(path)}:{i}: unlabelled record"
            assert (
                label == expected
            ), f"{_rel(path)}:{i}: label {label!r} disagrees with directory {expected}/"


def test_benign_records_stay_quiet(records_by_file):
    benign = {
        p: rows for p, rows in records_by_file.items() if p.parent.name == "benign"
    }
    assert benign, "no benign files found"
    for path, rows in benign.items():
        for i, rec in enumerate(rows, 1):
            where = f"{_rel(path)}:{i}"
            assert (
                rec["mitre_predictions"] == {}
            ), f"{where}: benign row carries MITRE predictions"
            assert (
                rec["anomaly_score"] < 0.3
            ), f"{where}: anomaly_score too high for benign"
            assert (
                rec["severity"] in BENIGN_SEVERITIES
            ), f"{where}: severity too loud for benign"
            assert rec["cluster_id"].startswith(
                "benign-"
            ), f"{where}: wrong cluster vocabulary"


def test_malicious_records_carry_signal(records_by_file):
    malicious = {
        p: rows for p, rows in records_by_file.items() if p.parent.name == "malicious"
    }
    assert malicious, "no malicious files found"
    for path, rows in malicious.items():
        for i, rec in enumerate(rows, 1):
            where = f"{_rel(path)}:{i}"
            assert len(rec["mitre_predictions"]) >= 1, f"{where}: no MITRE prediction"
            assert (
                rec["anomaly_score"] >= 0.5
            ), f"{where}: anomaly_score too low for malicious"
            assert (
                rec["severity"] in MALICIOUS_SEVERITIES
            ), f"{where}: severity too quiet"
            assert rec["cluster_id"].startswith(
                "c-"
            ), f"{where}: wrong cluster vocabulary"


# --------------------------------------------------------------------------
# Manifest agreement and coverage
# --------------------------------------------------------------------------


def test_manifest_header(manifest):
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["dataset"] == "fizzbait"
    convention = manifest["label_convention"]
    assert convention["field"] == "entity_context.label"
    assert sorted(convention["directories"]) == ["benign/", "malicious/"]


def test_manifest_agrees_with_disk(records_by_file, manifest):
    entries = manifest["files"]
    by_path = {entry["path"]: entry for entry in entries}
    assert len(by_path) == len(entries), "manifest lists duplicate paths"
    disk = {_rel(path) for path in records_by_file}
    assert set(by_path) == disk, (
        f"manifest/disk mismatch; manifest-only: {sorted(set(by_path) - disk)}, "
        f"unindexed: {sorted(disk - set(by_path))}"
    )
    for path, rows in records_by_file.items():
        entry = by_path[_rel(path)]
        assert entry["row_count"] == len(
            rows
        ), f"{_rel(path)}: manifest claims {entry['row_count']} rows, disk has {len(rows)}"
        assert entry["label"] == path.parent.name, f"{_rel(path)}: manifest label"
        assert (
            entry["data_source"] == rows[0]["data_source"]
        ), f"{_rel(path)}: manifest data_source"
        assert (
            entry["scenario"] == rows[0]["entity_context"]["scenario"]
        ), f"{_rel(path)}: manifest scenario"
        assert (
            entry["cluster_id"] == rows[0]["cluster_id"]
        ), f"{_rel(path)}: manifest cluster_id"
        techniques = {t for r in rows for t in r["mitre_predictions"]}
        assert (
            set(entry.get("mitre_techniques", [])) == techniques
        ), f"{_rel(path)}: manifest MITRE techniques"


def test_row_counts_stay_in_spec_ranges(records_by_file):
    for path, rows in records_by_file.items():
        lo, hi = (
            BENIGN_ROW_RANGE if path.parent.name == "benign" else MALICIOUS_ROW_RANGE
        )
        assert (
            lo <= len(rows) <= hi
        ), f"{_rel(path)}: {len(rows)} rows outside the spec range {lo}-{hi}"


# --------------------------------------------------------------------------
# Repo hygiene
# --------------------------------------------------------------------------


def test_all_dataset_files_within_size_cap():
    over = [
        (str(p.relative_to(REPO_ROOT)), p.stat().st_size)
        for p in sorted(FIZZBAIT_DIR.rglob("*"))
        if p.is_file() and p.stat().st_size > MAX_FILE_BYTES
    ]
    assert not over, f"files exceed the {MAX_FILE_BYTES} byte cap: {over}"


def test_no_gitignore_trap_names():
    traps = []
    for p in sorted(FIZZBAIT_DIR.rglob("*")):
        rel = p.relative_to(REPO_ROOT)
        if p.name.endswith(".log"):
            traps.append(f"{rel}: *.log is gitignored")
        if "logs" in rel.parts:
            traps.append(f"{rel}: logs/ directory is gitignored")
        if p.name.endswith("_config.json"):
            traps.append(f"{rel}: *_config.json is gitignored")
        if p.name.endswith("_test.json"):
            traps.append(f"{rel}: *_test.json is gitignored")
    assert not traps, f"dataset paths would silently vanish from git: {traps}"


def test_git_check_ignore_reports_nothing():
    if shutil.which("git") is None:
        pytest.skip("git not available")
    paths = [
        str(p.relative_to(REPO_ROOT))
        for p in sorted(FIZZBAIT_DIR.rglob("*"))
        if p.is_file()
    ]
    proc = subprocess.run(
        ["git", "check-ignore", "--", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, (
        "git check-ignore matched dataset paths; they would be silently "
        f"excluded from the repo: {proc.stdout.strip()}"
    )

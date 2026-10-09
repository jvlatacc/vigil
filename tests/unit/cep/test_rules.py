"""Unit tests for the CEP rule schema + YAML loader.

Packs are written to ``tmp_path`` mirroring the shipped ``data/cep_rules/``
shape (one rule per file). The rejection tests pin the loader's strict
contract: a malformed pack fails at boot with an error naming the file and
field, never mid-attack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from core.cep.rules import (
    ENTITY_FIELDS,
    SEVERITY_ORDER,
    RuleValidationError,
    load_rules,
    meets_floor,
)

_VALID_RULE = """\
id: test-rule
entity_key_fields: [host]
window_seconds: 600
steps:
  - sources: [crowdstrike, sentinelone]
    techniques: [T1486]
    max_gap_seconds: 300
  - sources: [splunk, elastic, opensearch]
    techniques: [T1486, T1070]
    max_gap_seconds: 300
action_type: isolate_host
target_field: host
base_confidence: 0.82
"""


def _write_pack(tmp_path: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    return tmp_path


class TestValidPack:
    def test_valid_rule_loads_with_parsed_fields(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, {"rule.yaml": _VALID_RULE})

        (rule,) = load_rules(tmp_path)

        assert rule.id == "test-rule"
        assert rule.entity_key_fields == ("host",)
        assert rule.window_seconds == 600
        assert len(rule.steps) == 2
        assert rule.steps[0].sources == ("crowdstrike", "sentinelone")
        assert rule.steps[0].techniques == ("T1486",)
        assert rule.steps[0].max_gap_seconds == 300
        assert rule.steps[1].sources == ("splunk", "elastic", "opensearch")
        assert rule.action_type == "isolate_host"
        assert rule.target_field == "host"
        assert rule.base_confidence == 0.82
        assert rule.enabled is True

    def test_defaults_apply(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": """\
id: minimal-rule
entity_key_fields: [user]
window_seconds: 120
steps:
  - sources: [splunk]
  - sources: [crowdstrike]
    min_severity: high
action_type: isolate_host
target_field: user
base_confidence: 0.5
""",
            },
        )

        (rule,) = load_rules(tmp_path)

        assert rule.steps[0].max_gap_seconds == 600  # loader default
        assert rule.steps[0].min_severity is None
        assert rule.steps[0].techniques is None

    def test_yml_extension_and_sorted_order(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "b.yaml": _VALID_RULE.replace("id: test-rule", "id: b-rule"),
                "a.yml": _VALID_RULE.replace("id: test-rule", "id: a-rule"),
                "ignored.txt": "not yaml",
            },
        )

        rules = load_rules(tmp_path)

        assert [rule.id for rule in rules] == ["a-rule", "b-rule"]

    def test_enabled_false_loads_with_flag_off(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, {"rule.yaml": _VALID_RULE + "enabled: false\n"})

        (rule,) = load_rules(tmp_path)

        assert rule.enabled is False


class TestRejections:
    def test_single_step_rule_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    """  - sources: [crowdstrike, sentinelone]
    techniques: [T1486]
    max_gap_seconds: 300
""",
                    "",
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="at least 2 steps"):
            load_rules(tmp_path)

    def test_unknown_action_type_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "action_type: isolate_host", "action_type: nuke_datacenter"
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="action_type") as exc:
            load_rules(tmp_path)
        # The error lists the valid values so an operator can fix the pack.
        assert "isolate_host" in str(exc.value)

    def test_duplicate_id_across_files_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "a.yaml": _VALID_RULE,
                "b.yaml": _VALID_RULE,
            },
        )

        with pytest.raises(RuleValidationError, match="duplicate rule id"):
            load_rules(tmp_path)

    def test_unknown_top_level_key_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE + "base_confidnce: 0.9\n",
            },
        )

        with pytest.raises(RuleValidationError, match="unknown key"):
            load_rules(tmp_path)

    def test_unknown_step_key_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "    max_gap_seconds: 300",
                    "    max_gap_seconds: 300\n    tecniques: [T1486]",
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="unknown key"):
            load_rules(tmp_path)

    def test_invalid_min_severity_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "    max_gap_seconds: 300\n  - sources: [splunk",
                    "    max_gap_seconds: 300\n    min_severity: severe\n"
                    "  - sources: [splunk",
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="min_severity"):
            load_rules(tmp_path)

    def test_zero_window_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "window_seconds: 600", "window_seconds: 0"
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="window_seconds"):
            load_rules(tmp_path)

    def test_base_confidence_out_of_range_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "base_confidence: 0.82", "base_confidence: 1.5"
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="base_confidence"):
            load_rules(tmp_path)

    def test_target_outside_key_fields_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "entity_key_fields: [host]", "entity_key_fields: [user]"
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="target_field"):
            load_rules(tmp_path)

    def test_unknown_entity_key_field_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace(
                    "entity_key_fields: [host]",
                    "entity_key_fields: [device_id]",
                ),
            },
        )

        with pytest.raises(RuleValidationError, match="entity_key_fields"):
            load_rules(tmp_path)

    def test_non_bool_enabled_rejected(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, {"rule.yaml": _VALID_RULE + "enabled: yes_please\n"})

        with pytest.raises(RuleValidationError, match="enabled"):
            load_rules(tmp_path)

    def test_missing_required_key_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {
                "rule.yaml": _VALID_RULE.replace("window_seconds: 600\n", ""),
            },
        )

        with pytest.raises(RuleValidationError, match="window_seconds"):
            load_rules(tmp_path)

    def test_list_of_rules_at_top_level_rejected(self, tmp_path: Path) -> None:
        _write_pack(
            tmp_path,
            {"rule.yaml": f"- {_VALID_RULE.replace(chr(10), chr(10) + '  ')}"},
        )

        with pytest.raises(RuleValidationError, match="expected a mapping"):
            load_rules(tmp_path)

    def test_missing_directory_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RuleValidationError, match="not a directory"):
            load_rules(tmp_path / "nope")

    def test_unparseable_yaml_rejected(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, {"rule.yaml": "id: [unclosed"})

        with pytest.raises(RuleValidationError, match="unparseable YAML"):
            load_rules(tmp_path)

    def test_empty_file_skipped(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, {"empty.yaml": "", "rule.yaml": _VALID_RULE})

        rules = load_rules(tmp_path)

        assert [rule.id for rule in rules] == ["test-rule"]


class TestSeverityFloor:
    def test_vocabulary_is_the_codebase_scale(self) -> None:
        # The processor sanitizer (services/daemon/processor.py) and
        # case_automation_service._SEVERITY_ORDER both use this vocabulary.
        assert SEVERITY_ORDER == ("low", "medium", "high", "critical")
        assert ENTITY_FIELDS == ("host", "user", "src_ip", "dest_ip")

    def test_meets_floor_boundaries(self) -> None:
        assert meets_floor("high", "high")
        assert meets_floor("critical", "high")
        assert not meets_floor("medium", "high")
        assert not meets_floor("low", "medium")

    def test_absent_or_unknown_severity_never_meets_a_floor(self) -> None:
        assert not meets_floor(None, "low")
        assert not meets_floor("sev1", "low")

    def test_no_floor_matches_everything(self) -> None:
        assert meets_floor(None, None)
        assert meets_floor("low", None)
        assert meets_floor("weird-string", None)

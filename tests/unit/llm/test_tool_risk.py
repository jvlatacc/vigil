"""The shared direct-action taxonomy and the one rule that reads it.

Three surfaces read this module — chat's exclusion, the agent invoke gate and
the playbook phase grant — so its classification matrix is the contract they
all ship. A new verb lands here once and tightens all of them at once.
"""

from __future__ import annotations

import pytest

from core.llm import chat_layers, tool_risk
from core.llm.tool_risk import destructive_refusal, is_destructive_mcp

pytestmark = pytest.mark.unit


class TestTheSharedTaxonomy:
    # One list, not three: chat's exclusion and the invoke gate must decide on
    # the same predicate, or a new verb would tighten one surface alone.

    def test_chat_reads_the_same_predicate(self):
        assert chat_layers._is_destructive_mcp is is_destructive_mcp

    @pytest.mark.parametrize(
        "name",
        [
            "cf_waf_block_ip",
            "cf_waf_unblock_ip",
            "cf_gateway_block_domain",
            "cf_access_revoke_session",
            "mde_isolate",
            "cb_quarantine",
            "acme_edr_isolate",
            "okta_delete_user",
            "palo_alto_reset_device",
        ],
    )
    def test_direct_action_names_are_destructive(self, name):
        assert is_destructive_mcp(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "get_finding",
            "list_findings",
            "recall_entity",
            "splunk_execute",
            "get_isolation_status",
            "list_blocked_ips",
        ],
    )
    def test_read_only_names_are_not_destructive(self, name):
        # A read-only lead verb wins even with a destructive noun behind it,
        # and ART execute stays named rather than verb-matched.
        assert is_destructive_mcp(name) is False


class TestTheInvokeRule:
    # The gate refuses a direct-action call with no person on it; a person or
    # the operator's allow-list releases it.

    def test_no_person_is_a_refusal_with_a_rule(self):
        rule = destructive_refusal("cf_waf_block_ip", person_bound=False)
        assert rule == "agent.tool_risk_no_person=cf_waf_block_ip"

    def test_a_bound_person_releases_the_call(self):
        assert destructive_refusal("cf_waf_block_ip", person_bound=True) is None

    def test_the_operators_allow_list_releases_the_call(self):
        assert (
            destructive_refusal(
                "cf_waf_block_ip",
                person_bound=False,
                overrides=("cf_waf_block_ip",),
            )
            is None
        )

    def test_a_name_the_taxonomy_does_not_claim_is_never_refused(self):
        assert destructive_refusal("get_finding", person_bound=False) is None


class TestCurrentOverrides:
    # The allow-list is read live from the typed config, so what the report
    # shows and what the gate enforces cannot drift. A read that fails lists
    # nothing: an unreadable setting must not read as an exemption.

    def test_blanks_are_dropped_and_names_trimmed(self, monkeypatch):
        class _FakeConfig:
            tool_risk_overrides = (" cf_waf_block_ip ", "", "mde_isolate")

            @classmethod
            def from_settings(cls):
                return cls()

        monkeypatch.setattr(tool_risk, "ResponseConfig", _FakeConfig)
        assert tool_risk.current_overrides() == ("cf_waf_block_ip", "mde_isolate")

    def test_a_setting_that_cannot_be_read_exempts_nothing(self, monkeypatch):
        class _Unreadable:
            @classmethod
            def from_settings(cls):
                raise RuntimeError("config store down")

        monkeypatch.setattr(tool_risk, "ResponseConfig", _Unreadable)
        assert tool_risk.current_overrides() == ()
        # And the refusal stands: fail-closed, never silently exempt.
        rule = destructive_refusal("cf_waf_block_ip", person_bound=False)
        assert rule is not None

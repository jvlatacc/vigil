"""Kernel executor paths: dispatch, the TTL floor, the person guard, the posture.

The executor's job is narrow: carry the approval row's ``action_id`` and the
parameters' TTL to the ebpf_xdp slice's helpers, refuse below-floor TTLs before
dispatching, and return the daemon's reply untouched — evidence for
``mark_executed`` on success, an error code for ``mark_failed`` on anything
else. A kernel action a person never decided never reaches a helper: the
person-decided guard outranks everything downstream of it.
"""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from core.config import get_settings
from core.intent import FIELDS_BY_KEY, diff_intent, read_intent
from core.response.approval_service import (
    KERNEL_ACTION_TYPES,
    ActionStatus,
    ActionType,
    ApprovalService,
    PendingAction,
)
from core.response.autonomous_response_service import (
    KERNEL_TTL_FLOOR_SECONDS,
    AutonomousResponseService,
)
from core.response.config import ResponseConfig

pytestmark = pytest.mark.unit

ENFORCED = {
    "action_id": "action-1",
    "state": "enforced",
    "evidence": {
        "attach_point": "eth0/xdp",
        "map": "/sys/fs/bpf/vigil/xdp_block_v1",
        "map_slot": 17,
        "counters": {"dropped_packets": 0},
    },
    "expires_at": "2026-10-09T23:12:04Z",
}


class _Store:
    """The approval store as the executor sees it: rows in, marks out."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = {}
        self.failed = {}

    def list_actions(self, status=None, **_):
        return self._rows

    def mark_executed(self, action_id, result):
        self.executed[action_id] = result

    def mark_failed(self, action_id, error):
        self.failed[action_id] = error


def _kernel_row(
    action_id="action-1",
    action_type=ActionType.XDP_BLOCK_IP.value,
    *,
    requires_approval=True,
    approved_by="analyst",
    parameters=None,
    target="203.0.113.7",
):
    return PendingAction(
        action_id=action_id,
        action_type=action_type,
        title="t",
        description="d",
        target=target,
        confidence=0.99,
        reason="credential harvesting",
        evidence=[],
        created_at="",
        created_by="responder",
        requires_approval=requires_approval,
        status="approved",
        approved_by=approved_by,
        parameters=parameters or {},
    )


def _service(rows):
    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _Store(rows)
    return service


# --- dispatch -----------------------------------------------------------------


def test_an_approved_block_dispatches_the_slice_helper():
    service = _service([_kernel_row(parameters={"ttl_seconds": 3600})])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={"success": True, **ENFORCED},
    ) as helper:
        results = service.execute_approved_actions()

    helper.assert_called_once_with(
        ip="203.0.113.7",
        reason="credential harvesting",
        ttl_seconds=3600,
        action_id="action-1",
    )
    # The row's action_id travels to the daemon, so a retried dispatch replays
    # against the daemon's idempotency instead of double-enforcing.
    assert results[0]["action_id"] == "action-1"


def test_the_enforcers_evidence_is_stored_verbatim():
    service = _service([_kernel_row()])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={"success": True, **ENFORCED},
    ):
        service.execute_approved_actions()

    assert service.approval_service.executed["action-1"] == {
        "success": True,
        **ENFORCED,
    }


def test_an_approved_redirect_carries_the_port():
    service = _service(
        [
            _kernel_row(
                action_type=ActionType.SOCKET_REDIRECT.value,
                parameters={"port": 443, "ttl_seconds": 3600},
            )
        ]
    )
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_redirect_socket",
        return_value={"success": True, **ENFORCED},
    ) as helper:
        service.execute_approved_actions()

    helper.assert_called_once_with(
        ip="203.0.113.7",
        reason="credential harvesting",
        port=443,
        ttl_seconds=3600,
        action_id="action-1",
    )


def test_an_approved_interdict_resolves_the_pid_from_the_target():
    service = _service(
        [_kernel_row(action_type=ActionType.INTERDICT_PROCESS.value, target="4242")]
    )
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_interdict_process",
        return_value={"success": True, **ENFORCED},
    ) as helper:
        service.execute_approved_actions()

    # No pid in parameters, no ttl: the target names the process and the
    # integration's configured default TTL applies (None defers to it).
    helper.assert_called_once_with(
        pid=4242,
        reason="credential harvesting",
        ttl_seconds=None,
        action_id="action-1",
    )


def test_the_idempotency_key_convention_is_the_helpers_not_the_executors():
    # xdp_block_ip:{ip} and siblings are built inside the slice's helpers —
    # the single source of truth for the enforcement API surface. The executor
    # only guarantees the row's action_id; this pins that it does not build a
    # competing key.
    service = _service([_kernel_row()])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={"success": True, **ENFORCED},
    ) as helper:
        service.execute_approved_actions()

    assert helper.call_args.kwargs.keys() == {
        "ip",
        "reason",
        "ttl_seconds",
        "action_id",
    }


# --- TTL floor ----------------------------------------------------------------


def test_a_ttl_below_the_floor_is_refused_before_dispatching():
    service = _service(
        [_kernel_row(parameters={"ttl_seconds": KERNEL_TTL_FLOOR_SECONDS - 1})]
    )
    with patch("core.integrations.ebpf_xdp.tool.xdp_block_ip") as helper:
        service.execute_approved_actions()

    helper.assert_not_called()
    assert service.approval_service.failed["action-1"] == "ttl_below_floor"
    assert not service.approval_service.executed


def test_a_ttl_at_the_floor_dispatches():
    service = _service(
        [_kernel_row(parameters={"ttl_seconds": KERNEL_TTL_FLOOR_SECONDS})]
    )
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={"success": True, **ENFORCED},
    ) as helper:
        service.execute_approved_actions()

    helper.assert_called_once_with(
        ip="203.0.113.7",
        reason="credential harvesting",
        ttl_seconds=KERNEL_TTL_FLOOR_SECONDS,
        action_id="action-1",
    )


def test_a_non_numeric_ttl_is_refused():
    service = _service([_kernel_row(parameters={"ttl_seconds": "soon"})])
    with patch("core.integrations.ebpf_xdp.tool.xdp_block_ip") as helper:
        service.execute_approved_actions()

    helper.assert_not_called()
    assert service.approval_service.failed["action-1"] == "ttl_invalid"


# --- failure paths --------------------------------------------------------------


def test_an_unreachable_enforcer_fails_the_action():
    service = _service([_kernel_row()])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={
            "success": False,
            "error": "enforcer_unreachable",
            "message": "connection refused",
        },
    ):
        service.execute_approved_actions()

    assert service.approval_service.failed["action-1"] == "enforcer_unreachable"
    assert not service.approval_service.executed


def test_a_daemon_refusal_fails_the_action_with_the_daemons_code():
    service = _service([_kernel_row()])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        return_value={
            "success": False,
            "error": "invalid_target",
            "message": "loopback targets are refused",
        },
    ):
        service.execute_approved_actions()

    assert service.approval_service.failed["action-1"] == "invalid_target"


def test_a_raising_helper_fails_the_action():
    service = _service([_kernel_row()])
    with patch(
        "core.integrations.ebpf_xdp.tool.xdp_block_ip",
        side_effect=RuntimeError("boom"),
    ):
        service.execute_approved_actions()

    assert service.approval_service.failed["action-1"] == "boom"


# --- the person-decided guard ---------------------------------------------------


def test_a_kernel_row_no_person_decided_is_skipped():
    service = _service([_kernel_row(requires_approval=False, approved_by=None)])
    with patch("core.integrations.ebpf_xdp.tool.xdp_block_ip") as helper:
        results = service.execute_approved_actions()

    helper.assert_not_called()
    assert results == []
    assert not service.approval_service.executed
    assert not service.approval_service.failed


def test_unknown_action_types_stay_left_for_another_executor():
    service = _service([_kernel_row(action_type="custom")])
    results = service.execute_approved_actions()

    assert results == []
    assert not service.approval_service.executed
    assert not service.approval_service.failed


# --- the enforcement posture (creation side) ------------------------------------


@pytest.fixture
def no_db():
    """Stand-in session and config store so ApprovalService never reaches
    PostgreSQL (the same fixture test_approval_workflow.py uses)."""
    manager = Mock()

    @contextmanager
    def _scope():
        yield Mock()

    manager.session_scope = _scope
    config_store = Mock()
    config_store.read_system_config.return_value = {"enabled": False}
    with (
        patch("core.response.approval_service.get_db_manager", return_value=manager),
        patch(
            "core.response.approval_service.get_config_service",
            return_value=config_store,
        ),
    ):
        yield


def _create(svc: ApprovalService, action_type: ActionType, confidence: float):
    # No idempotency_key: with the mocked session a key lookup returns a Mock
    # and _row_to_pending would float() it. The real key convention is the
    # callers' concern; the posture under test reads requires_approval/status.
    return svc.create_action(
        action_type=action_type,
        title="t",
        description="d",
        target="203.0.113.7",
        confidence=confidence,
        reason="test",
        evidence=[],
        created_by="pytest",
    )


@pytest.mark.usefixtures("no_db")
class TestEnforcementPosture:
    """Kernel rows wait for a person while the INTENT.md posture stands."""

    def test_a_kernel_row_is_human_only_at_any_confidence(self):
        svc = ApprovalService()  # no-arg form: default intent
        action = _create(svc, ActionType.XDP_BLOCK_IP, confidence=0.99)
        assert action.status == ActionStatus.PENDING.value
        assert action.requires_approval is True
        # The row records the posture that held it, not the response-wide flag.
        assert "enforcement.force_manual_approval=True" in action.reason
        assert "approval.force_manual_approval=True" not in action.reason

    @pytest.mark.parametrize("action_type", sorted(KERNEL_ACTION_TYPES))
    def test_every_kernel_type_is_held(self, action_type):
        member = ActionType(action_type)
        svc = ApprovalService(config=ResponseConfig())
        action = _create(svc, member, confidence=0.99)
        assert action.requires_approval is True

    def test_non_kernel_rows_still_auto_approve_at_the_band(self):
        svc = ApprovalService(config=ResponseConfig())
        action = _create(svc, ActionType.BLOCK_IP, confidence=0.90)
        assert action.status == ActionStatus.APPROVED.value
        assert action.requires_approval is False

    def test_the_env_override_relaxes_the_creation_posture(self, monkeypatch):
        monkeypatch.setenv("DAEMON_ENFORCEMENT_FORCE_APPROVAL", "false")
        get_settings.cache_clear()
        try:
            svc = ApprovalService()
            action = _create(svc, ActionType.XDP_BLOCK_IP, confidence=0.99)
            assert action.status == ActionStatus.APPROVED.value
            assert action.requires_approval is False
        finally:
            get_settings.cache_clear()

    def test_the_relaxed_posture_still_leaves_the_execution_guard(self, monkeypatch):
        # The override changes how rows are created, not what can run
        # unattended: an auto-released kernel row is still skipped by the
        # person-decided guard at execution.
        monkeypatch.setenv("DAEMON_ENFORCEMENT_FORCE_APPROVAL", "false")
        get_settings.cache_clear()
        try:
            svc = ApprovalService()
            action = _create(svc, ActionType.XDP_BLOCK_IP, confidence=0.99)
        finally:
            get_settings.cache_clear()
        service = _service(
            [
                _kernel_row(
                    action_id=action.action_id,
                    requires_approval=False,
                    approved_by=None,
                )
            ]
        )
        with patch("core.integrations.ebpf_xdp.tool.xdp_block_ip") as helper:
            results = service.execute_approved_actions()
        helper.assert_not_called()
        assert results == []


# --- the intent reader -----------------------------------------------------------


class TestIntentReader:
    """The enforcement block has a reader; the shipped manifest declares it."""

    def test_the_enforcement_key_has_a_reader(self):
        field = FIELDS_BY_KEY["enforcement.force_manual_approval"]
        assert field.path == "response.enforcement_force_manual_approval"
        assert field.setting == "daemon_enforcement_force_approval"

    def test_the_shipped_manifest_declares_the_kernel_posture(self):
        declared = read_intent()
        assert declared is not None
        assert declared["enforcement.force_manual_approval"] is True

    def test_the_declared_posture_equals_the_shipped_default(self):
        # INTENT.md promises a fresh checkout reports no drift; the declared
        # true must therefore equal the code default, not just the env default.
        assert ResponseConfig().enforcement_force_manual_approval is True
        assert (
            ResponseConfig.from_settings(
                get_settings()
            ).enforcement_force_manual_approval
            is True
        )

    def test_relaxing_the_override_reports_tighten_drift(self):
        declared = {"enforcement.force_manual_approval": True}
        effective = {"enforcement.force_manual_approval": False}
        rows = diff_intent(
            declared,
            effective,
            {"response.enforcement_force_manual_approval": "env"},
        )
        assert len(rows) == 1
        assert rows[0].label == "tighten"
        assert rows[0].source == "env"

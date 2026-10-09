"""Unit tests for the console policies router (``core/policy_compiler/policies_router.py``).

DB access is faked with an in-memory session (the ``test_ai_config_api.py``
pattern) — no live Postgres. Security posture is covered by
``test_policies_router_security.py`` (401 on every route against the real app,
v1 absence) and by the deny-by-default gate in ``tests/security/``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.auth.auth_service import AuthService
from core.auth.current_user import get_current_user
from core.policy_compiler.models import compute_content_hash
from core.policy_compiler.policies_router import (
    ROUTER_META,
    agreement_counts,
    apply_transition,
)
from core.policy_compiler.policies_router import router as policies_router
from core.routing import request_unit_of_work
from core.storage.models import (
    CompiledPolicy,
    CompiledPolicyDecision,
    ConfigAuditLog,
)
from tests.unit.policy_compiler.fixtures.sample_ir import (
    POLICY_ID,
    sample_ir_dict,
)

pytestmark = pytest.mark.unit

ACTOR = "analyst-1"
T0 = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[3]


# --- Fake session ------------------------------------------------------------


class _Query:
    def __init__(self, rows, model):
        self._rows = rows
        self._model = model
        self._criteria: list = []
        self._order: list[tuple[str, bool]] = []

    def filter(self, *criteria):
        self._criteria.extend(criteria)
        return self

    def order_by(self, *criteria):
        for criterion in criteria:
            element = getattr(criterion, "element", criterion)
            self._order.append((element.key, criterion is not element))
        return self

    def _matches(self, row):
        if type(row) is not self._model:
            return False
        return all(
            getattr(row, criterion.left.key) == criterion.right.value
            for criterion in self._criteria
        )

    def all(self):
        rows = [row for row in self._rows if self._matches(row)]
        for key, descending in reversed(self._order):
            rows.sort(key=lambda r: getattr(r, key), reverse=descending)
        return rows

    def first(self):
        rows = self.all()
        return rows[0] if rows else None


class _Session:
    """Just enough of a SQLAlchemy session for the router's query surface:

    ``query(model).filter(col == literal).order_by(col)[.all()/.first()]`` and
    ``get(model, (pk1, pk2))`` — every filter in the router is a plain
    equality, which is what keeps this fake honest.
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added: list = []

    def query(self, model):
        return _Query(self.rows, model)

    def get(self, model, pk):
        keys = [column.key for column in model.__mapper__.primary_key]
        if not isinstance(pk, tuple):
            pk = (pk,)
        for row in self.rows:
            if type(row) is model and all(
                getattr(row, key) == value for key, value in zip(keys, pk)
            ):
                return row
        return None

    def add(self, obj):
        self.added.append(obj)


# --- Row builders ------------------------------------------------------------


def _ir_dict(version=3):
    ir = sample_ir_dict()
    ir["version"] = version
    ir["content_hash"] = compute_content_hash(ir)
    return ir


def make_policy_row(state="shadow", version=3):
    ir = _ir_dict(version)
    return CompiledPolicy(
        policy_id=POLICY_ID,
        version=version,
        state=state,
        policy_ir=ir,
        content_hash=ir["content_hash"],
        maturity_evidence=ir["maturity"],
        compiled_at=T0,
        compiled_by="system",
    )


def make_decision_row(
    finding_id="f-1",
    version=3,
    mode="shadow",
    outcome="shadow_logged",
    agreement_source=None,
    agrees=None,
    actual=None,
    evaluated_at=T0,
    row_id=1,
):
    return CompiledPolicyDecision(
        id=row_id,
        finding_id=finding_id,
        policy_id=POLICY_ID,
        policy_version=version,
        content_hash="sha256:" + "0" * 8,
        mode=mode,
        outcome=outcome,
        decision={"severity": "high"},
        actual_decision=actual,
        agreement_source=agreement_source,
        agrees=agrees,
        evaluation_us=42,
        evaluated_at=evaluated_at,
    )


@pytest.fixture()
def session():
    return _Session()


@pytest.fixture()
def client(session, monkeypatch):
    app = FastAPI()
    app.include_router(policies_router, prefix=ROUTER_META.prefix)
    app.dependency_overrides[request_unit_of_work] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username=ACTOR, user_id="u-1"
    )
    # The lifecycle routes sit behind permission_gate("settings.write");
    # check_permission resolves User→Role in the database, which the fake
    # session cannot serve — patch it permissive and cover the deny path
    # explicitly in test_lifecycle_transition_denied_without_the_permission.
    monkeypatch.setattr(
        AuthService, "check_permission", staticmethod(lambda *a, **k: True)
    )
    return TestClient(app)


def test_lifecycle_transition_denied_without_the_permission(
    client, session, monkeypatch
):
    """A signed-in user without settings.write gets 403, not 401."""
    monkeypatch.setattr(
        AuthService, "check_permission", staticmethod(lambda *a, **k: False)
    )
    session.rows.extend([make_policy_row(state="shadow")])
    r = client.post(f"/api/compiled-policies/{POLICY_ID}/promote", json={"version": 3})
    assert r.status_code == 403, r.text
    assert session.rows[0].state == "shadow"


def _swap_session(client, session):
    client.app.dependency_overrides[request_unit_of_work] = lambda: session


# --- List --------------------------------------------------------------------


def test_list_is_empty_before_any_compile(client):
    r = client.get("/api/compiled-policies")
    assert r.status_code == 200, r.text
    assert r.json() == {"policies": [], "total": 0}


def test_list_returns_policies_newest_version_first(client, session):
    session.rows.extend([make_policy_row(version=3), make_policy_row(version=4)])
    r = client.get("/api/compiled-policies")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert [p["version"] for p in body["policies"]] == [4, 3]
    head = body["policies"][0]
    assert head["policy_id"] == POLICY_ID
    assert head["state"] == "shadow"
    assert head["content_hash"].startswith("sha256:")
    assert head["match"]["workflow_id"] == "wf_hunt_cred_stuffing"
    assert head["decision"]["actions_human_only"] is True
    assert head["maturity"]["outcomes"] == {"resolved": 14, "false_positive": 1}


def test_list_filters_by_state(client, session):
    session.rows.extend(
        [
            make_policy_row(state="shadow", version=1),
            make_policy_row(state="active", version=2),
        ]
    )
    r = client.get("/api/compiled-policies", params={"state": "active"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["policies"][0]["version"] == 2


def test_list_rejects_an_unknown_state_value(client):
    r = client.get("/api/compiled-policies", params={"state": "zombie"})
    assert r.status_code == 422, r.text


def test_summary_reports_the_row_state_not_the_document_state(client, session):
    """The row is the lifecycle's writer: a stale document state must not leak."""
    row = make_policy_row(state="shadow")
    row.policy_ir = {**row.policy_ir, "state": "candidate"}
    session.rows.append(row)
    r = client.get("/api/compiled-policies")
    assert r.json()["policies"][0]["state"] == "shadow"


# --- Inspect -----------------------------------------------------------------


def test_inspect_unknown_policy_is_404(client):
    r = client.get(f"/api/compiled-policies/{POLICY_ID}")
    assert r.status_code == 404, r.text


def test_inspect_returns_all_versions_with_head(client, session):
    session.rows.extend(
        [make_policy_row(version=3), make_policy_row(version=4, state="active")]
    )
    r = client.get(f"/api/compiled-policies/{POLICY_ID}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["head"]["version"] == 4
    assert [v["version"] for v in body["versions"]] == [4, 3]


# --- Lifecycle transitions ---------------------------------------------------


def test_promote_moves_shadow_to_active_and_audits(client, session):
    session.rows.append(make_policy_row(state="shadow"))
    r = client.post(f"/api/compiled-policies/{POLICY_ID}/promote", json={"version": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transition"]["action"] == "promote"
    assert body["transition"]["actor"] == ACTOR
    assert body["transition"]["from_state"] == "shadow"
    assert body["transition"]["to_state"] == "active"
    assert body["policy"]["state"] == "active"
    row = session.rows[0]
    assert row.state == "active"
    assert row.promoted_by == ACTOR
    assert row.promoted_at is not None
    # The stored document's state is kept in step with the row.
    assert row.policy_ir["state"] == "active"
    audit = [a for a in session.added if isinstance(a, ConfigAuditLog)]
    assert len(audit) == 1
    assert audit[0].config_type == "compiled_policy"
    assert audit[0].config_key == f"{POLICY_ID}:v3"
    assert audit[0].action == "promote"
    assert audit[0].changed_by == ACTOR
    assert audit[0].new_value["content_hash"] == row.content_hash


def test_promote_accepts_the_expected_content_hash(client, session):
    row = make_policy_row(state="shadow")
    session.rows.append(row)
    r = client.post(
        f"/api/compiled-policies/{POLICY_ID}/promote",
        json={"version": 3, "content_hash": row.content_hash},
    )
    assert r.status_code == 200, r.text


def test_promote_conflicts_when_the_hash_has_changed(client, session):
    session.rows.append(make_policy_row(state="shadow"))
    r = client.post(
        f"/api/compiled-policies/{POLICY_ID}/promote",
        json={"version": 3, "content_hash": "sha256:" + "f" * 8},
    )
    assert r.status_code == 409, r.text
    assert session.rows[0].state == "shadow"


def test_promote_is_only_legal_from_shadow(client):
    for state in ("candidate", "active", "suspended", "retired"):
        fresh = _Session([make_policy_row(state=state)])
        _swap_session(client, fresh)
        r = client.post(
            f"/api/compiled-policies/{POLICY_ID}/promote", json={"version": 3}
        )
        assert r.status_code == 409, (state, r.text)
        assert fresh.rows[0].state == state


def test_suspend_works_from_shadow_and_active(client):
    for state in ("shadow", "active"):
        fresh = _Session([make_policy_row(state=state)])
        _swap_session(client, fresh)
        r = client.post(
            f"/api/compiled-policies/{POLICY_ID}/suspend", json={"version": 3}
        )
        assert r.status_code == 200, (state, r.text)
        assert fresh.rows[0].state == "suspended"
        assert fresh.rows[0].suspended_by == ACTOR
        audit = [a for a in fresh.added if isinstance(a, ConfigAuditLog)]
        assert audit[0].action == "suspend"


def test_rearm_returns_a_suspended_policy_to_shadow_never_active(client, session):
    session.rows.append(make_policy_row(state="suspended"))
    r = client.post(f"/api/compiled-policies/{POLICY_ID}/rearm", json={"version": 3})
    assert r.status_code == 200, r.text
    row = session.rows[0]
    assert row.state == "shadow"
    assert row.rearmed_by == ACTOR
    assert row.rearmed_at is not None


def test_retire_is_reachable_from_every_live_state_and_is_terminal(client):
    for state in ("candidate", "shadow", "active", "suspended"):
        fresh = _Session([make_policy_row(state=state)])
        _swap_session(client, fresh)
        r = client.post(
            f"/api/compiled-policies/{POLICY_ID}/retire", json={"version": 3}
        )
        assert r.status_code == 200, (state, r.text)
        assert fresh.rows[0].state == "retired"
        assert fresh.rows[0].retired_by == ACTOR
        r2 = client.post(
            f"/api/compiled-policies/{POLICY_ID}/retire", json={"version": 3}
        )
        assert r2.status_code == 409, (state, r2.text)


def test_transition_on_an_unknown_policy_or_version_is_404(client, session):
    session.rows.append(make_policy_row(state="shadow"))
    r = client.post(
        "/api/compiled-policies/pol_0000000000000000/promote", json={"version": 3}
    )
    assert r.status_code == 404, r.text
    r = client.post(f"/api/compiled-policies/{POLICY_ID}/promote", json={"version": 9})
    assert r.status_code == 404, r.text


def test_transition_rejects_a_non_positive_version(client):
    r = client.post(f"/api/compiled-policies/{POLICY_ID}/promote", json={"version": 0})
    assert r.status_code == 422, r.text


def test_apply_transition_is_a_pure_state_machine():
    policy = make_policy_row(state="shadow")
    assert apply_transition(policy, "promote", "a") == "active"
    assert apply_transition(policy, "suspend", "a") == "suspended"
    assert apply_transition(policy, "rearm", "a") == "shadow"
    assert apply_transition(policy, "retire", "a") == "retired"
    with pytest.raises(ValueError):
        apply_transition(policy, "promote", "a")


# --- Decisions log -----------------------------------------------------------


def _decision_fixture():
    at = lambda m: datetime(2026, 10, 9, 21, m, tzinfo=timezone.utc)  # noqa: E731
    return [
        make_decision_row(
            "f-1",
            agreement_source="llm",
            agrees=True,
            actual={"severity": "high"},
            evaluated_at=at(0),
            row_id=1,
        ),
        make_decision_row(
            "f-2",
            agreement_source="llm",
            agrees=True,
            actual={"severity": "high"},
            evaluated_at=at(5),
            row_id=2,
        ),
        make_decision_row(
            "f-3",
            agreement_source="llm",
            agrees=False,
            actual={"severity": "low"},
            evaluated_at=at(10),
            row_id=3,
        ),
        make_decision_row(
            "f-4",
            agreement_source="analyst",
            agrees=True,
            actual={"severity": "high"},
            evaluated_at=at(15),
            row_id=4,
        ),
        make_decision_row(
            "f-5", mode="active", outcome="applied", evaluated_at=at(20), row_id=5
        ),
        make_decision_row(
            "f-6", mode="active", outcome="applied", evaluated_at=at(25), row_id=6
        ),
    ]


def test_decisions_unknown_policy_is_404(client):
    r = client.get(f"/api/compiled-policies/{POLICY_ID}/decisions")
    assert r.status_code == 404, r.text


def test_decisions_log_counts_agreement_across_the_whole_log(client, session):
    session.rows.append(make_policy_row(state="shadow"))
    session.rows.extend(_decision_fixture())
    r = client.get(f"/api/compiled-policies/{POLICY_ID}/decisions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 6
    assert body["agreement"] == {
        "by_mode": {"shadow": 4, "active": 2},
        "llm": {"agrees": 2, "disagrees": 1},
        "analyst": {"agrees": 1, "disagrees": 0},
        "pending": 2,
    }
    # Newest first.
    assert [d["finding_id"] for d in body["decisions"]] == [
        "f-6",
        "f-5",
        "f-4",
        "f-3",
        "f-2",
        "f-1",
    ]


def test_decisions_pagination(client, session):
    session.rows.append(make_policy_row(state="shadow"))
    session.rows.extend(_decision_fixture())
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/decisions",
        params={"limit": 2, "offset": 2},
    )
    body = r.json()
    assert body["total"] == 6  # counts cover the whole log, not just the page
    assert [d["finding_id"] for d in body["decisions"]] == ["f-4", "f-3"]


def test_decisions_filter_by_version(client, session):
    session.rows.append(make_policy_row(version=4))
    rows = _decision_fixture()
    rows[0].policy_version = 4
    session.rows.extend(rows)
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/decisions", params={"version": 4}
    )
    body = r.json()
    assert body["total"] == 1
    assert body["agreement"]["llm"]["agrees"] == 1


def test_agreement_counts_treats_missing_actual_outcome_as_pending():
    rows = [
        make_decision_row(agreement_source=None, agrees=None),
        make_decision_row(
            agreement_source="llm", agrees=False, actual={"severity": "low"}
        ),
    ]
    counts = agreement_counts(rows)
    assert counts["pending"] == 1
    assert counts["llm"]["disagrees"] == 1


# --- Export ------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,ext",
    [
        ("rego", "rego"),
        ("snort", "rules"),
        ("suricata", "rules"),
        ("iptables", "conf"),
    ],
)
def test_export_returns_the_rendered_artifact(client, session, fmt, ext):
    session.rows.append(make_policy_row(state="active"))
    r = client.get(f"/api/compiled-policies/{POLICY_ID}/export", params={"format": fmt})
    assert r.status_code == 200, r.text
    assert r.text.strip(), "render must not be empty"
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"] == (
        f'attachment; filename="{POLICY_ID}-v3.{ext}"'
    )
    digest = "sha256:" + hashlib.sha256(r.text.encode("utf-8")).hexdigest()
    assert r.headers["x-vigil-render-sha256"] == digest


def test_export_defaults_to_the_head_version(client, session):
    session.rows.extend([make_policy_row(version=3), make_policy_row(version=4)])
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/export", params={"format": "rego"}
    )
    assert (
        r.headers["content-disposition"]
        == f'attachment; filename="{POLICY_ID}-v4.rego"'
    )


def test_export_explicit_version(client, session):
    session.rows.extend([make_policy_row(version=3), make_policy_row(version=4)])
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/export",
        params={"format": "rego", "version": 3},
    )
    assert (
        r.headers["content-disposition"]
        == f'attachment; filename="{POLICY_ID}-v3.rego"'
    )


def test_export_unknown_version_is_404(client, session):
    session.rows.append(make_policy_row(version=3))
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/export",
        params={"format": "rego", "version": 9},
    )
    assert r.status_code == 404, r.text


def test_export_unknown_format_is_422_not_a_fallback_render(client, session):
    session.rows.append(make_policy_row(state="active"))
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/export", params={"format": "nginx"}
    )
    assert r.status_code == 422, r.text


def test_export_of_a_tampered_row_is_500_not_a_render(client, session):
    row = make_policy_row(state="active")
    row.policy_ir = {**row.policy_ir, "content_hash": "sha256:" + "0" * 64}
    session.rows.append(row)
    r = client.get(
        f"/api/compiled-policies/{POLICY_ID}/export", params={"format": "rego"}
    )
    assert r.status_code == 500, r.text
    assert "failed validation" in r.json()["detail"]


# --- Console-only placement: never under the frozen v1 surface ---------------


def test_v1_contract_snapshot_has_no_compiled_policies():
    snapshot_path = REPO / "core" / "api" / "v1" / "contract.snapshot.json"
    committed = json.loads(snapshot_path.read_text())
    assert "compiled-policies" not in json.dumps(committed)


def test_v1_package_never_references_the_policy_compiler():
    v1_dir = REPO / "core" / "api" / "v1"
    for source in sorted(v1_dir.glob("*.py")):
        text = source.read_text()
        assert "policy_compiler" not in text, source
        assert "compiled_policies" not in text, source

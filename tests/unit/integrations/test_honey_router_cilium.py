"""CiliumBackend route/unroute behavior against a fake Kubernetes client.

The backend lazy-imports ``kubernetes`` inside ``_k8s()``; these tests
inject a fake package into ``sys.modules`` so the no-DB CI job can run
them without the real client (and prove the failure paths that real
installs hit: missing package, no cluster config, absent Cilium CRD,
API errors).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
import yaml

from core.integrations.honey_router import route as hr
from core.integrations.honey_router.route import (
    CILIUM_LRP_PLURAL,
    CiliumBackend,
    DecoyTarget,
)

DECOY = DecoyTarget(
    decoy_id="decoy-ssh-01",
    name="SSH decoy",
    kind="ssh",
    endpoint_host="10.42.0.77",
    endpoint_port=2222,
    namespace="vigil-decoys",
)
ATTACKER = "203.0.113.7"


class FakeApiException(Exception):
    def __init__(self, status, reason=""):
        self.status = status
        self.reason = reason or str(status)
        super().__init__(self.reason)


class FakeCustomObjectsApi:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.create_side_effect = None
        self.delete_side_effect = None

    def create_namespaced_custom_object(self, group, version, namespace, plural, body):
        if self.create_side_effect is not None:
            raise self.create_side_effect
        self.created.append(body)
        return body

    def delete_namespaced_custom_object(self, group, version, namespace, plural, name):
        if self.delete_side_effect is not None:
            raise self.delete_side_effect
        self.deleted.append(name)
        return {}


def _raise(exc):
    raise exc


def _fail_config(*args, **kwargs):
    raise FileNotFoundError("no cluster configuration")


def _fake_kubernetes(crd_status=200):
    """A fake ``kubernetes`` package: client + config modules."""
    custom_api = FakeCustomObjectsApi()

    def read_crd(name):
        assert name == "ciliumlocalredirectpolicies.cilium.io"
        if crd_status == 200:
            return {"metadata": {"name": name}}
        _raise(
            FakeApiException(
                crd_status, "Not Found" if crd_status == 404 else "Server Error"
            )
        )

    client = types.SimpleNamespace(
        ApiException=FakeApiException,
        CustomObjectsApi=lambda: custom_api,
        ApiextensionsV1Api=lambda: types.SimpleNamespace(
            read_custom_resource_definition=read_crd
        ),
    )
    config = types.SimpleNamespace(
        load_incluster_config=lambda *a, **k: None,  # in-cluster: success
        load_kube_config=_fail_config,
    )
    return types.SimpleNamespace(client=client, config=config), custom_api


@pytest.fixture()
def fake_k8s(monkeypatch):
    fake, custom_api = _fake_kubernetes()
    monkeypatch.setitem(sys.modules, "kubernetes", fake)
    return custom_api


class TestCiliumBackendRoute:
    def test_route_creates_the_policy_and_reports_success(self, fake_k8s):
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is True
        assert result["backend"] == "cilium"
        assert result["policy"].startswith("vigil-honey-")
        assert len(fake_k8s.created) == 1
        manifest = fake_k8s.created[0]
        assert manifest["apiVersion"] == "cilium.io/v2"
        assert manifest["kind"] == "CiliumLocalRedirectPolicy"

    def test_route_fails_without_kubernetes_package(self, monkeypatch):
        # sys.modules['kubernetes'] = None simulates "package not installed":
        # the from-import raises ImportError, which must surface as a
        # structured failure — never an exception escaping to the executor.
        monkeypatch.setitem(sys.modules, "kubernetes", None)
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is False
        assert result["error"] == "k8s_client_unavailable"

    def test_route_fails_when_no_cluster_config_exists(self, monkeypatch):
        fake, _ = _fake_kubernetes()
        fake.config.load_incluster_config = _fail_config
        fake.config.load_kube_config = _fail_config
        monkeypatch.setitem(sys.modules, "kubernetes", fake)
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is False
        assert result["error"] == "k8s_client_unavailable"
        assert "no kubernetes configuration available" in result["message"]

    def test_route_fails_loudly_when_the_cilium_crd_is_absent(self, monkeypatch):
        fake, custom_api = _fake_kubernetes(crd_status=404)
        monkeypatch.setitem(sys.modules, "kubernetes", fake)
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is False
        assert result["error"] == "cilium_crd_unavailable"
        assert "does not run Cilium" in result["message"]
        assert custom_api.created == []  # nothing half-applied

    def test_route_reports_api_errors_as_failures(self, fake_k8s):
        fake_k8s.create_side_effect = FakeApiException(422, "Unprocessable")
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is False
        assert result["error"] == "cilium_api_error"
        assert "Unprocessable" in result["message"]

    def test_existing_policy_is_a_truthful_success(self, fake_k8s):
        # 409 = the policy already exists: the route IS in effect. Recording
        # a failure would fabricate a problem; the row stays honest.
        fake_k8s.create_side_effect = FakeApiException(409, "Conflict")
        result = CiliumBackend().route(ATTACKER, DECOY)
        assert result["success"] is True
        assert result["already_existed"] is True


class TestCiliumBackendUnroute:
    def test_unroute_deletes_the_policy(self, fake_k8s):
        result = CiliumBackend().unroute(ATTACKER)
        assert result["success"] is True
        assert fake_k8s.deleted == [hr.policy_name_for(ATTACKER)]

    def test_unroute_of_an_already_gone_policy_is_success(self, fake_k8s):
        # Fail-safe direction: restoring the normal path is the goal, and
        # it holds either way — never an error, never a rethrow.
        fake_k8s.delete_side_effect = FakeApiException(404, "Not Found")
        result = CiliumBackend().unroute(ATTACKER)
        assert result["success"] is True
        assert result["already_gone"] is True

    def test_unroute_reports_api_errors_as_failures(self, fake_k8s):
        fake_k8s.delete_side_effect = FakeApiException(500, "Internal Server Error")
        result = CiliumBackend().unroute(ATTACKER)
        assert result["success"] is False
        assert result["error"] == "cilium_api_error"


class TestPluralConstant:
    def test_plural_matches_the_vendored_crd_resource(self):
        # The create/delete calls key off the plural; the vendored CRD is
        # the ground truth for it.
        crd = yaml.safe_load(
            (Path(__file__).parent / "fixtures/cilium-lrp-crd.yaml").read_text()
        )
        assert crd["spec"]["names"]["plural"] == CILIUM_LRP_PLURAL
        assert CILIUM_LRP_PLURAL in crd["metadata"]["name"]

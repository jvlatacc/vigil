"""The Cloudflare Containers manifest has to agree with the repo it deploys.

``infra/cloudflare/containers/python-tier.json`` is read by deploy tooling that
never sees this codebase: it renders wrangler's ``containers[]`` from names,
ports, images and env listed there. A port that drifts from the Dockerfile's
EXPOSE, or an env var that no longer exists, produces a container that starts
and then fails to serve -- the kind of break that only shows up after a deploy.

These tests are the cheap version of that feedback: they assert the manifest
against the Dockerfiles and ``env.example``, and they load both Python entry
points the manifest claims are loadable.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "infra" / "cloudflare" / "containers" / "python-tier.json"
ENV_EXAMPLE_PATH = REPO_ROOT / "env.example"

# Cloudflare's published Container instance types (developers.cloudflare.com/
# containers/platform-details/limits/). Anything outside this set is a typo that
# wrangler would reject at deploy time.
KNOWN_INSTANCE_TYPES = frozenset(
    {"lite", "basic", "standard-1", "standard-2", "standard-3", "standard-4"}
)
KEEP_ALIVE_STRATEGIES = frozenset({"request", "cron-ping"})
DURATION_RE = re.compile(r"^\d+(s|m|h)$")


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _exposed_ports(dockerfile: Path) -> set[int]:
    """Ports the image advertises, from every EXPOSE line in the Dockerfile."""
    ports: set[int] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("EXPOSE "):
            continue
        for token in stripped.split()[1:]:
            port = token.split("/", 1)[0]
            if port.isdigit():
                ports.add(int(port))
    return ports


def _documented_env_names() -> set[str]:
    """Env var names env.example documents, commented-out defaults included."""
    names: set[str] = set()
    pattern = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=")
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            names.add(match.group(1))
    return names


MANIFEST = _load_manifest()
CONTAINERS = MANIFEST["containers"]
DOCUMENTED_ENV = _documented_env_names()


def _container_ids() -> list[str]:
    return [container["name"] for container in CONTAINERS]


@pytest.fixture(params=CONTAINERS, ids=_container_ids())
def container(request: pytest.FixtureRequest) -> dict[str, Any]:
    return request.param


def test_manifest_schema_version_is_current() -> None:
    assert MANIFEST["schema_version"] == 1


def test_container_names_and_bindings_are_unique() -> None:
    names = [c["name"] for c in CONTAINERS]
    class_names = [c["class_name"] for c in CONTAINERS]
    bindings = [c["binding"] for c in CONTAINERS]

    assert len(set(names)) == len(names)
    assert len(set(class_names)) == len(class_names)
    assert len(set(bindings)) == len(bindings)


def test_container_dockerfile_exists(container: dict[str, Any]) -> None:
    dockerfile = REPO_ROOT / container["image"]["dockerfile"]
    assert dockerfile.is_file(), f"{container['name']} names a missing Dockerfile"


def test_container_ports_are_exposed_by_its_image(container: dict[str, Any]) -> None:
    """Every port the manifest routes to must be a port the image advertises."""
    dockerfile = REPO_ROOT / container["image"]["dockerfile"]
    exposed = _exposed_ports(dockerfile)

    for port in container["required_ports"]:
        assert port in exposed, (
            f"{container['name']} requires port {port}, which "
            f"{container['image']['dockerfile']} does not EXPOSE ({sorted(exposed)})"
        )

    default_port = container["default_port"]
    if default_port is not None:
        assert default_port in container["required_ports"]


def test_container_env_is_documented(container: dict[str, Any]) -> None:
    """A required env var that env.example never mentions cannot be supplied."""
    undocumented = [name for name in container["required_env"] if name not in DOCUMENTED_ENV]
    assert not undocumented, (
        f"{container['name']} requires env vars absent from env.example: {undocumented}"
    )


def test_container_instance_type_is_a_real_cloudflare_type(container: dict[str, Any]) -> None:
    assert container["instance_type"] in KNOWN_INSTANCE_TYPES


def test_singleton_containers_are_capped_at_one_instance(container: dict[str, Any]) -> None:
    """The daemon's loops, pollers and consumer-group seat tolerate exactly one."""
    if container["singleton"]:
        assert container["max_instances"] == 1, (
            f"{container['name']} is a singleton but allows "
            f"{container['max_instances']} instances"
        )
    else:
        assert container["max_instances"] >= 1


def test_container_lifecycle_is_declared(container: dict[str, Any]) -> None:
    assert container["keep_alive"] in KEEP_ALIVE_STRATEGIES
    assert DURATION_RE.match(container["sleep_after"]), (
        f"{container['name']} sleep_after must look like 30s/20m/1h"
    )


def test_portless_containers_do_not_rely_on_request_activity(
    container: dict[str, Any],
) -> None:
    """No port means no requests, so nothing would ever renew the sleep timer."""
    if not container["required_ports"]:
        assert container["keep_alive"] == "cron-ping", (
            f"{container['name']} serves no port and cannot be kept awake by requests"
        )


def test_daemon_owns_the_kafka_consumer_group_seat() -> None:
    """Kafka stays in the daemon process; the manifest must not fan it out."""
    daemon = next(c for c in CONTAINERS if c["name"] == "vigil-daemon")
    assert daemon["singleton"] is True
    assert "consumer group" in daemon["singleton_note"].lower()

    kafka_env = set(MANIFEST["external_services"]["kafka"]["env"])
    assert "KAFKA_BOOTSTRAP_SERVERS" in kafka_env
    assert kafka_env <= DOCUMENTED_ENV


def test_external_services_are_documented_and_reachable() -> None:
    external = MANIFEST["external_services"]
    for service in ("postgres", "redis", "kafka"):
        entry = external[service]
        assert entry["reachable_from"], f"{service} declares no reachability"
        undocumented = [name for name in entry["env"] if name not in DOCUMENTED_ENV]
        assert not undocumented, f"{service} names undocumented env: {undocumented}"


def test_state_mode_is_one_of_the_declared_modes() -> None:
    """The workdir decision is open, so both modes stay selectable and named."""
    state = MANIFEST["state"]
    assert state["mode"] in state["modes"]
    assert state["workdir_env"] in DOCUMENTED_ENV
    assert state["state_dir_env"] in DOCUMENTED_ENV


def test_smoke_targets_exist(container: dict[str, Any]) -> None:
    smoke = container["smoke"]
    if smoke is None:
        return
    if smoke["kind"] == "file":
        assert (REPO_ROOT / smoke["target"]).is_file()
    else:
        assert importlib.util.find_spec(smoke["target"]) is not None


def _apply_smoke_env(smoke: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in smoke["env"].items():
        monkeypatch.setenv(name, value)


def test_manifest_entry_points_load(
    container: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container smoke test, run against the source tree.

    CI repeats this inside the built images; here it catches an import-time
    break (or a manifest that points at the wrong entry point) without a build.
    """
    smoke = container["smoke"]
    if smoke is None:
        pytest.skip(f"{container['name']} declares no smoke entry point")

    _apply_smoke_env(smoke, monkeypatch)

    if smoke["kind"] == "file":
        path = REPO_ROOT / smoke["target"]
        spec = importlib.util.spec_from_file_location(
            f"smoke_{container['name'].replace('-', '_')}", path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(smoke["target"])

    attribute = smoke.get("attribute")
    if attribute:
        assert getattr(module, attribute, None) is not None, (
            f"{container['name']} entry point lacks {attribute}"
        )

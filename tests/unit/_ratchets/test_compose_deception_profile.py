"""The deception compose profile: contained decoys, inert by default.

The farm is honeypot infrastructure. Containment regressions this ratchet
exists to catch: a decoy attached to the production network (the decoy-net-
only invariant), a writable rootfs, missing resource caps, published ports
(the farm is reachable only through the steering controller), a farm service
that starts on a default `docker compose up` (profiles other than
`deception`), and a hardcoded credential.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO / "infra" / "docker" / "docker-compose.yml"

FARM_SERVICES = (
    "decoy-controller",
    "decoy-cowrie",
    "decoy-opencanary",
    "decoy-samba",
    "decoy-http",
    "decoy-shipper",
)
# Containment invariants apply to the decoys + shipper. The controller is
# enforcement, not bait: it is deliberately dual-homed and its nftables
# driver needs NET_ADMIN, so `cap_drop: ALL` would contradict its own docs.
DECOYS = ("decoy-cowrie", "decoy-opencanary", "decoy-samba", "decoy-http")
HARDENED = DECOYS + ("decoy-shipper",)
# The fake app listens unprivileged on 8080; port 80 is what steering maps in.
DECOY_ADDRESSES = {
    "decoy-http": "10.0.5.10",
    "decoy-cowrie": "10.0.5.11",
    "decoy-opencanary": "10.0.5.12",
    "decoy-samba": "10.0.5.13",
}


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8")) or {}


def _services() -> dict:
    return _compose().get("services") or {}


def _network_names(spec: dict) -> set:
    networks = spec.get("networks") or []
    if isinstance(networks, dict):
        return set(networks)
    return set(networks)


@pytest.mark.parametrize("name", FARM_SERVICES)
def test_farm_service_is_behind_the_deception_profile_only(name):
    spec = _services().get(name)
    assert spec is not None, f"{name} missing from compose"
    assert spec.get("profiles") == [
        "deception"
    ], f"{name} must be `profiles: [deception]` exactly, got {spec.get('profiles')!r}"


@pytest.mark.parametrize("name", DECOYS)
def test_decoy_attaches_only_to_the_decoy_net(name):
    networks = _network_names(_services()[name])
    assert networks == {
        "decoy-net"
    }, f"{name} must attach to decoy-net only, got {networks}"


def test_controller_reaches_both_planes():
    networks = _network_names(_services()["decoy-controller"])
    assert networks == {"deeptempo-network", "decoy-net"}


def test_shipper_is_the_only_farm_service_on_the_production_network():
    networks = _network_names(_services()["decoy-shipper"])
    assert networks == {"deeptempo-network"}


def test_decoy_net_is_internal():
    net = (_compose().get("networks") or {}).get("decoy-net") or {}
    assert net.get("internal") is True, "decoy-net must deny egress (internal: true)"


def test_decoy_net_has_fixed_addressing():
    config = (
        ((_compose().get("networks") or {}).get("decoy-net") or {})
        .get("ipam", {})
        .get("config", [])
    )
    assert any(c.get("subnet") == "10.0.5.0/24" for c in config), (
        "the decoy-controller's decoy map targets static decoy addresses; "
        "the subnet must stay fixed"
    )


@pytest.mark.parametrize("name", DECOYS)
def test_decoy_has_its_static_address(name):
    spec = _services()[name]
    address = (spec.get("networks") or {}).get("decoy-net", {}).get("ipv4_address")
    assert address == DECOY_ADDRESSES[name], f"{name} must hold {DECOY_ADDRESSES[name]}"


@pytest.mark.parametrize("name", HARDENED)
def test_farm_container_is_hardened(name):
    spec = _services()[name]
    assert spec.get("read_only") is True, f"{name} must run a read-only rootfs"
    assert "ALL" in (spec.get("cap_drop") or []), f"{name} must drop all capabilities"
    assert spec.get("pids_limit"), f"{name} must cap its process count"
    limits = (spec.get("deploy") or {}).get("resources", {}).get("limits") or {}
    assert limits.get("cpus") and limits.get(
        "memory"
    ), f"{name} must cap cpu and memory"


@pytest.mark.parametrize("name", HARDENED)
def test_farm_ships_no_published_ports(name):
    spec = _services()[name]
    assert not spec.get("ports"), (
        f"{name} must publish nothing: the farm is reachable only through "
        "the steering controller"
    )


def test_shipper_mounts_decoy_logs_read_only():
    mounts = _services()["decoy-shipper"].get("volumes") or []
    decoy_mounts = [m for m in mounts if "decoy_logs" in str(m).split(":")[0]]
    assert decoy_mounts, "the shipper must read the decoy log volumes"
    for mount in decoy_mounts:
        assert str(mount).endswith(
            ":ro"
        ), f"shipper mount {mount!r} must be read-only: telemetry flows one way"


def test_no_secrets_mounted_or_hardcoded_in_the_farm():
    for name in FARM_SERVICES:
        spec = _services()[name]
        for mount in spec.get("volumes") or []:
            assert "docker.sock" not in str(mount), f"{name} must not mount docker.sock"
            assert "secret" not in str(mount).lower(), f"{name} must not mount secrets"
        for key, value in (spec.get("environment") or {}).items():
            if "TOKEN" in str(key):
                assert "${" in str(value), (
                    f"{name} env {key} must come from the environment "
                    f"(interpolated), not a hardcoded value"
                )


def test_cowrie_image_is_digest_pinned():
    image = _services()["decoy-cowrie"].get("image") or ""
    assert image.startswith(
        "cowrie/cowrie@sha256:"
    ), f"cowrie image must be digest-pinned for a reproducible honeypot, got {image!r}"


def test_decoy_controller_map_defaults_reach_the_farm():
    env = _services()["decoy-controller"].get("environment") or {}
    decoy_map = str(env.get("DECOY_CONTROLLER_DECOY_MAP", ""))
    # Every decoy the farm stands up is steerable by default.
    assert "2222=10.0.5.11" in decoy_map  # cowrie ssh
    assert "2223=10.0.5.11" in decoy_map  # cowrie telnet
    assert "445=10.0.5.13" in decoy_map  # samba
    assert "80=10.0.5.10:8080" in decoy_map  # fake app

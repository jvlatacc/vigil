"""Compose and Helm have to render the Cloudflare topology, not almost render it.

The Cloudflare path means one thing structurally: the Python tier runs, and no
datastore runs beside it. Both statements are easy to break by accident -- a
copied service block reintroduces an in-compose Postgres, a flipped default puts
the in-chart StatefulSet back -- and neither break is visible until something
connects to the wrong database.

These tests read the two topology files as data. They do not shell out to
``docker compose config`` or ``helm template``: neither binary is available in
this test environment, and the properties worth protecting (which services
exist, which datastores are external, which variables are required) are
structural rather than semantic. Chart rendering itself is covered by the Helm
workflow, which runs ``helm template`` with these values.

The last test is the one that matters during cutover: the legacy in-cluster path
must still be intact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CF_COMPOSE_PATH = REPO_ROOT / "infra" / "docker" / "docker-compose.cloudflare.yml"
LEGACY_COMPOSE_PATH = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
CHART_DIR = REPO_ROOT / "infra" / "helm" / "vigil"
CF_VALUES_PATH = CHART_DIR / "values-cloudflare.yaml"
LEGACY_VALUES_PATH = CHART_DIR / "values.yaml"

# The Python tier, and nothing else. The TypeScript agent runs on Workers in
# this topology, so agent-serve/agent-worker are deliberately absent too.
EXPECTED_CF_SERVICES = frozenset({"backend", "soc-daemon", "llm-worker"})

# Anything that stores state or collects telemetry belongs outside the tier:
# a Container accepts no non-HTTP inbound connection and its disk is ephemeral.
FORBIDDEN_CF_SERVICES = frozenset(
    {
        "postgres",
        "postgresql",
        "redis",
        "kafka",
        "zookeeper",
        "otel-collector",
        "jaeger",
        "prometheus",
        "grafana",
        "pgadmin",
        "splunk",
    }
)

# Variables with no safe default. A default endpoint points a developer at a
# datastore that does not exist; a default secret is worse.
REQUIRED_COMPOSE_VARS = ("POSTGRES_HOST", "POSTGRES_PASSWORD", "REDIS_URL", "JWT_SECRET_KEY")


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cf_compose() -> dict[str, Any]:
    return _load_yaml(CF_COMPOSE_PATH)


@pytest.fixture(scope="module")
def cf_values() -> dict[str, Any]:
    return _load_yaml(CF_VALUES_PATH)


# ---------------------------------------------------------------------------
# Compose: the Cloudflare topology
# ---------------------------------------------------------------------------


def test_cf_compose_declares_exactly_the_python_tier(cf_compose: dict[str, Any]) -> None:
    assert set(cf_compose["services"]) == set(EXPECTED_CF_SERVICES)


def test_cf_compose_starts_no_datastore_or_telemetry_backend(
    cf_compose: dict[str, Any],
) -> None:
    intruders = FORBIDDEN_CF_SERVICES & set(cf_compose["services"])
    assert not intruders, (
        f"{sorted(intruders)} cannot run as a Cloudflare Container: no non-HTTP "
        "inbound, ephemeral disk. Point the tier at a managed endpoint instead."
    )


def test_cf_compose_requires_connection_variables(cf_compose: dict[str, Any]) -> None:
    """``${VAR:?message}`` fails the render; ``${VAR:-default}`` hides the mistake."""
    rendered = CF_COMPOSE_PATH.read_text(encoding="utf-8")
    for var in REQUIRED_COMPOSE_VARS:
        assert f"${{{var}:?" in rendered, (
            f"{var} has no safe default in the Cloudflare topology -- use "
            f"${{{var}:?...}} so a missing value fails at render time"
        )
    # Guard the inverse: a later edit must not soften one of these to a default.
    for var in REQUIRED_COMPOSE_VARS:
        assert f"${{{var}:-" not in rendered, f"{var} must not carry a default"


def test_cf_compose_pins_the_daemon_to_one_replica(cf_compose: dict[str, Any]) -> None:
    """Its loops and its Kafka consumer-group seat live in one process."""
    daemon = cf_compose["services"]["soc-daemon"]
    assert daemon["deploy"]["replicas"] == 1


def test_cf_compose_builds_images_from_the_repo_root(cf_compose: dict[str, Any]) -> None:
    """Both Dockerfiles COPY core/, services/ and mempalace/."""
    for name, service in cf_compose["services"].items():
        build = service["build"]
        assert build["context"] == "../..", f"{name} needs the repo root as context"
        assert build["dockerfile"].startswith("infra/docker/Dockerfile."), name


def test_cf_compose_persists_the_daemon_workdir(cf_compose: dict[str, Any]) -> None:
    """A bare container loses in-flight investigations on every restart."""
    daemon = cf_compose["services"]["soc-daemon"]
    workdir = daemon["environment"]["ORCHESTRATOR_WORKDIR"]
    mount_target = workdir.split(":-")[-1].rstrip("}")
    targets = [entry.split(":")[1] for entry in daemon["volumes"]]
    assert mount_target in targets, f"nothing is mounted at {mount_target}"
    volume_names = {entry.split(":")[0] for entry in daemon["volumes"]}
    assert volume_names <= set(cf_compose["volumes"]), "volume is not declared"


def test_cf_compose_disables_the_inherited_healthcheck_on_the_queue_worker(
    cf_compose: dict[str, Any],
) -> None:
    """It runs the backend image, whose HEALTHCHECK curls an HTTP port it never opens."""
    worker = cf_compose["services"]["llm-worker"]
    assert worker["healthcheck"]["disable"] is True
    assert worker["command"] == ["python", "-m", "services.worker"]


# ---------------------------------------------------------------------------
# Helm: the Cloudflare values profile
# ---------------------------------------------------------------------------


def test_cf_values_externalize_every_stateful_service(cf_values: dict[str, Any]) -> None:
    assert cf_values["postgresql"]["enabled"] is False
    assert cf_values["postgresql"]["bitnami"]["enabled"] is False
    assert cf_values["redis"]["enabled"] is False
    assert cf_values["redis"]["bitnami"]["enabled"] is False


def test_cf_values_leave_external_endpoints_empty_on_purpose(
    cf_values: dict[str, Any],
) -> None:
    """The chart raises `required` on these, which is the failure we want: at
    install time, naming the missing value -- not at runtime, as a timeout."""
    assert cf_values["postgresql"]["external"]["host"] == ""
    assert cf_values["redis"]["external"]["url"] == ""
    assert cf_values["config"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == ""


def test_cf_values_require_tls_to_managed_postgres(cf_values: dict[str, Any]) -> None:
    """Findings and IOCs cross the public internet on this connection."""
    assert cf_values["postgresql"]["external"]["sslRequired"] is True


def test_cf_values_drop_the_in_cluster_telemetry_stack(cf_values: dict[str, Any]) -> None:
    assert cf_values["otelCollector"]["enabled"] is False
    assert cf_values["observability"]["serviceMonitor"]["enabled"] is False
    assert cf_values["config"]["VIGIL_OTEL_ENABLED"] == "true"


def test_cf_values_drop_dev_only_extras(cf_values: dict[str, Any]) -> None:
    assert cf_values["splunk"]["enabled"] is False
    assert cf_values["pgadmin"]["enabled"] is False


def test_cf_values_keep_the_daemon_volume_at_the_legacy_size(
    cf_values: dict[str, Any],
) -> None:
    """The Containers-side equivalent is the manifest's `state` block, which is
    still configurable pending the stateDirectory inventory."""
    assert cf_values["daemon"]["persistence"]["enabled"] is True
    assert cf_values["daemon"]["persistence"]["size"] == "10Gi"


# ---------------------------------------------------------------------------
# The legacy path survives until cutover
# ---------------------------------------------------------------------------


def test_legacy_compose_still_starts_its_own_datastores() -> None:
    legacy = _load_yaml(LEGACY_COMPOSE_PATH)
    assert {"postgres", "redis"} <= set(legacy["services"]), (
        "docker-compose.yml is the self-contained path; the Cloudflare topology "
        "lives in docker-compose.cloudflare.yml and does not replace it"
    )


def test_legacy_values_still_default_to_in_chart_datastores() -> None:
    legacy = _load_yaml(LEGACY_VALUES_PATH)
    assert legacy["postgresql"]["enabled"] is True
    assert legacy["redis"]["enabled"] is True

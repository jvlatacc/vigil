"""Runtime-fetched MCP servers must pin an exact artifact, not registry HEAD.

npx / uvx / docker entries in mcp-config.json download code at process start.
An unpinned spec, a version range, @latest, or a git default branch makes two
identical deploys diverge and is a supply-chain footgun. In-repo python3
servers are not registry resolves and are left alone. A local ``uv
--directory`` clone is not a registry resolve either, but it is still code the
host runs, so its setup note must check the clone out at a full commit SHA.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.integrations.mcp.packaged import npm_version, npx_package, uvx_specs

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MCP_CONFIG = _REPO_ROOT / "mcp-config.json"

# Concrete versions only: 1.2.3, 2025.4.8. Dist-tags, x-ranges, and pre-releases
# are not pins.
_EXACT_VERSION = re.compile(r"^[0-9]+(\.[0-9]+)*$")
_EXACT_PYPI = re.compile(r"==([0-9]+(?:\.[0-9]+)*)$")
_GIT_REF = re.compile(r"\.git@([^#]+)$")
# A pin is a full commit SHA. Tags and branch names are server-side mutable:
# the target of v0.7.0 can be re-pointed after a compromise, so a tag is not
# a pin, and neither is a short SHA.
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_GIT_CLONE_URL = re.compile(r"git clone (?P<url>\S+?\.git)")
_GIT_CHECKOUT_SHA = re.compile(r"git checkout [0-9a-f]{40}\b")
_SHA256 = re.compile(r"@sha256:[0-9a-f]{64}$")
_MCP_REMOTE_PATCH = re.compile(r"^0\.1\.(\d+)$")

_DOCKER_VALUE_FLAGS = {
    "-e",
    "--env",
    "-v",
    "--volume",
    "-w",
    "--workdir",
    "--name",
    "-u",
    "--user",
    "--platform",
    "-p",
    "--publish",
}


def _servers() -> dict[str, dict]:
    raw = json.loads(_MCP_CONFIG.read_text())["mcpServers"]
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def _npm_pinned(spec: str) -> bool:
    version = npm_version(spec)
    return bool(version) and bool(_EXACT_VERSION.fullmatch(version))


def _git_pinned(spec: str) -> bool:
    match = _GIT_REF.search(spec.split("#", 1)[0])
    if not match:
        return False
    return bool(_FULL_SHA.fullmatch(match.group(1)))


def _pypi_or_git_pinned(spec: str) -> bool:
    if spec.startswith("git+") or "git+" in spec:
        return _git_pinned(spec)
    return bool(_EXACT_PYPI.search(spec))


def _uvx_unpinned(args: list[str]) -> list[str]:
    """Return package specs that are missing an exact pin."""
    spec, with_specs, _, _ = uvx_specs(args)
    return [s for s in [*with_specs, spec] if s and not _pypi_or_git_pinned(s)]


def _docker_image(args: list[str]) -> str | None:
    skip_next = False
    images: list[str] = []
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in _DOCKER_VALUE_FLAGS:
            skip_next = True
            continue
        if arg.startswith("-") or arg == "run":
            continue
        images.append(arg)
    return images[-1] if images else None


def _mcp_remote_in_cve_window(version: str) -> bool:
    """CVE-2025-6514 is fixed in 0.1.16; stay on exact 0.1.N with N >= 16."""
    match = _MCP_REMOTE_PATCH.fullmatch(version)
    return bool(match) and int(match.group(1)) >= 16


@pytest.mark.unit
@pytest.mark.parametrize(
    "spec, ok",
    [
        ("pkg@1.2.3", True),
        ("@scope/pkg@2025.4.8", True),
        ("pkg", False),
        ("pkg@latest", False),
        ("pkg@Latest", False),
        ("pkg@next", False),
        ("pkg@^0.1.16", False),
        ("pkg@0.1.x", False),
    ],
)
def test_npm_pin_helper(spec: str, ok: bool):
    assert _npm_pinned(spec) is ok


@pytest.mark.unit
@pytest.mark.parametrize(
    "spec, ok",
    [
        ("falcon-mcp==0.19.0", True),
        ("falcon-mcp==latest", False),
        ("mcp<2", False),
        ("mcp==1.29.1", True),
        (
            "git+https://github.com/org/repo.git@07d4992089b10affff6163f296b1f6cb5734539f",
            True,
        ),
        ("git+https://github.com/org/repo.git@v0.7.0", False),
        ("git+https://github.com/org/repo.git@07d4992", False),
        ("git+https://github.com/org/repo.git", False),
        ("git+https://github.com/org/repo.git@HEAD", False),
        ("git+https://github.com/org/repo.git@main", False),
        ("git+https://github.com/org/repo.git@refs/heads/main", False),
    ],
)
def test_pypi_or_git_pin_helper(spec: str, ok: bool):
    assert _pypi_or_git_pinned(spec) is ok


@pytest.mark.unit
def test_runtime_fetched_mcp_servers_are_pinned():
    unpinned: dict[str, str] = {}
    inspected = 0
    for name, config in _servers().items():
        command = config.get("command")
        args = [a for a in config.get("args") or [] if isinstance(a, str)]
        if command == "npx":
            inspected += 1
            package = npx_package(args)[0]
            if not package or not _npm_pinned(package):
                unpinned[name] = package or "(missing npx package)"
        elif command == "uvx":
            inspected += 1
            leftover = _uvx_unpinned(args)
            if leftover:
                unpinned[name] = ", ".join(leftover)
        elif command == "docker":
            inspected += 1
            image = _docker_image(args)
            if not image or not _SHA256.search(image):
                unpinned[name] = image or "(missing docker image)"

    assert inspected >= 15, (
        "expected to inspect npx/uvx/docker MCP servers; the ratchet is "
        f"vacuous if launchers were renamed ({inspected} found)"
    )
    assert not unpinned, (
        "runtime-fetched MCP servers must pin an exact version, git commit SHA, "
        "or image digest — not @latest, a range, a tag, or git HEAD:\n"
        + "\n".join(f"  {name}: {detail}" for name, detail in sorted(unpinned.items()))
    )


@pytest.mark.unit
def test_mcp_remote_stays_inside_the_0_1_cve_window():
    """CVE-2025-6514 is fixed in 0.1.16; jumping to 0.8.x is a separate decision."""
    offenders: dict[str, str] = {}
    found = 0
    for name, config in _servers().items():
        for arg in config.get("args") or []:
            if not isinstance(arg, str) or not arg.startswith("mcp-remote"):
                continue
            found += 1
            version = npm_version(arg) or ""
            if not _mcp_remote_in_cve_window(version):
                offenders[name] = arg
    assert found >= 3, (
        "expected several mcp-remote specs; the CVE pin ratchet is vacuous "
        f"if they were renamed ({found} found)"
    )
    assert not offenders, (
        "mcp-remote must stay on an exact 0.1.N pin with N>=16 "
        f"(CVE-2025-6514 window), not a range or 0.8.x: {offenders}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "version, ok",
    [
        ("0.1.16", True),
        ("0.1.49", True),
        ("0.1.15", False),
        ("0.1.0", False),
        ("0.1.x", False),
        ("0.8.3", False),
        ("^0.1.16", False),
    ],
)
def test_mcp_remote_cve_window_helper(version: str, ok: bool):
    assert _mcp_remote_in_cve_window(version) is ok


@pytest.mark.unit
def test_uv_directory_clones_are_pinned_to_a_commit():
    """A local ``uv --directory`` clone is code the host runs. Its setup note
    must check the clone out at a full commit SHA — a default-branch checkout
    floats exactly like an unpinned registry resolve."""
    inspected = 0
    offenders: dict[str, str] = {}
    for name, config in _servers().items():
        args = [a for a in config.get("args") or [] if isinstance(a, str)]
        if config.get("command") != "uv" or "--directory" not in args:
            continue
        inspected += 1
        notes = " ".join(
            str(v) for v in (config.get("env") or {}).values() if isinstance(v, str)
        )
        clone = _GIT_CLONE_URL.search(notes)
        if clone and not _GIT_CHECKOUT_SHA.search(notes):
            offenders[name] = clone.group("url")
    assert inspected >= 1, (
        "expected at least one uv --directory clone; the clone-pin ratchet is "
        f"vacuous if the launcher shape changed ({inspected} found)"
    )
    assert not offenders, (
        "uv --directory clones must check out a full 40-hex commit in their "
        "setup note (git checkout <sha>), not a floating branch:\n"
        + "\n".join(f"  {name}: {url}" for name, url in sorted(offenders.items()))
    )


_IMAGE_PACKAGES = _REPO_ROOT / "infra" / "docker" / "mcp-packages"


def _config_pins() -> tuple[set[str], set[tuple[str, frozenset[str]]]]:
    """npx package specs and uvx (package, --with specs) pinned in mcp-config.json."""
    npx: set[str] = set()
    uvx: set[tuple[str, frozenset[str]]] = set()
    for config in _servers().values():
        args = [a for a in config.get("args") or [] if isinstance(a, str)]
        if config.get("command") == "npx":
            npx.add(npx_package(args)[0])
        elif config.get("command") == "uvx":
            spec, with_specs, _, _ = uvx_specs(args)
            uvx.add((spec, frozenset(with_specs)))
    return npx, uvx


@pytest.mark.unit
def test_image_npm_list_matches_npx_pins():
    """The backend image bakes exactly the npx pins; drift either way fails."""
    deps = json.loads((_IMAGE_PACKAGES / "package.json").read_text())["dependencies"]
    image = {f"{name}@{version}" for name, version in deps.items()}
    lock = json.loads((_IMAGE_PACKAGES / "package-lock.json").read_text())
    assert lock["packages"][""]["dependencies"] == deps, "package-lock.json is stale"
    config, _ = _config_pins()
    assert len(config) >= 5, "npx ratchet is vacuous"
    assert config == image, (
        f"only in mcp-config.json: {sorted(config - image)}; "
        f"only in infra/docker/mcp-packages/package.json: {sorted(image - config)}"
    )


@pytest.mark.unit
def test_image_uv_tool_list_matches_uvx_pins():
    image: set[tuple[str, frozenset[str]]] = set()
    for line in (_IMAGE_PACKAGES / "uv-tools.txt").read_text().splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        withs = {tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t == "--with"}
        image.add((tokens[0], frozenset(withs)))
    _, config = _config_pins()
    assert len(config) >= 5, "uvx ratchet is vacuous"
    assert config == image, (
        f"only in mcp-config.json: {sorted(config - image, key=str)}; "
        f"only in infra/docker/mcp-packages/uv-tools.txt: {sorted(image - config, key=str)}"
    )

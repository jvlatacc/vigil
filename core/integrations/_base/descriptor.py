"""Integration descriptor — the per-vendor source of truth for registry metadata.

Vendors register a descriptor here; the scattered integration registries
(secret-field map, MCP-server map, …) derive their per-vendor entries from it
instead of hardcoding them.

Descriptors are found by scanning ``core/integrations/*/descriptor.py``, not by
an import list. A descriptor missing from such a list never runs its
``register_descriptor`` call and goes silently dead — which is exactly how
darktrace's became dead scaffolding before #557 removed it.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

_SLICES_DIR = Path(__file__).resolve().parent.parent

_TRUTHY = {"true", "1", "yes", "on"}


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_COERCERS: Dict[str, Callable[[Any], Any]] = {
    "str": lambda value: value,
    "bool": _to_bool,
    "int": _to_int,
}


@dataclass(frozen=True)
class IntegrationField:
    """One configurable value: its name, whether it is secret, its type.

    ``value_type`` exists because the two config channels disagree on typing.
    The Settings form stores JSON, so a checkbox arrives as a real ``bool``;
    the env channel — an ``mcp-config.json`` ``env`` block, or ``get_secret``
    — is strings all the way down. Undeclared, ``VERIFY_SSL=false`` reaches
    ``requests(verify=...)`` as the string ``"false"``, which is not a flag
    but a CA-bundle path that does not exist.
    """

    name: str
    secret: bool = False
    value_type: str = "str"
    # What an unset field resolves to; ``None`` leaves the caller to decide.
    default: Any = None

    def __post_init__(self) -> None:
        if self.value_type not in _COERCERS:
            raise ValueError(
                f"{self.name}: unknown value_type {self.value_type!r}, "
                f"expected one of {sorted(_COERCERS)}"
            )

    def coerce(self, value: Any) -> Any:
        """Apply the declared type. Unset is the field's default, ``None`` unless declared."""
        if value is None:
            return self.default
        return _COERCERS[self.value_type](value)


@dataclass(frozen=True)
class IntegrationDescriptor:
    """One code-backed integration's registry facts.

    ``fields`` is the *complete* field list, not just the secret ones: the
    config resolver keys its result off it, so a server can only read what its
    descriptor declares, and the catalog-parity ratchet compares the two
    statically instead of parsing server source.

    ``mcp_server_names`` is a tuple because one vendor can back several servers
    — Splunk has both an official server and the self-hosted one Vigil ships.
    """

    id: str
    category: str
    mcp_server_names: Tuple[str, ...] = ()
    fields: Tuple[IntegrationField, ...] = ()
    # Optional console URL. ``{external_id}`` and the descriptor's non-secret
    # field names. Set only where the stored ``external_id`` is the vendor's
    # own alert id and the vendor documents the URL; cite the doc beside it.
    # Evidence refs win when they are links.
    console_link_template: Optional[str] = None
    # Tools that change the world -- isolate a host, quarantine a device, run
    # an attack technique. Declared here, the vendor's source of truth, because
    # the fail-closed name pattern can only read what a name says:
    # ``manage_incidents`` changes incident state and no suffix reveals it.
    # Names are the vendor's own tool ids (the registry prefixes the server),
    # and the dispatch gate queues every match for human approval (area B).
    mutating_tools: Tuple[str, ...] = ()

    @property
    def secret_fields(self) -> Tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.secret)

    @property
    def field_names(self) -> Tuple[str, ...]:
        return tuple(f.name for f in self.fields)


_REGISTRY: Dict[str, IntegrationDescriptor] = {}
_discovered = False
_discovering = False


def register_descriptor(descriptor: IntegrationDescriptor) -> IntegrationDescriptor:
    _REGISTRY[descriptor.id] = descriptor
    return descriptor


def _discover() -> None:
    """Import every vendor slice's descriptor module exactly once.

    ``_discovering`` guards re-entry so a descriptor that reaches back into
    this module can't recurse; ``_discovered`` is only set once the sweep
    completes. Import errors propagate: a broken descriptor should fail loudly
    rather than leave a vendor silently unregistered. Marking the sweep done up
    front would do exactly that — a caller that swallows the error would pin a
    partial registry in place for the life of the process, and every secret
    field belonging to a missing vendor would then be persisted in plaintext.
    """
    global _discovered, _discovering
    if _discovered or _discovering:
        return
    _discovering = True
    try:
        for path in sorted(_SLICES_DIR.glob("*/descriptor.py")):
            package = path.parent.name
            if package.startswith("_"):
                continue
            importlib.import_module(f"core.integrations.{package}.descriptor")
        _discovered = True
    finally:
        _discovering = False


def get_descriptor(integration_id: str) -> Optional[IntegrationDescriptor]:
    _discover()
    return _REGISTRY.get(integration_id)


def iter_descriptors() -> Tuple[IntegrationDescriptor, ...]:
    _discover()
    return tuple(_REGISTRY.values())


# The fail-closed fallback when a descriptor declares nothing: a tool whose
# name ends in a direct-action verb changes the world whether or not a
# descriptor vouches for it. Suffix-anchored so a read-only lead wins
# (get_isolation_status, list_blocked_ips) -- the same reading chat's token
# list makes, and the same side to err on: a spurious queue costs a person's
# click, a missed one is an ungated detonation.
MUTATING_TOOL_PATTERN = re.compile(
    r"_(isolate|unisolate|quarantine|block|delete|remove|execute|terminate|"
    r"kill|reset|revoke|purge|escalate)$"
)


def descriptor_for_server(server: Optional[str]) -> Optional[IntegrationDescriptor]:
    """The vendor descriptor whose MCP servers carry ``server``, if any."""
    _discover()
    return next((d for d in _REGISTRY.values() if server in d.mcp_server_names), None)


def declared_requires_approval(server: Optional[str], tool: str) -> Optional[bool]:
    """Whether the server's descriptor declares this tool mutating.

    ``None`` means undeclared -- not safe: the caller falls back to the name
    pattern.
    """
    descriptor = descriptor_for_server(server)
    if descriptor is None or tool not in descriptor.mutating_tools:
        return None
    return True


def tool_requires_approval(server: Optional[str], tool: str) -> bool:
    """Whether dispatching this MCP tool must first queue for approval.

    The descriptor decides where one covers the server; everything else fails
    closed to the name pattern, read against the server-prefixed name the
    registry and chat both see (``{server}_{tool}``), so a bare-verb tool id
    -- ``quarantine`` on its own -- is still caught under its prefix.
    """
    if declared_requires_approval(server, tool) is not None:
        return True
    prefixed = f"{server}_{tool}" if server else tool
    return bool(MUTATING_TOOL_PATTERN.search(prefixed))


def flat_name_requires_approval(name: str) -> bool:
    """``tool_requires_approval`` from a registry tool id alone.

    Chat reaches tools by name only, with no server list to split against,
    so the server prefix is matched against the names descriptors declare --
    longest first, the same reading ``split_tool_name`` gives the live
    servers. A name no descriptor claims is classified whole.
    """
    _discover()
    servers = sorted(
        {s for d in _REGISTRY.values() for s in d.mcp_server_names},
        key=len,
        reverse=True,
    )
    for server in servers:
        prefix = f"{server}_"
        if name.startswith(prefix) and len(name) > len(prefix):
            return tool_requires_approval(server, name[len(prefix) :])
    return tool_requires_approval(None, name)

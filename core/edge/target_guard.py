"""The pre-executor guard: which targets may never be blocked.

The only real precedent in the repo is the daemon's ``_actionable_ip``
(``services/daemon/responder.py``), which filters loopback, unspecified,
multicast, link-local, and reserved addresses — but not the daemon's own
address, the gateways, the control plane, or the DNS resolvers, and whose
inputs (``src_ips``) come from vendor payloads an attacker can shape. This
guard is the fix, placed before every executor: the targets it refuses are
configured on the node — never taken from alert data — so no payload can
rename what is protected.

Two layers, both fail-closed:

- **Structural floor (unconditional).** Loopback, unspecified, multicast,
  reserved, link-local, and the node's own addresses are refused whatever a
  pack says — self-lockout is impossible by construction, and a block
  against a link-local or broadcast address is a denial of service against
  the segment's own plumbing.
- **Signed categories (from the pack).** ``gateway``, ``control_plane``,
  and ``dns_resolvers`` configure sets of addresses/networks that are
  protected while the pack lists that category. A signed pack can tighten
  this layer, never loosen the floor.

A target the guard cannot parse is refused: the v1 executor acts on IPs and
the guard must see what it clears.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Sequence

from core.edge.policy import PolicyPack

__all__ = ["CATEGORIES", "TargetGuard"]

Address = ipaddress.IPv4Address | ipaddress.IPv6Address
Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# The categories a pack's ``protected_targets`` may name — the schema's enum,
# restated here because the guard's behavior is keyed on them.
CATEGORIES = frozenset({"self", "gateway", "control_plane", "dns_resolvers"})


def _parse_target(target: str) -> Address | None:
    """The address in ``target``, unwrapping IPv4-mapped IPv6, or None."""
    try:
        ip = ipaddress.ip_address(str(target).strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def _networks(entries: Sequence[str]) -> frozenset[Network]:
    """Parse configured addresses and networks; refuse anything sloppy.

    Networks are parsed strict — ``10.0.0.1/8`` (host bits set) raises
    rather than silently narrowing to ``10.0.0.0/8``, so a mistyped
    protection fails the configuration, not the node.
    """
    networks: set[Network] = set()
    for entry in entries:
        text = entry.strip()
        try:
            if "/" in text:
                networks.add(ipaddress.ip_network(text, strict=True))
            else:
                ip = ipaddress.ip_address(text)
                networks.add(ipaddress.ip_network(f"{text}/{ip.max_prefixlen}"))
        except ValueError as exc:
            raise ValueError(f"invalid protected address/network {entry!r}") from exc
    return frozenset(networks)


@dataclass(frozen=True)
class TargetGuard:
    """Configured protected targets, checked against one signed pack's
    categories. Build with :meth:`from_pack` so the categories always come
    from the verified pack the decision cites."""

    protected_categories: frozenset[str]
    self_addresses: frozenset[Network] = frozenset()
    gateway_networks: frozenset[Network] = frozenset()
    control_plane_networks: frozenset[Network] = frozenset()
    dns_resolvers: frozenset[Network] = frozenset()

    @classmethod
    def from_pack(
        cls,
        pack: PolicyPack,
        *,
        self_addresses: Sequence[str] = (),
        gateway_addresses: Sequence[str] = (),
        control_plane_addresses: Sequence[str] = (),
        dns_resolvers: Sequence[str] = (),
    ) -> "TargetGuard":
        """A guard for ``pack`` with the node's own view of its network.

        The address arguments are node configuration (the data dir's
        enrollment state, the host's interfaces, resolv.conf equivalents) —
        never anything derived from an alert.
        """
        return cls(
            protected_categories=frozenset(pack.protected_targets) & CATEGORIES,
            self_addresses=_networks(self_addresses),
            gateway_networks=_networks(gateway_addresses),
            control_plane_networks=_networks(control_plane_addresses),
            dns_resolvers=_networks(dns_resolvers),
        )

    def check(self, target: str) -> str | None:
        """Why acting on ``target`` is forbidden, or None when it is clear.

        The returned string is the ``decision_rule`` detail the journal
        records — the category and the matched address, e.g.
        ``self (loopback 127.0.0.1)``.
        """
        ip = _parse_target(target)
        if ip is None:
            # Fail closed: the guard cannot vouch for what it cannot see,
            # and no v1 executor could act on it anyway.
            return f"unparseable ({target!r})"
        if ip.is_loopback:
            return f"self (loopback {ip})"
        if ip.is_unspecified:
            return f"self (unspecified {ip})"
        if ip.is_multicast:
            return f"multicast ({ip})"
        if ip.is_reserved:
            return f"reserved ({ip})"
        # Link-local is where segment plumbing lives (RFC 3927/4862): the
        # default route's IPv6 gateway, mDNS, cloud metadata. Never blockable.
        if ip.is_link_local:
            return f"gateway (link-local {ip})"
        if any(ip in network for network in self.self_addresses):
            return f"self ({ip})"
        if "gateway" in self.protected_categories and any(
            ip in network for network in self.gateway_networks
        ):
            return f"gateway ({ip})"
        if "control_plane" in self.protected_categories and any(
            ip in network for network in self.control_plane_networks
        ):
            return f"control_plane ({ip})"
        if "dns_resolvers" in self.protected_categories and any(
            ip in network for network in self.dns_resolvers
        ):
            return f"dns_resolvers ({ip})"
        return None

    def is_protected(self, target: str) -> bool:
        """Whether the guard refuses this target — ``check`` carries the why."""
        return self.check(target) is not None

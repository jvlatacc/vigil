"""Sources exempt from honey-routing.

Sanctioned scanners and shared-NAT ranges are exactly the sources a recon
predicate fires on, and steering either one wastes a lease on a friend or
punishes a crowd. Exemption is decided here, before corroboration, so an
allowlisted source never accumulates probes toward the posture either.

One entry shape — an IP or CIDR, comma-separated in
``DAEMON_DECEPTION_ALLOWLIST``. No expiry, no per-entry reason: that is a
console concern (PR: Deception screen) and this module is the spine.
"""

import ipaddress

from core.deception.config import parse_allowlist_entries


class Allowlist:
    """Parsed exemption set with a cheap membership test."""

    def __init__(self, entries: str = ""):
        self._networks = parse_allowlist_entries(entries)

    def is_exempt(self, ip: str, now=None) -> bool:
        """Whether ``ip`` is exempt.

        ``now`` is accepted (and unused): callers pass the decision clock so
        a time-scoped entry shape can land later without touching call sites.
        """
        if not self._networks or not ip:
            return False
        try:
            address = ipaddress.ip_address(str(ip).strip())
        except ValueError:
            return False
        return any(address in network for network in self._networks)

    def __bool__(self) -> bool:
        return bool(self._networks)


def allowlist_from_config(config) -> Allowlist:
    """The :class:`Allowlist` a :class:`DeceptionConfig` configures."""
    return Allowlist(config.allowlist)

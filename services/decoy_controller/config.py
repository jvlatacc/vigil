"""Controller configuration, read from the environment.

Every knob is a plain ``DECOY_CONTROLLER_*`` environment variable; the
service intentionally does not use pydantic Settings or ``core.config`` —
it is self-contained by contract (see the package docstring) and shares no
configuration machinery with the process it enforces for.

Safety defaults, in order of importance:

- no token configured → every API request is denied (an enforcement plane
  with no credential never trusts whoever can reach the port);
- driver ``memory`` → rules are recorded in-process and no traffic is touched;
- TTLs are capped at ``max_ttl`` no matter what the caller asks for — the
  controller enforces expiry itself and re-checks every lease against its
  own ceiling, it does not trust the caller's bookkeeping.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)

DRIVER_MEMORY = "memory"
DRIVER_NFTABLES = "nftables"
DRIVER_CILIUM = "cilium"
KNOWN_DRIVERS = (DRIVER_MEMORY, DRIVER_NFTABLES, DRIVER_CILIUM)

DEFAULT_PORT = 8484


def _split_endpoint(raw: str) -> tuple:
    """Split a map entry into (host, port|None).

    IPv6 needs brackets around the host when a port follows — a bare
    ``fd00::10:2222`` is not parseable, so map entries use
    ``445=[fd00:decoy::11]:2222``. An entry that cannot carry a port
    parses as a bare host.
    """
    if raw.startswith("["):
        host, _, rest = raw[1:].partition("]")
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if raw.count(":") > 1:  # bare IPv6 — no port suffix is representable
        return raw, None
    host, sep, port = raw.partition(":")
    if sep and port.isdigit():
        return host, int(port)
    return raw, None


def parse_decoy_map(raw: str) -> Dict[int, str]:
    """Parse ``445=10.0.5.10,3389=10.0.5.11:3389`` into a port → endpoint map.

    An endpoint is an IP (the decoy listens on the same port) or ``ip:port``
    (IPv6 entries bracketed: ``445=[fd00:decoy::11]:2222``). An entry that
    does not parse is skipped loudly — a typo must be visible,
    but must not keep the rest of the map from working (the repo's allowlist
    precedent).
    """
    endpoints: Dict[int, str] = {}
    for chunk in (raw or "").split(","):
        entry = chunk.strip()
        if not entry:
            continue
        port_str, _, endpoint = entry.partition("=")
        try:
            port = int(port_str.strip())
            if not (1 <= port <= 65535) or not endpoint:
                raise ValueError
        except ValueError:
            logger.warning("Ignoring unparseable decoy map entry: %r", entry)
            continue
        endpoints[port] = endpoint.strip()
    return endpoints


def _env(name: str, default: str = "") -> str:
    # Standalone service: the medic contract forbids core imports, so
    # get_settings() is unreachable here — the raw read is the process boundary.
    value = os.environ.get(name)  # noqa: ENV001 — standalone service
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class ControllerConfig:
    """One controller deployment's knobs."""

    driver: str = DRIVER_MEMORY
    # Empty token denies every request (see module docstring).
    token: str = ""
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    # TTL reaper cadence, seconds. The reaper is the controller-side lease
    # enforcement: expiry is enforced here, not left to filter timeouts.
    sweep_interval: int = 30
    # Ceiling on any lease the caller asks for, seconds — renewals included.
    max_ttl: int = 86400
    # Maximum concurrently held redirects. A full registry refuses new
    # steering (409) — fail-open for the caller, which marks the lease failed.
    max_rules: int = 100
    # Where matched traffic lands. One default endpoint plus an optional
    # per-port override map (see parse_decoy_map).
    decoy_ip: str = "10.0.5.10"
    decoy_map: str = ""
    # Protocols the nftables driver redirects, comma-separated. The service
    # class Vigil scopes leases to (SSH/SMB/HTTP probes) is TCP; UDP is
    # opt-in because it doubles the rule set for traffic that was never
    # observed.
    protocols: str = "tcp"
    # Flush every rule on boot. After a restart, stale redirects nobody can
    # name are worse than a brief gap: the plane starts clean and Vigil's
    # lease sweep re-asserts any lease that should still exist.
    boot_drain: bool = True

    @classmethod
    def from_env(cls) -> "ControllerConfig":
        driver = _env("DECOY_CONTROLLER_DRIVER", DRIVER_MEMORY)
        if driver not in KNOWN_DRIVERS:
            logger.warning(
                "Unknown DECOY_CONTROLLER_DRIVER %r; falling back to %r",
                driver,
                DRIVER_MEMORY,
            )
            driver = DRIVER_MEMORY
        return cls(
            driver=driver,
            token=_env("DECOY_CONTROLLER_TOKEN"),
            host=_env("DECOY_CONTROLLER_HOST", "0.0.0.0"),
            port=int(_env("DECOY_CONTROLLER_PORT", str(DEFAULT_PORT))),
            sweep_interval=max(int(_env("DECOY_CONTROLLER_SWEEP_INTERVAL", "30")), 1),
            max_ttl=max(int(_env("DECOY_CONTROLLER_MAX_TTL", "86400")), 1),
            max_rules=max(int(_env("DECOY_CONTROLLER_MAX_RULES", "100")), 1),
            decoy_ip=_env("DECOY_CONTROLLER_DECOY_IP", "10.0.5.10"),
            decoy_map=_env("DECOY_CONTROLLER_DECOY_MAP"),
            protocols=_env("DECOY_CONTROLLER_PROTOCOLS", "tcp"),
            boot_drain=_env("DECOY_CONTROLLER_BOOT_DRAIN", "true").lower()
            in ("true", "1", "yes", "on"),
        )

    def endpoint_for(self, port: int) -> tuple:
        """The decoy ``(host, port|None)`` one redirected port lands on.

        ``None`` means the decoy listens on the redirected port itself.
        """
        raw = parse_decoy_map(self.decoy_map).get(port)
        if raw is None:
            return _split_endpoint(self.decoy_ip)
        return _split_endpoint(raw)

    def protocol_list(self) -> tuple:
        return tuple(
            p.strip().lower() for p in self.protocols.split(",") if p.strip()
        ) or ("tcp",)

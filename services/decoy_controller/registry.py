"""The rule registry: what the controller currently holds on the plane.

The durable record of a redirect lives in Vigil's Postgres (the lease row);
the controller keeps only the working set it needs to program and enforce
expiry — deliberately in-memory, deliberately small. After a restart the
working set is empty, the driver's boot drain clears anything stale on the
plane, and Vigil's lease sweep re-asserts what should exist. A registry that
could outlive its process would be a second database to reconcile against
Vigil's, and the reconciliation bug that implies.

Expiry is enforced here, controller-side — not left to nftables timeout
semantics or a CNI's notion of age — so every driver gets identical lease
semantics and the reaper is one loop over one data structure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional


class RegistryFull(Exception):
    """Raised when a new lease would exceed ``max_rules``.

    The API maps this to 409; the caller (Vigil) marks the lease failed and
    production routing is untouched — fail-open.
    """


@dataclass(frozen=True)
class Rule:
    """One redirect the controller holds: who, where, until."""

    lease_id: str
    source_ip: str
    destination_ips: tuple = field(default_factory=tuple)
    ports: tuple = field(default_factory=tuple)
    ttl_seconds: int = 0
    created_at: float = 0.0
    expires_at: float = 0.0
    # Driver-assigned backend reference (audit/rollback handle).
    ref: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "source_ip": self.source_ip,
            "destination_ips": list(self.destination_ips),
            "ports": list(self.ports),
            "ttl_seconds": self.ttl_seconds,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "ref": self.ref,
        }


class RuleRegistry:
    """The working set of redirects, with TTL enforcement.

    Not thread-safe: the FastAPI event loop serializes access, and driver
    calls (the blocking part) run through ``asyncio.to_thread`` without ever
    touching the registry themselves.
    """

    def __init__(
        self,
        max_rules: int = 100,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._max_rules = max_rules
        self._clock = clock
        self._rules: Dict[str, Rule] = {}

    def upsert(
        self,
        *,
        lease_id: str,
        source_ip: str,
        destination_ips: List[str],
        ports: List[int],
        ttl_seconds: int,
        ref: str = "",
    ) -> Rule:
        """Record (or re-record) one lease. Renewal is an upsert."""
        now = self._clock()
        existing = self._rules.get(lease_id)
        if existing is None and len(self._rules) >= self._max_rules:
            raise RegistryFull(
                f"registry holds {self._max_rules} rules; refusing lease {lease_id}"
            )
        rule = Rule(
            lease_id=lease_id,
            source_ip=source_ip,
            destination_ips=tuple(destination_ips),
            ports=tuple(ports),
            ttl_seconds=ttl_seconds,
            created_at=existing.created_at if existing else now,
            expires_at=now + ttl_seconds,
            ref=ref,
        )
        self._rules[lease_id] = rule
        return rule

    def get(self, lease_id: str) -> Optional[Rule]:
        return self._rules.get(lease_id)

    def remove(self, lease_id: str) -> Optional[Rule]:
        """Drop a lease from the working set; None when it was not held."""
        return self._rules.pop(lease_id, None)

    def all(self) -> List[Rule]:
        """Every held rule, oldest first — stable order for rendering."""
        return sorted(self._rules.values(), key=lambda r: (r.created_at, r.lease_id))

    def expired(self, now: Optional[float] = None) -> List[Rule]:
        """Held rules whose TTL has passed."""
        moment = self._clock() if now is None else now
        return [r for r in self.all() if r.expires_at <= moment]

    def clear(self) -> List[str]:
        """Drop everything (the drain path); returns the removed lease ids."""
        removed = list(self._rules)
        self._rules.clear()
        return removed

    def set_ref(self, lease_id: str, ref: str) -> Optional[Rule]:
        """Attach the driver-assigned backend ref without touching the TTL."""
        current = self._rules.get(lease_id)
        if current is None:
            return None
        updated = replace(current, ref=ref)
        self._rules[lease_id] = updated
        return updated

    def renew(self, lease_id: str, ttl_seconds: int) -> Optional[Rule]:
        """Extend one held lease's expiry, keeping its created_at."""
        current = self._rules.get(lease_id)
        if current is None:
            return None
        updated = replace(
            current,
            ttl_seconds=ttl_seconds,
            expires_at=self._clock() + ttl_seconds,
        )
        self._rules[lease_id] = updated
        return updated

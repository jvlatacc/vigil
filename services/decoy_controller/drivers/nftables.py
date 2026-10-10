"""nftables driver — compose / single-host DNAT enforcement.

The controller owns one nftables table (``inet vigildecoy``) with a single
NAT chain. Every sync regenerates the chain's rules atomically from the
registry's current contents (flush + re-add in one ``nft -f -`` batch), so
apply is idempotent, removal is exact, and there is no incremental nft state
to drift from the registry — the rendered ruleset is a pure function of the
desired state, and it is unit-tested as one.

Deployment reality: DNAT requires kernel privileges. Run the container with
``network_mode: host`` and ``NET_ADMIN`` (the compose service documents the
override) on a host whose FORWARD path reaches the decoys. On Kubernetes use
the cilium driver instead — that is what it exists for.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Dict, List, Optional, Sequence

from services.decoy_controller.config import ControllerConfig
from services.decoy_controller.registry import Rule

logger = logging.getLogger(__name__)

TABLE = "inet vigildecoy"
CHAIN = "dstnat"
COMMENT_PREFIX = "vigil-lease:"

# nft's nat chain priority for destination NAT (matches `priority dstnat`).
_DSTNAT_PRIORITY = -100


def render_rule(rule: Rule, config: ControllerConfig) -> List[str]:
    """The nft commands for one lease — a pure function, unit-tested directly.

    One command per (protocol, destination, port) triple; each commented
    with its lease id so an operator reading ``nft list chain`` can map any
    rule back to the audit record in Vigil. The rule family follows the
    source address; destinations of the other family cannot share a nat
    rule and are skipped loudly (an nft batch mixing families fails whole,
    which would drop the other leases' rules too).
    """
    commands: List[str] = []
    family = "ip6" if ":" in rule.source_ip else "ip"
    destinations = sorted(set(rule.destination_ips))
    ports = sorted(set(int(p) for p in rule.ports))
    for protocol in config.protocol_list():
        for destination in destinations:
            if (":" in destination) != (family == "ip6"):
                logger.warning(
                    "Lease %s: skipping %s destination %s — family differs "
                    "from source %s",
                    rule.lease_id,
                    family,
                    destination,
                    rule.source_ip,
                )
                continue
            for port in ports:
                decoy_host, mapped_port = config.endpoint_for(port)
                if (":" in decoy_host) != (family == "ip6"):
                    logger.warning(
                        "Lease %s: decoy %s is not reachable from the %s "
                        "family — skipping port %d",
                        rule.lease_id,
                        decoy_host,
                        family,
                        port,
                    )
                    continue
                # `dnat to <ip>` preserves the port; `dnat to <ip>:<port>`
                # rewrites it (a decoy that does not listen on 1:1 ports).
                target_port = mapped_port if mapped_port is not None else port
                if family == "ip6":
                    target = f"[{decoy_host}]:{target_port}"
                else:
                    target = f"{decoy_host}:{target_port}"
                comment = f"{COMMENT_PREFIX}{rule.lease_id}"
                commands.append(
                    f"add rule {TABLE} {CHAIN} {family} saddr {rule.source_ip} "
                    f"{family} daddr {destination} {protocol} dport {port} "
                    f'dnat {family} to {target} comment "{comment}"'
                )
    return commands


def render_ruleset(rules: Sequence[Rule], config: ControllerConfig) -> str:
    """The complete atomic batch: flush the chain, re-add every lease.

    Regenerating everything from desired state is what makes a sync safe to
    replay: an interrupted batch leaves the chain as it was, and the next
    sync converges regardless.
    """
    lines = [
        f"flush table {TABLE}",
        f"add chain {TABLE} {CHAIN} {{ type nat hook prerouting priority "
        f"{_DSTNAT_PRIORITY} ; }}",
    ]
    for rule in rules:
        lines.extend(render_rule(rule, config))
    return "\n".join(lines) + "\n"


class NftablesDriver:
    """Applies the rendered ruleset through the local ``nft`` binary."""

    name = "nftables"

    def __init__(self, config: ControllerConfig, run=None) -> None:
        self._config = config
        self._run = run if run is not None else self._exec

    @staticmethod
    def _exec(args: Sequence[str], input_text: Optional[str] = None) -> str:
        result = subprocess.run(  # noqa: S603 — fixed argv, no shell
            list(args),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"nft failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def boot(self) -> None:
        """Delete the whole table — every rule a previous life created.

        Missing table is fine (first boot); anything else fails loudly at
        startup rather than letting stale redirects outlive their registry.
        """
        try:
            self._run(["nft", "-f", "-"], input_text=f"delete table {TABLE}\n")
        except RuntimeError as e:
            if "No such file or directory" in str(e):
                return
            raise

    def sync(self, rules: Sequence[Rule]) -> Dict[str, str]:
        """Ensure the table exists, then atomically converge it."""
        self._ensure_table()
        ruleset = render_ruleset(rules, self._config)
        self._run(["nft", "-f", "-"], input_text=ruleset)
        return {rule.lease_id: self.ref_for(rule.lease_id) for rule in rules}

    @staticmethod
    def ref_for(lease_id: str) -> str:
        return f"nft:{TABLE}/{CHAIN}/{lease_id}"

    def _ensure_table(self) -> None:
        listing = self._run(["nft", "list", "tables"])
        if TABLE in listing:
            return
        batch = (
            f"add table {TABLE}\n"
            f"add chain {TABLE} {CHAIN} {{ type nat hook prerouting priority "
            f"{_DSTNAT_PRIORITY} ; }}\n"
        )
        self._run(["nft", "-f", "-"], input_text=batch)
        logger.info("Created nftables table %s with chain %s", TABLE, CHAIN)

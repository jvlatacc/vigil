"""Gateway-mode containment: nftables with a dedicated ``vigil_edge`` table.

Design spec (edge daemons, executors): one executor interface, two
implementations; gateway mode manages a dedicated nftables table on the
host (host networking + NET_ADMIN) and blocks only egress to specific
addresses, always with a TTL so the reaper can revert.

Shape: one chain per blocked target, named deterministically
(``blk_<12 hex of executor+type+target>``), installed as its own base
chain on the ``output`` hook with ``policy accept`` and one drop rule per
resolved address. Deleting the chain is the whole revert — no handle
bookkeeping — and re-applying flushes the chain first, so the net
ruleset is identical no matter how many times the same block lands.

Trust boundary: every rule the daemon writes lives inside the dedicated
``vigil_edge`` table, never the operator's own tables; the daemon
creates no chains outside it and touches nothing else on the host.

All enforcement goes through an injected command runner — production
shells out to ``nft`` (requires root/NET_ADMIN), tests record argv and
reply with canned results, so the suite runs without root.

Known tradeoff, recorded here: domain blocks resolve DNS at apply time
and pin the resolved addresses for the TTL; a domain that re-resolves
mid-TTL is not re-blocked until the next decision for it. Acceptable for
v1 — the observation feed keeps flowing and re-triggers.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable, Sequence

from services.edge.executors.registry import ActionResult
from services.edge.gate.gate import Action

#: The dedicated table — the only object the daemon creates on the host.
TABLE = "vigil_edge"

#: Base-chain priority for block chains on the output hook.
CHAIN_PRIORITY = "0"

#: A domain name a resolver would accept; deliberately looser than
#: RFC-1123 (we validate shape, the resolver is the real check).
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}\.?$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\.?$",
    re.IGNORECASE,
)

CommandResultTuple = tuple[int, str, str]
CommandRunner = Callable[[Sequence[str]], Awaitable[CommandResultTuple]]


async def run_command(argv: Sequence[str]) -> CommandResultTuple:
    """The production runner: execute argv, return (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else -1,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


async def _resolve_domain(domain: str) -> list[str]:
    """Resolve a domain to addresses (v4 and v6); empty on failure."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(domain, None)
    except socket.gaierror:
        return []
    seen: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in seen:
            seen.append(addr)
    return seen


def chain_name(executor_name: str, action: Action) -> str:
    """Deterministic per-target chain name — the same block always lands
    on the same chain, so re-apply reuses it and revert finds it."""
    digest = hashlib.sha256(
        f"{executor_name}|{action.action_type}|{action.target}".encode()
    ).hexdigest()[:12]
    return f"blk_{digest}"


def ref_for(chains: Sequence[str]) -> str:
    """The revert contract: the table and the chains to remove."""
    return json.dumps({"table": TABLE, "chains": sorted(chains)})


def parse_ref(ref: str) -> tuple[str, list[str]]:
    """Inverse of :func:`ref_for`; raises ValueError on a foreign ref.
    The table must be this daemon's own: a tampered or corrupt ref must
    fail loudly, not revert to deleting chains that were never there and
    calling the no-op a success."""
    raw = json.loads(ref)
    table = raw.get("table")
    chains = raw.get("chains")
    if (
        not isinstance(table, str)
        or not isinstance(chains, list)
        or not all(isinstance(c, str) for c in chains)
    ):
        raise ValueError(f"unparseable nftables ref: {ref!r}")
    if table != TABLE:
        raise ValueError(f"foreign_table:{table!r}")
    return table, chains


def _addresses_for(action: Action) -> list[str]:
    """Validate the target and return the addresses to drop. Raises
    ValueError on anything the daemon must not act on."""
    if action.action_type == "block_ip":
        try:
            ip = ipaddress.ip_address(action.target)  # may raise
        except ValueError as exc:
            raise ValueError(f"invalid_ip:{action.target}") from exc
        return [str(ip)]
    if action.action_type == "block_domain":
        domain = action.target.strip()
        if not _DOMAIN_RE.match(domain):
            raise ValueError(f"invalid_domain:{action.target!r}")
        return [domain]
    raise ValueError(f"unsupported_action_type:{action.action_type}")


class NftablesExecutor:
    """Reversible egress denial in gateway mode via a dedicated table."""

    def __init__(
        self,
        executor_name: str,
        runner: CommandRunner,
        *,
        resolver: Callable[[str], Awaitable[list[str]]] = _resolve_domain,
    ) -> None:
        self._executor_name = executor_name
        self._runner = runner
        self._resolver = resolver

    @property
    def name(self) -> str:
        return self._executor_name

    @property
    def action_types(self) -> frozenset[str]:
        return frozenset({"block_ip", "block_domain"})

    # -- apply ---------------------------------------------------------------

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        # ``namespaces`` is accepted for Executor-protocol uniformity and
        # deliberately unused: gateway-mode nftables rules are host-scoped,
        # there is no namespace concept to scope them to.
        chain = chain_name(self._executor_name, action)
        try:
            # block_domain resolves first: a dead resolver must not leave
            # an empty chain behind as fake containment.
            addresses = _addresses_for(action)
            if action.action_type == "block_domain":
                addresses = await self._resolver(action.target.strip())
                if not addresses:
                    return ActionResult(
                        success=False,
                        error=f"domain_unresolved:{action.target}",
                    )
        except ValueError as exc:
            return ActionResult(success=False, error=str(exc))

        # Ensure the table and the chain exist: probe with list (rc 0 =
        # present); a failed probe means absent (or unreadable — then the
        # create fails and that is the real error). The dedicated table is
        # this daemon's single-writer object, so probe-then-create races
        # are not a supported deployment shape.
        ensured = await self._ensure(
            ["nft", "list", "table", "inet", TABLE],
            create=["nft", "add", "table", "inet", TABLE],
        )
        if ensured is not None:
            return ensured
        ensured = await self._ensure(
            ["nft", "list", "chain", "inet", TABLE, chain],
            create=[
                "nft",
                "add",
                "chain",
                "inet",
                TABLE,
                chain,
                (
                    "{ type filter hook output priority "
                    f"{CHAIN_PRIORITY}; policy accept; }}"
                ),
            ],
        )
        if ensured is not None:
            return ensured

        commands: list[list[str]] = [
            # Flush before re-adding: apply is idempotent — the same
            # block re-applied leaves exactly one set of rules.
            ["nft", "flush", "chain", "inet", TABLE, chain],
        ]
        for address in addresses:
            family = "ip6" if ":" in address else "ip"
            commands.append(
                [
                    "nft",
                    "add",
                    "rule",
                    "inet",
                    TABLE,
                    chain,
                    family,
                    "daddr",
                    address,
                    "drop",
                    "comment",
                    f"vigil:{action.action_type}:{action.target}",
                ]
            )
        return await self._run_all(commands, on_success=ref_for([chain]))

    async def _ensure(
        self, probe: list[str], *, create: list[str] | None = None
    ) -> ActionResult | None:
        """Run probe (list); on success there is nothing to do. On failure
        run create (if any) and turn its failure into an error result."""
        rc, _stdout, stderr = await self._runner(probe)
        if rc == 0:
            return None
        if create is None:
            # A probe without a create command is only used where absence
            # cannot be recovered locally.
            return ActionResult(
                success=False,
                error=f"nft_error:{rc}:{' '.join(probe[2:5])}:{stderr.strip()[:120]}",
            )
        rc, _stdout, stderr = await self._runner(create)
        if rc != 0:
            shorthand = " ".join(create[2:6])
            return ActionResult(
                success=False,
                error=f"nft_error:{rc}:{shorthand}:{stderr.strip()[:120]}",
            )
        return None

    # -- revert ---------------------------------------------------------------

    async def revert(self, ref: str) -> ActionResult:
        try:
            _table, chains = parse_ref(ref)
        except (ValueError, json.JSONDecodeError) as exc:
            return ActionResult(success=False, error=f"bad_ref:{exc}")
        if not chains:
            return ActionResult(success=False, error="bad_ref:empty chains")
        for chain in chains:
            rc, _stdout, stderr = await self._runner(
                ["nft", "delete", "chain", "inet", TABLE, chain]
            )
            if rc == 0:
                continue
            # Already gone is the goal state: an operator (or an earlier
            # crashed-after-delete run) removing the chain must not wedge
            # the reaper in a permanent retry. Same convention as the
            # NetworkPolicy executor's delete-404.
            if "no such file" in stderr.lower():
                continue
            return ActionResult(
                success=False,
                error=f"nft_error:{rc}:delete chain {chain}:{stderr.strip()[:120]}",
            )
        return ActionResult(success=True, ref=ref)

    # -- shared plumbing ------------------------------------------------------

    async def _run_all(
        self, commands: list[list[str]], *, on_success: str
    ) -> ActionResult:
        """Run every command; the first failure fails the whole result."""
        for argv in commands:
            try:
                rc, _stdout, stderr = await self._runner(argv)
            except OSError as exc:
                # nft missing from PATH and similar environment failures:
                # nothing was applied, report rather than pretend.
                return ActionResult(
                    success=False,
                    error=f"exec_error:{argv[0]}:{exc}",
                )
            if rc != 0:
                shorthand = " ".join(argv[2:6])
                return ActionResult(
                    success=False,
                    error=f"nft_error:{rc}:{shorthand}:{stderr.strip()[:120]}",
                )
        return ActionResult(success=True, ref=on_success)

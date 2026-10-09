"""Command-mock tests for the nftables executor — no root, no nft.

The fake is a tiny state machine over the executor's command vocabulary
(list/add/flush/delete for tables, chains, rules). It doubles as the
present/absent oracle: after apply the drop rule is in the fake's
ruleset, after revert the chain is gone.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from services.edge.executors import nftables
from services.edge.executors.nftables import (
    NftablesExecutor,
    chain_name,
    parse_ref,
)
from services.edge.gate.gate import Action


class FakeNft:
    """Enough of nft for the executor's vocabulary, with the same
    success/failure behavior: list fails on a missing object, add table
    is idempotent, add chain errors on an existing chain."""

    def __init__(self) -> None:
        self.tables: set[str] = set()
        self.chains: dict[str, dict[str, Any]] = {}
        self.add_table_calls = 0

    async def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        op, rest = argv[1], argv[2:]
        kind = rest[0] if rest else ""
        if op == "list":
            if kind == "table":
                key = f"inet {rest[2]}"
                return (0, "", "") if key in self.tables else (1, "", "No such file")
            if kind == "chain":
                key = f"inet {rest[2]}/{rest[3]}"
                return (0, "", "") if key in self.chains else (1, "", "No such file")
            return (1, "", f"unexpected list target {kind}")
        if op == "add":
            if kind == "table":
                self.add_table_calls += 1
                self.tables.add(f"inet {rest[2]}")
                return (0, "", "")
            if kind == "chain":
                key = f"inet {rest[2]}/{rest[3]}"
                if key in self.chains:
                    return (1, "", "File exists")
                self.chains[key] = {
                    "hook": rest[4] if len(rest) > 4 else None,
                    "rules": [],
                }
                return (0, "", "")
            if kind == "rule":
                key = f"inet {rest[2]}/{rest[3]}"
                if key not in self.chains:
                    return (1, "", "No such chain")
                self.chains[key]["rules"].append(list(rest[4:]))
                return (0, "", "")
            return (1, "", f"unexpected add target {kind}")
        if op == "flush":
            key = f"inet {rest[2]}/{rest[3]}"
            if key not in self.chains:
                return (1, "", "No such chain")
            self.chains[key]["rules"].clear()
            return (0, "", "")
        if op == "delete" and kind == "chain":
            key = f"inet {rest[2]}/{rest[3]}"
            if key in self.chains:
                del self.chains[key]
                return (0, "", "")
            return (1, "", "No such file")
        return (1, "", f"unexpected command {op} {kind}")

    def rules(self, chain: str) -> list[list[str]]:
        entry = self.chains.get(f"inet {nftables.TABLE}/{chain}")
        return entry["rules"] if entry else []


def make_executor(fake: FakeNft, *, resolver: Any = None) -> NftablesExecutor:
    kwargs: dict[str, Any] = {}
    if resolver is not None:
        kwargs["resolver"] = resolver
    return NftablesExecutor("nftables", fake, **kwargs)


def block_action(target: str = "203.0.113.55") -> Action:
    return Action(
        action_type="block_ip", executor="nftables", target=target, ttl_seconds=900
    )


def domain_action(target: str = "c2.example") -> Action:
    return Action(
        action_type="block_domain", executor="nftables", target=target, ttl_seconds=600
    )


def test_block_ip_apply_leaves_the_drop_rule_present() -> None:
    fake = FakeNft()
    executor = make_executor(fake)

    result = asyncio.run(executor.apply(block_action(), 900))

    assert result.success is True
    _table, chains = parse_ref(result.ref or "")
    assert len(chains) == 1
    chain = chains[0]
    assert chain == chain_name("nftables", block_action())
    rules = fake.rules(chain)
    assert len(rules) == 1
    rule = rules[0]
    assert rule[:4] == ["ip", "daddr", "203.0.113.55", "drop"]
    assert "vigil:block_ip:203.0.113.55" in rule  # comment records provenance


def test_reapply_is_idempotent_one_rule_total() -> None:
    fake = FakeNft()
    executor = make_executor(fake)

    first = asyncio.run(executor.apply(block_action(), 900))
    second = asyncio.run(executor.apply(block_action(), 900))

    assert first.success and second.success
    assert first.ref == second.ref  # deterministic identity
    chain = chain_name("nftables", block_action())
    assert len(fake.rules(chain)) == 1  # flushed, not duplicated
    assert fake.add_table_calls == 1  # table created exactly once


def test_revert_removes_the_chain() -> None:
    fake = FakeNft()
    executor = make_executor(fake)
    result = asyncio.run(executor.apply(block_action(), 900))
    chain = chain_name("nftables", block_action())
    assert fake.rules(chain)  # present before revert

    revert = asyncio.run(executor.revert(result.ref or ""))

    assert revert.success is True
    assert f"inet {nftables.TABLE}/{chain}" not in fake.chains  # absent after


def test_revert_of_an_already_gone_chain_succeeds() -> None:
    fake = FakeNft()
    executor = make_executor(fake)
    result = asyncio.run(executor.apply(block_action(), 900))
    ref = result.ref or ""
    _table, chains = parse_ref(ref)
    del fake.chains[f"inet {nftables.TABLE}/{chains[0]}"]  # operator removed it

    revert = asyncio.run(executor.revert(ref))

    assert revert.success is True  # goal state already reached, no retry loop


def test_invalid_ip_target_is_rejected_before_any_command() -> None:
    fake = FakeNft()
    executor = make_executor(fake)

    result = asyncio.run(executor.apply(block_action("not-an-ip"), 900))

    assert result.success is False
    assert result.error is not None and result.error.startswith("invalid")
    assert fake.tables == set() and fake.chains == {}  # nothing ran


def test_unsupported_action_type_is_rejected() -> None:
    fake = FakeNft()
    executor = make_executor(fake)
    action = Action(
        action_type="isolate_host", executor="nftables", target="node-1", ttl_seconds=60
    )

    result = asyncio.run(executor.apply(action, 60))

    assert result.success is False
    assert result.error == "unsupported_action_type:isolate_host"
    assert fake.chains == {}


def test_block_domain_resolves_and_pins_addresses() -> None:
    fake = FakeNft()
    resolved: list[str] = []

    async def resolver(domain: str) -> list[str]:
        resolved.append(domain)
        return ["198.51.100.7", "2001:db8::7"]

    executor = make_executor(fake, resolver=resolver)

    result = asyncio.run(executor.apply(domain_action(), 600))

    assert result.success is True
    assert resolved == ["c2.example"]
    chain = chain_name("nftables", domain_action())
    rules = fake.rules(chain)
    assert len(rules) == 2
    families = sorted(rule[0] for rule in rules)
    assert families == ["ip", "ip6"]  # v4 and v6 both pinned
    assert all("c2.example" in " ".join(rule) for rule in rules)  # provenance


def test_unresolvable_domain_fails_without_leaving_rules() -> None:
    fake = FakeNft()

    async def resolver(domain: str) -> list[str]:
        return []

    executor = make_executor(fake, resolver=resolver)

    result = asyncio.run(executor.apply(domain_action(), 600))

    assert result.success is False
    assert result.error == "domain_unresolved:c2.example"
    assert fake.chains == {}  # no empty chain posing as containment


def test_domain_shape_is_validated_before_resolution() -> None:
    fake = FakeNft()
    executor = make_executor(fake)

    result = asyncio.run(executor.apply(domain_action("not a domain"), 600))

    assert result.success is False
    assert result.error is not None and result.error.startswith("invalid_domain")
    assert fake.chains == {}


def test_command_failure_fails_the_whole_apply() -> None:
    fake = FakeNft()
    executor = make_executor(fake)

    # Wrap the fake so the flush (the first command after ensure) fails.
    async def failing(argv: list[str]) -> tuple[int, str, str]:
        if argv[1] == "flush":
            return (1, "", "boom")
        return await fake(argv)

    executor = NftablesExecutor("nftables", failing)
    result = asyncio.run(executor.apply(block_action(), 900))

    assert result.success is False
    assert result.ref is None
    assert result.error is not None and result.error.startswith("nft_error:1:")


def test_refs_round_trip() -> None:
    ref = nftables.ref_for(["blk_aaa", "blk_bbb"])
    table, chains = parse_ref(ref)
    assert table == nftables.TABLE
    assert chains == ["blk_aaa", "blk_bbb"]
    with pytest.raises(ValueError):
        parse_ref(json.dumps({"table": "other", "chains": ["x"]}))
    with pytest.raises(ValueError):
        parse_ref("not json at all")

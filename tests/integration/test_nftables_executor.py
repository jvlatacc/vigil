"""Real nftables enforcement: the executor against a live table.

The unit suite proves the honesty ladder against scripted replies; this one
proves the commands it builds are commands nft actually accepts — the
element lands with its timeout, the drop rule exists, undo removes the
element, and undoing a never-applied block is a no-op success. Skipped by
default (needs the nft binary and CAP_NET_ADMIN — an unprivileged runner
collects nothing but the skip), and it uses TEST-NET-2 so no real address
is ever the subject.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from core.edge.executors import (
    BLOCKED,
    CLEAR,
    EXECUTED,
    NFT_SET,
    NFT_TABLE,
    NO_OP,
    NftablesBlockIpExecutor,
)
from core.edge.policy import EdgeAction

pytestmark = [pytest.mark.integration]


def _nft(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["nft", *args], capture_output=True, text=True, timeout=15)


def _nftables_capable() -> bool:
    """The same probe selection uses: binary present AND privileged enough
    to read the ruleset — the capability creating the owned table needs."""
    if shutil.which("nft") is None:
        return False
    return _nft(["list", "ruleset"]).returncode == 0


if not _nftables_capable():
    pytest.skip(
        "real-nftables enforcement needs the nft binary and CAP_NET_ADMIN;"
        " skipped by default per the repo's integration-marker conventions",
        allow_module_level=True,
    )

ACTION = EdgeAction(type="block_ip", ttl_minutes=1)
TARGET = "198.51.100.7"  # TEST-NET-2 — documentation space, as in probes.py


@pytest.fixture
def warden_table():
    """Best-effort teardown: leave the host without the owned table."""
    yield
    _nft(["delete", "table", "inet", NFT_TABLE])


def _element_get() -> subprocess.CompletedProcess[str]:
    return _nft(["get", "element", "inet", NFT_TABLE, NFT_SET, "{", TARGET, "}"])


class TestRealNftablesEnforcement:
    def test_enforce_lands_an_element_with_its_timeout(self, warden_table):
        executor = NftablesBlockIpExecutor()
        result = executor.enforce(ACTION, TARGET)
        assert result.success is True, result.message
        assert result.status == EXECUTED
        assert result.end_state == BLOCKED
        # Independent verification, not the executor's word for it:
        assert _element_get().returncode == 0, "element did not land in the set"
        listing = _nft(["list", "set", "inet", NFT_TABLE, NFT_SET])
        assert "timeout" in listing.stdout, "the set cannot hold TTLs"

    def test_the_drop_rule_makes_the_set_mean_something(self, warden_table):
        """An element nobody drops on is bookkeeping, not enforcement — the
        owned chain's rule referencing the set is part of the guarantee."""
        executor = NftablesBlockIpExecutor()
        assert executor.enforce(ACTION, TARGET).success
        table = _nft(["list", "table", "inet", NFT_TABLE])
        assert "@" + NFT_SET in table.stdout

    def test_repeated_enforce_is_a_no_op(self, warden_table):
        executor = NftablesBlockIpExecutor()
        assert executor.enforce(ACTION, TARGET).status == EXECUTED
        again = executor.enforce(ACTION, TARGET)
        assert again.success is True
        assert again.status == NO_OP

    def test_undo_removes_a_live_block(self, warden_table):
        executor = NftablesBlockIpExecutor()
        assert executor.enforce(ACTION, TARGET).success
        result = executor.undo(ACTION, TARGET)
        assert result.success is True, result.message
        assert result.end_state == CLEAR
        assert _element_get().returncode != 0, "the element survived the undo"

    def test_undo_of_a_never_applied_block_is_a_no_op_success(self, warden_table):
        result = NftablesBlockIpExecutor().undo(ACTION, TARGET)
        assert result.success is True
        assert result.status == NO_OP
        assert result.end_state == CLEAR

"""Unit tests for core.llm.providers.catalog_sync.

Ported from the deleted ``test_bifrost_admin.py`` minus every assertion about
Bifrost's admin API. What the sync still owes its callers is unchanged: one
pass over each active provider row that leaves the dropdown cache and the
live-meta cache agreeing, survives an unreachable upstream, and doesn't
stampede upstream when two callers arrive at once.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

os.environ.setdefault("DEV_MODE", "true")

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO))

from core.llm.providers import catalog_sync  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeProviderRow:
    def __init__(self, provider_id, provider_type):
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.base_url = None
        self.api_key_ref = None
        self.config = {}
        self.is_active = True
        self.is_default = False


class _FakeSessionScope:
    """Stand-in for db_manager.session_scope() context manager."""

    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        class _S:
            def __init__(self, rows):
                self._rows = rows

            def query(self, model):
                class _Q:
                    def __init__(self, rows):
                        self._rows = rows

                    def filter(self, *_):
                        return self

                    def all(self):
                        return self._rows

                return _Q(self._rows)

        return _S(self._rows)

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDBManager:
    def __init__(self, rows):
        self._rows = rows
        self._engine = object()  # truthy so initialize() isn't called

    def initialize(self):
        self._engine = object()

    def session_scope(self):
        return _FakeSessionScope(self._rows)


class _M:
    def __init__(self, mid):
        self.id = mid
        self.display_name = mid
        self.context_window = 0
        self.capabilities = {}


def _patch_db(monkeypatch, rows):
    fake_db = _FakeDBManager(rows)
    monkeypatch.setattr(
        "core.storage.connection.get_db_manager",
        lambda: fake_db,
        raising=False,
    )


def _reset_registry():
    from core.llm.providers import registry as model_registry

    model_registry._MODEL_LIST_CACHE.clear()
    model_registry._EXTRA_IDS.clear()
    model_registry.clear_live_meta()


def test_sync_all_populates_dropdown_cache_with_live_models_and_extras(monkeypatch):
    """One call writes the dropdown cache: live ids first, extras appended.

    Extras exist precisely for ids upstream stopped listing, so they are
    unioned in rather than replacing anything.
    """
    _reset_registry()

    rows = [_FakeProviderRow("ant-default", "anthropic")]
    _patch_db(monkeypatch, rows)

    async def fake_fetch_row(row_dict, discovery):
        return [_M("claude-opus-4-7"), _M("claude-haiku-4-5-20251001")]

    monkeypatch.setattr(catalog_sync, "_fetch_meta_for_row", fake_fetch_row)
    monkeypatch.setenv("ANTHROPIC_EXTRA_MODELS", "claude-3-5-haiku-20241022")

    result = asyncio.run(catalog_sync.sync_all_provider_models())

    expected = [
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
        "claude-3-5-haiku-20241022",
    ]
    from core.llm.providers.registry import _MODEL_LIST_CACHE

    assert _MODEL_LIST_CACHE.get("ant-default") == expected
    assert result["models_by_provider"]["ant-default"] == expected
    _reset_registry()


def test_sync_all_keeps_same_type_rows_separate(monkeypatch):
    """Two anthropic rows with different keys keep their own model lists.

    Bifrost forced a union here because its allow-list was per provider
    *type*; nothing downstream needs that now, and unioning would offer each
    row models its own key can't serve.
    """
    _reset_registry()

    rows = [
        _FakeProviderRow("ant-dev", "anthropic"),
        _FakeProviderRow("ant-prod", "anthropic"),
    ]
    _patch_db(monkeypatch, rows)

    async def fake_fetch_row(row_dict, discovery):
        if row_dict["provider_id"] == "ant-dev":
            return [_M("claude-opus-4-7"), _M("claude-haiku-4-5-20251001")]
        return [_M("claude-opus-4-7"), _M("claude-sonnet-4-6")]

    monkeypatch.setattr(catalog_sync, "_fetch_meta_for_row", fake_fetch_row)
    monkeypatch.setenv("ANTHROPIC_EXTRA_MODELS", "")

    asyncio.run(catalog_sync.sync_all_provider_models())

    from core.llm.providers.registry import _MODEL_LIST_CACHE

    assert _MODEL_LIST_CACHE.get("ant-dev") == [
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
    ]
    assert _MODEL_LIST_CACHE.get("ant-prod") == [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
    ]
    _reset_registry()


def test_sync_all_falls_back_when_fetch_fails(monkeypatch):
    """An unreachable upstream yields bootstrap + extras, not an empty list.

    An empty dropdown reads as "this provider has no models" — a failed
    fetch must not be indistinguishable from a provider that serves nothing.
    """
    _reset_registry()

    rows = [_FakeProviderRow("ant-default", "anthropic")]
    _patch_db(monkeypatch, rows)

    async def fake_fetch_row(row_dict, discovery):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(catalog_sync, "_fetch_meta_for_row", fake_fetch_row)
    monkeypatch.setenv("ANTHROPIC_EXTRA_MODELS", "legacy-1")

    asyncio.run(catalog_sync.sync_all_provider_models())

    from core.llm.providers.registry import _MODEL_LIST_CACHE

    row_list = _MODEL_LIST_CACHE.get("ant-default")
    assert "claude-opus-4-7" in row_list  # from bootstrap
    assert "legacy-1" in row_list  # extras applied even on failure
    _reset_registry()


def test_sync_all_coalesces_concurrent_callers(monkeypatch):
    """Two simultaneous callers should share a single upstream fetch pass.

    Prevents a dropdown cold-load from doubling upstream load when it
    races the scheduled refresher's first tick.
    """
    _reset_registry()

    rows = [_FakeProviderRow("ant-default", "anthropic")]
    _patch_db(monkeypatch, rows)

    fetch_calls = {"n": 0}
    gate = asyncio.Event()

    async def slow_fake_fetch_row(row_dict, discovery):
        fetch_calls["n"] += 1
        # Hold the sync open long enough for the second caller to join.
        await gate.wait()
        return [_M("claude-opus-4-7")]

    monkeypatch.setattr(catalog_sync, "_fetch_meta_for_row", slow_fake_fetch_row)
    monkeypatch.setenv("ANTHROPIC_EXTRA_MODELS", "")

    async def _race():
        task_a = asyncio.create_task(catalog_sync.sync_all_provider_models())
        # Yield so task_a enters the critical section and claims the slot.
        await asyncio.sleep(0)
        task_b = asyncio.create_task(catalog_sync.sync_all_provider_models())
        # Let task_b also start and try to join the in-flight future.
        await asyncio.sleep(0)
        gate.set()
        return await asyncio.gather(task_a, task_b)

    results = asyncio.run(_race())

    # Exactly one upstream fetch despite two callers.
    assert fetch_calls["n"] == 1
    assert results[0]["models_by_provider"] == results[1]["models_by_provider"]
    _reset_registry()


def test_cache_has_no_ttl():
    """Cache entries are valid indefinitely until overwritten/invalidated.

    Before the drift-prevention refactor this had a 60s TTL that caused
    periodic latency spikes when the UI hit an expired entry.
    """
    from core.llm.providers.registry import _MODEL_LIST_CACHE

    _MODEL_LIST_CACHE.clear()
    _MODEL_LIST_CACHE["p1"] = ["a", "b"]

    import time as _time

    original = _time.time

    try:
        # Shift time far into the future. If a TTL lingered, .get() would
        # drop the entry.
        _time.time = lambda: original() + 10_000_000  # type: ignore[assignment]
        assert _MODEL_LIST_CACHE.get("p1") == ["a", "b"]
    finally:
        _time.time = original  # type: ignore[assignment]
    _MODEL_LIST_CACHE.clear()


def test_fetch_meta_for_row_ollama_bypasses_ssrf_ip_gate():
    """The ollama branch must pass ``allow_loopback=True``.

    The row's ``base_url`` was persisted by a ``settings.write`` admin
    (shape-validated at save time), and self-hosted Ollama on a
    loopback/private address is the expected deployment. Without the
    flag, the scheduled sync re-runs the SSRF IP gate and fails with
    "resolved address ... is disallowed: private address" for any
    RFC1918 host — even though the admin-gated discover-models and
    test endpoints reach the same URL fine.
    """
    calls: Dict[str, Any] = {}

    class _FakeDiscovery:
        @staticmethod
        async def fetch_ollama_models(base_url=None, *, allow_loopback=False):
            calls["base_url"] = base_url
            calls["allow_loopback"] = allow_loopback
            return []

    row = {
        "provider_id": "ollama",
        "provider_type": "ollama",
        "base_url": "http://10.64.201.1:11434",
        "api_key_ref": None,
        "config": {},
    }

    out = asyncio.run(catalog_sync._fetch_meta_for_row(row, _FakeDiscovery))

    assert out == []
    assert calls == {
        "base_url": "http://10.64.201.1:11434",
        "allow_loopback": True,
    }

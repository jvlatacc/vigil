"""Model-catalog refresh for every configured LLM provider.

Vigil needs one authoritative answer to "which models can this provider
serve?", and it needs it in two places: the Settings dropdown, and the
live-meta cache that pricing and context-window lookups read. This module
computes that answer and writes both.

It replaces ``core.llm.bifrost.admin``, which did the same discovery pass and
then pushed the union of each provider *type*'s models to Bifrost's allow-list
through its admin API. That push is gone with Bifrost: AI Gateway routes by URL
path and enforces no allow-list, so there is no third surface to keep in sync
and no reason to union rows of the same type. What remains is discovery and the
two local caches — written in the same pass, so they cannot drift.

The credential story changed with it. Bifrost held one key per provider type in
its own config, which is why the old module resolved a "type key" and pushed it
on every write. Provider keys now live only in the encrypted secret store, keyed
per provider row, and ``core.llm.router.router`` resolves the row's
``api_key_ref`` on each dispatch. Nothing has to be pushed anywhere for a
rotation to take effect — the next call reads the new value.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-flight future used to coalesce concurrent ``sync_all_provider_models``
# calls. If a sync is running and a second caller arrives (e.g. a cold
# dropdown lazy-sync landing during the scheduled refresher's iteration),
# the second caller awaits the same future instead of issuing a duplicate
# round of upstream fetches. None when idle.
_sync_in_flight: Optional["asyncio.Future[Dict[str, Any]]"] = None


async def sync_all_provider_models() -> Dict[str, Any]:
    """Canonical model-catalog refresh for every active LLM provider.

    Single source of truth — called at startup, on a schedule, from the
    refresh endpoints, and lazily on a dropdown cache miss. One call:

    1. Fetches each provider's live upstream catalog via
       ``core.llm.providers.discovery``.
    2. Applies the configured extras (IDs upstream dropped from
       ``/v1/models`` but that still route — e.g. Claude 3.x).
    3. Populates ``_MODEL_LIST_CACHE[provider_id]`` and the live-meta cache
       in ``core.llm.providers.registry``.

    Concurrent calls are coalesced — if a sync is already running (e.g. the
    scheduled refresher kicked off at the same time as a dropdown cold-load),
    the second caller awaits the same future rather than issuing a duplicate
    round of upstream fetches.

    Best-effort per provider: a row whose upstream is unreachable falls back
    to the bootstrap list rather than failing the pass. Returns the computed
    per-row model lists under ``models_by_provider``.
    """
    global _sync_in_flight
    if _sync_in_flight is not None and not _sync_in_flight.done():
        logger.debug("sync_all_provider_models: joining in-flight sync")
        return await _sync_in_flight

    loop = asyncio.get_running_loop()
    _sync_in_flight = loop.create_future()
    try:
        result = await _do_sync_all_provider_models()
        _sync_in_flight.set_result(result)
        return result
    except Exception as exc:
        _sync_in_flight.set_exception(exc)
        raise
    finally:
        # Release the slot so the next scheduled tick or CRUD event can
        # start a fresh sync.
        _sync_in_flight = None


async def _do_sync_all_provider_models() -> Dict[str, Any]:
    # Deferred imports to keep module load cheap.
    from core.llm.providers import discovery
    from core.llm.providers.registry import (
        _FALLBACK_MODELS_BY_PROVIDER,
        _MODEL_LIST_CACHE,
        _register_extras,
        get_extra_model_ids,
        record_live_meta,
    )
    from core.storage.connection import get_db_manager
    from core.storage.models import LLMProviderConfig

    db_manager = get_db_manager()
    if db_manager._engine is None:
        db_manager.initialize()

    # Group active providers by type and detach the state we need, so we
    # don't hold the session open across awaits.
    rows_by_type: Dict[str, List[Dict[str, Any]]] = {}
    with db_manager.session_scope() as session:
        rows = (
            session.query(LLMProviderConfig)
            .filter(LLMProviderConfig.is_active.is_(True))
            .all()
        )
        for row in rows:
            rows_by_type.setdefault(row.provider_type, []).append(
                {
                    "provider_id": row.provider_id,
                    "provider_type": row.provider_type,
                    "base_url": row.base_url,
                    "api_key_ref": row.api_key_ref,
                    "config": dict(row.config or {}),
                }
            )

    per_row_models: Dict[str, List[str]] = {}

    for provider_type, provider_rows in rows_by_type.items():
        # Extras are per-provider-type; apply to every row of this type.
        extras = get_extra_model_ids(provider_type)
        _register_extras(provider_type, extras)

        for row_dict in provider_rows:
            row_ids = await _model_ids_for_row(
                row_dict,
                discovery,
                extras=extras,
                fallback=_FALLBACK_MODELS_BY_PROVIDER.get(provider_type, ()),
                record_live_meta=record_live_meta,
            )
            # Single-writer: populate the dropdown cache with this row's
            # list. ``fetch_provider_models`` reads this same key.
            _MODEL_LIST_CACHE[row_dict["provider_id"]] = row_ids
            per_row_models[row_dict["provider_id"]] = row_ids

    if per_row_models:
        logger.info(
            "Model catalog sync: refreshed %d provider rows across %d types",
            len(per_row_models),
            len(rows_by_type),
        )

    return {"models_by_provider": per_row_models}


async def _model_ids_for_row(
    row_dict: Dict[str, Any],
    discovery,
    *,
    extras,
    fallback,
    record_live_meta,
) -> List[str]:
    """The model ids one provider row should offer, in preference order.

    Live upstream ids first; the bootstrap list instead when upstream is
    unreachable, so the dropdown is never empty; then the configured extras,
    which are unioned in either way because they exist precisely for ids
    upstream no longer lists.
    """
    provider_type = row_dict["provider_type"]
    ids: List[str] = []
    seen: set = set()

    def add(candidates) -> None:
        for mid in candidates:
            if not mid or mid in seen:
                continue
            seen.add(mid)
            ids.append(mid)

    try:
        meta = await _fetch_meta_for_row(row_dict, discovery)
    except Exception as exc:  # noqa: BLE001 - one bad row must not fail the pass
        logger.warning(
            "sync_all_provider_models: discovery failed for %s (%s): %s",
            row_dict["provider_id"],
            provider_type,
            exc,
        )
        meta = None

    if meta is None:
        add(fallback)
    else:
        record_live_meta(provider_type, meta)
        add(m.id for m in meta)

    add(extras)
    return ids


def _resolve_row_key(row_dict: Dict[str, Any]) -> Optional[str]:
    """Resolve one provider row's plaintext secret, or None.

    The row's own ``api_key_ref`` wins; the env-held names are a fallback for
    deployments that never wrote a per-row ref.
    """
    from core.secrets_manager import get_secret

    provider_type = row_dict["provider_type"]
    api_key_ref = row_dict.get("api_key_ref")

    if api_key_ref:
        try:
            val = get_secret(api_key_ref)
            if val:
                return val
        except Exception as exc:  # noqa: BLE001
            logger.debug("secret lookup for %s failed: %s", api_key_ref, exc)
    if provider_type == "anthropic":
        return get_secret("ANTHROPIC_API_KEY") or get_secret("CLAUDE_API_KEY")
    if provider_type == "openai":
        return get_secret("OPENAI_API_KEY")
    return None


async def _fetch_meta_for_row(row_dict: Dict[str, Any], discovery) -> Optional[list]:
    """Call the appropriate discovery function for one provider row.

    Returns ``None`` when the row isn't usable (e.g. no API key). The caller
    falls back to the bootstrap list.
    """
    provider_type = row_dict["provider_type"]
    base_url = row_dict.get("base_url")
    config = row_dict.get("config") or {}
    key = _resolve_row_key(row_dict)

    if provider_type == "anthropic":
        if not key:
            logger.info(
                "Catalog sync: no Anthropic key available for %s — skipping",
                row_dict["provider_id"],
            )
            return None
        return await discovery.fetch_anthropic_models(key, base_url=base_url)

    if provider_type == "openai":
        # A key is required only for the real OpenAI cloud; a self-hosted
        # OpenAI-compatible server (vLLM, LM Studio) on a loopback/private
        # address is keyless. Pass the key through (may be None) and let
        # fetch_openai_models enforce it for the allowlisted cloud host only,
        # and allow_loopback so the SSRF IP gate doesn't reject an RFC1918
        # host — the same admin-gated trust anchor as the test and
        # discover-models endpoints, and mirroring the ollama branch below.
        return await discovery.fetch_openai_models(
            key,
            base_url=base_url,
            organization=config.get("organization"),
            allow_loopback=True,
        )

    if provider_type == "ollama":
        # ``base_url`` comes from a persisted provider row, which only a
        # ``settings.write`` admin can create/update (shape-validated at
        # save time). Self-hosted Ollama on a loopback/private address is
        # the expected deployment, so skip the SSRF IP gate here — the
        # same trust anchor as the admin-gated test and discover-models
        # endpoints.
        return await discovery.fetch_ollama_models(base_url, allow_loopback=True)

    logger.debug("Catalog sync: unsupported provider_type %s", provider_type)
    return None


def sync_after_ollama_start() -> dict:
    """Refresh the model catalog once a freshly-started Ollama is reachable.

    Starting Ollama alone accomplishes nothing user-visible: until the catalog
    is re-discovered, no Ollama model is selectable in Settings and the button
    "succeeds" with nothing to show for it.

    Passed as the ``post_start_sync`` argument to
    ``core.platform.ollama_supervisor.start`` by a composition root — platform
    supervises the process, this decides what a running Ollama means for the
    model catalog. Awaits the sync rather than firing it off so the caller can
    report ``catalog_synced`` truthfully. Callers run in a threadpool thread
    with no running loop; if a loop *is* running we fall back to scheduling,
    since ``asyncio.run`` would raise.

    Best-effort throughout — an upstream still booting must not fail the start.
    """
    try:
        from core.llm.providers.registry import invalidate_model_cache

        invalidate_model_cache()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(sync_all_provider_models())
            return {"catalog_synced": True}
        asyncio.get_running_loop().create_task(sync_all_provider_models())
        return {"catalog_synced": False, "catalog_sync_scheduled": True}
    except Exception as e:  # noqa: BLE001
        logger.info("Model catalog sync after Ollama start did not complete: %s", e)
        return {"catalog_synced": False, "catalog_sync_error": str(e)}

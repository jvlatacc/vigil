"""The connection-state machine for OAuth-configured remote MCP servers.

One MCP server with an ``auth`` block is one connection, and its state is
one of the five an operator can act on: ``disabled`` (toggled off),
``dormant`` (secrets the auth block names are unresolved), ``needs_consent``
(an authorization-code grant waiting for its one interactive consent),
``connected`` (a valid or refreshable token), or ``error`` (the last
acquisition attempt failed).

Two kinds of knowledge meet here, and neither is trusted alone:

* **Live knowledge** -- the :class:`OAuthTokenProvider` for the server,
  whose in-memory state is the freshest thing about the current process's
  token attempts, plus the catalog/secrets answers about enabled state and
  credential presence.
* **Last-known knowledge** -- the ``oauth_connections`` row, which survives
  a restart and is the only knowledge there is before this process has
  tried anything.

Resolution rules (:func:`resolve_connection_state`) are a pure function so
every transition is unit-testable and the precedence -- disabled over
dormant over live provider state over last-known state -- is written down
in one place.

Every write to ``oauth_connections`` passes through :func:`sanitize_error`;
``last_error`` is operator-display text, and an error message that carried
token material would make the table a leak.
"""

import enum
import logging
import re
from datetime import datetime, timezone
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence, Tuple

from core.integrations.mcp.oauth import (
    OAuthTokenProvider,
    ProviderState,
    ServerAuthConfig,
    TokenError,
    token_providers,
)
from core.secrets import get_secret
from core.storage.models import OAuthConnection
from core.storage.models.mcp_oauth import VALID_CONNECTION_STATUSES
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow

logger = logging.getLogger(__name__)


class ConnectionState(str, enum.Enum):
    """The operator-visible states, matching ``VALID_CONNECTION_STATUSES``."""

    DISABLED = "disabled"
    DORMANT = "dormant"
    NEEDS_CONSENT = "needs_consent"
    CONNECTED = "connected"
    ERROR = "error"


# Patterns that would smuggle credential material into an error string.
# The token provider's messages are engineered safe (the aad_token.py bar);
# this is the second layer, at the storage boundary, so a future caller
# cannot undo that engineering by passing raw exception text.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_QP_RE = re.compile(
    r"(?i)((?:access_token|refresh_token|id_token|code|token|client_secret)"
    r"(?:=|:\s*))([A-Za-z0-9._~+/=-]{8,})"
)

_MAX_ERROR_CHARS = 500


def sanitize_error(message: str) -> str:
    """Make an error string safe to store and show.

    Redacts the shapes credential material takes in practice -- JWTs,
    ``Bearer`` headers, and token-bearing query parameters -- rather than
    trusting every caller to have written a clean message. The result is
    also capped at 500 chars so a verbose stack cannot bloat a status row.
    """
    cleaned = _JWT_RE.sub("<redacted>", message)
    cleaned = _BEARER_RE.sub("Bearer <redacted>", cleaned)
    cleaned = _SECRET_QP_RE.sub(r"\1<redacted>", cleaned)
    if len(cleaned) > _MAX_ERROR_CHARS:
        cleaned = cleaned[:_MAX_ERROR_CHARS] + "..."
    return cleaned


def resolve_connection_state(
    *,
    enabled: bool,
    grant: str,
    missing_secrets: Sequence[str] = (),
    provider_state: Optional[ProviderState] = None,
    stored_status: Optional[str] = None,
    refresh_token_present: bool = False,
) -> ConnectionState:
    """Resolve one server's connection state. Pure; see the module docstring.

    ``enabled`` and ``missing_secrets`` are structural and win first: an
    operator who toggled a server off wants it off, and a server whose
    auth-block secrets do not resolve cannot try anything. A live provider
    state outranks the stored row -- it is this process's latest attempt --
    except ``PENDING`` (nothing attempted yet), which defers. Stored status
    is sticky below that: an ``error`` row does not become ``connected``
    because a refresh token still sits in the store -- the issuer is the
    judge of that, and it refused.
    """
    if not enabled:
        return ConnectionState.DISABLED
    if missing_secrets:
        return ConnectionState.DORMANT
    if provider_state is ProviderState.ERROR:
        return ConnectionState.ERROR
    if provider_state is ProviderState.NEEDS_CONSENT:
        return ConnectionState.NEEDS_CONSENT
    if provider_state is ProviderState.CONNECTED:
        return ConnectionState.CONNECTED
    if stored_status in VALID_CONNECTION_STATUSES:
        return ConnectionState(stored_status)
    if refresh_token_present:
        # A refresh token in the store is a refreshable token: connected,
        # per the definition, even though this process has not used it yet.
        return ConnectionState.CONNECTED
    # Nothing is known beyond the config itself. An authorization-code grant
    # cannot work until somebody consents; a client-credentials server with
    # resolvable secrets is dormant the way the provider's ``PENDING`` maps
    # onto the operator's dormant display.
    if grant == "authorization_code":
        return ConnectionState.NEEDS_CONSENT
    return ConnectionState.DORMANT


def auth_config_for(
    server_name: str, auth: Optional[Mapping[str, Any]]
) -> Tuple[Optional[ServerAuthConfig], Optional[str]]:
    """Parse a server's ``auth`` block into a config.

    Returns ``(config, None)`` or ``(None, safe_error)``. A server with no
    auth block is simply not OAuth-managed -- ``None`` for both.
    """
    if not auth:
        return None, None
    try:
        return ServerAuthConfig.from_server_entry(server_name, auth), None
    except TokenError as exc:
        return None, sanitize_error(str(exc))


def ensure_provider(config: ServerAuthConfig) -> OAuthTokenProvider:
    """The registry's provider for this config, configured if needed.

    One provider per server, rebuilt only when its auth block changed -- so
    a token lifecycle is not silently reset by a status poll.
    """
    registry = token_providers()
    existing = registry.provider_for(config.server_name)
    if existing is not None and existing.config == config:
        return existing
    return registry.configure(config)


def missing_auth_secrets(config: ServerAuthConfig) -> List[str]:
    """Secret-store keys the auth block references that do not resolve.

    A missing client secret is the OAuth analogue of the env-placeholder
    dormancy the catalog already reports -- the connection cannot even try.
    A missing refresh token is not here: that is ``needs_consent``, not
    dormant, and naming it as a missing credential would tell the operator
    to set a token instead of clicking Connect.
    """
    missing = []
    if config.client_secret_key and not _get_secret_safe(config.client_secret_key):
        missing.append(config.client_secret_key)
    return missing


def _get_secret_safe(key: str) -> Optional[str]:
    try:
        return get_secret(key)
    except (
        Exception
    ):  # noqa: BLE001 - a secrets store that cannot answer is an unset secret
        logger.warning("Secrets store lookup for %s failed; treating as unset", key)
        return None


def _stored_status(stored: Optional[OAuthConnection], grant: str) -> Optional[str]:
    """The stored row's status, when the row can still be believed.

    A row whose grant disagrees with the server's current auth block is a
    stale story about a different configuration; it is ignored (and the
    next sync overwrites it).
    """
    if stored is None or stored.grant != grant:
        return None
    return stored.status


def status_fields(
    server_name: str,
    auth: Optional[Mapping[str, Any]],
    *,
    enabled: bool,
    session: Any = None,
) -> Optional[Tuple[ConnectionState, Optional[str], Dict[str, Any]]]:
    """The connection-state fields for one server's status row.

    Returns ``(state, last_error, oauth_fields)``; ``last_error`` is None
    unless the state has a reason to name. ``None`` overall when the server
    carries no auth block -- the five states describe OAuth connections, and
    pinning them onto plain stdio servers would invent an answer for a
    question their transport cannot ask. An auth block that does not parse
    reports ``error`` with no metadata, because none can honestly be
    attached to a config we could not read. The return never raises: a
    database that cannot answer degrades the row to live knowledge, which
    is what a status poll is for.
    """
    config, config_error = auth_config_for(server_name, auth)
    if config is None:
        if config_error is not None:
            return ConnectionState.ERROR, config_error, {}
        return None

    provider = ensure_provider(config)
    fresh_error = provider.last_error or None
    try:
        return sync_connection_state(
            config,
            enabled=enabled,
            missing_secrets=missing_auth_secrets(config),
            provider=provider,
            fresh_error=fresh_error,
            session=session,
        )
    except Exception:  # noqa: BLE001 - a status poll degrades, never fails
        logger.warning(
            "Connection-state sync for %s failed; reporting live state",
            server_name,
            exc_info=True,
        )
        state = resolve_connection_state(
            enabled=True,
            grant=config.grant,
            missing_secrets=missing_auth_secrets(config),
            provider_state=provider.state,
        )
        last_error = sanitize_error(fresh_error) if fresh_error else None
        return state, last_error, _operator_fields(config, None, provider)


def _operator_fields(
    config: ServerAuthConfig,
    stored: Optional[OAuthConnection],
    provider: Optional[OAuthTokenProvider],
    *,
    missing_secrets: Sequence[str] = (),
) -> Dict[str, Any]:
    """The non-secret per-server fields the status row carries."""
    expires_at = provider.access_token_expires_at if provider else None
    return {
        "grant": config.grant,
        "issuer_url": config.issuer_url,
        "client_id": config.client_id,
        "scopes": list(config.scopes),
        "resource": config.resource_url,
        "last_refreshed_at": (
            stored.last_refreshed_at.isoformat()
            if stored and stored.last_refreshed_at
            else None
        ),
        "missing_secrets": list(missing_secrets),
        "token_expires_at": (
            datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
            if expires_at
            else None
        ),
    }


def sync_connection_state(
    config: ServerAuthConfig,
    *,
    enabled: bool,
    missing_secrets: Sequence[str] = (),
    provider: Optional[OAuthTokenProvider] = None,
    fresh_error: Optional[str] = None,
    session: Any = None,
) -> Tuple[ConnectionState, Optional[str], Dict[str, Any]]:
    """Resolve the state and remember it, if it changed.

    Returns ``(state, last_error, operator_fields)`` for the status row.
    Upserts are diff-based, so a status poll in steady state writes nothing;
    a transition *into* ``connected`` stamps ``last_refreshed_at``. A
    database that cannot answer is logged and skipped -- the row is
    operator-display memory, and the connection itself must not depend on
    it. Callers pass an already-open ``session`` to join their transaction;
    none is opened otherwise.
    """
    stored: Optional[OAuthConnection] = None
    db_open = True
    try:
        with unit_of_work(session) as db:
            stored = (
                db.query(OAuthConnection)
                .filter(OAuthConnection.server_name == config.server_name)
                .first()
            )
    except Exception:  # noqa: BLE001 - display memory, not a dependency
        logger.warning(
            "Could not read oauth_connections for %s; reporting live state",
            config.server_name,
            exc_info=True,
        )
        stored = None
        db_open = False

    refresh_present = config.grant == "authorization_code" and bool(
        _get_secret_safe(config.refresh_key)
    )
    state = resolve_connection_state(
        enabled=enabled,
        grant=config.grant,
        missing_secrets=missing_secrets,
        provider_state=provider.state if provider else None,
        stored_status=_stored_status(stored, config.grant),
        refresh_token_present=refresh_present,
    )

    last_error: Optional[str] = None
    if state is ConnectionState.CONNECTED:
        last_error = None
    elif fresh_error is not None:
        last_error = sanitize_error(fresh_error)
    elif stored is not None and stored.status == state.value:
        last_error = stored.last_error

    fields = _operator_fields(config, stored, provider, missing_secrets=missing_secrets)
    if not db_open:
        return state, last_error, fields

    became_connected = state is ConnectionState.CONNECTED and (
        stored is None or stored.status != ConnectionState.CONNECTED.value
    )
    try:
        with unit_of_work(session) as db:
            row = (
                db.query(OAuthConnection)
                .filter(OAuthConnection.server_name == config.server_name)
                .first()
            )
            if row is not None and row.grant != config.grant:
                # A stale story about a different configuration; start blank.
                db.delete(row)
                db.flush()
                row = None
            changed = row is None or (
                row.status != state.value
                or row.last_error != last_error
                or row.issuer_url != fields["issuer_url"]
                or row.client_id != fields["client_id"]
                or list(row.scopes or []) != fields["scopes"]
                or row.resource != fields["resource"]
            )
            if not changed:
                return state, last_error, fields
            if row is None:
                row = OAuthConnection(
                    server_name=config.server_name,
                    grant=config.grant,
                    status=state.value,
                )
                db.add(row)
            row.grant = config.grant
            row.issuer_url = fields["issuer_url"]
            row.client_id = fields["client_id"]
            row.scopes = fields["scopes"]
            row.resource = fields["resource"]
            row.status = state.value
            row.last_error = last_error
            if became_connected:
                row.last_refreshed_at = utcnow()
            fields["last_refreshed_at"] = (
                row.last_refreshed_at.isoformat() if row.last_refreshed_at else None
            )
    except Exception:  # noqa: BLE001 - same tolerance as the read leg
        logger.warning(
            "Could not persist oauth_connections for %s; the next poll re-syncs",
            config.server_name,
            exc_info=True,
        )
    return state, last_error, fields


def stored_connections(session: Any = None) -> Dict[str, OAuthConnection]:
    """Every stored connection row, keyed by server name; ``{}`` if unreadable."""
    try:
        with unit_of_work(session) as db:
            rows = db.query(OAuthConnection).all()
            return {row.server_name: row for row in rows}
    except (
        Exception
    ):  # noqa: BLE001 - an unreadable table is no knowledge, not a failure
        logger.warning("Could not read oauth_connections", exc_info=True)
        return {}


def prune_connections(keep: Collection[str], session: Any = None) -> int:
    """Drop rows for servers that no longer exist or no longer carry an
    auth block. Returns how many rows went. Never raises."""
    try:
        with unit_of_work(session) as db:
            stale = [
                row.server_name
                for row in db.query(OAuthConnection).all()
                if row.server_name not in keep
            ]
            for name in stale:
                db.query(OAuthConnection).filter(
                    OAuthConnection.server_name == name
                ).delete()
            return len(stale)
    except Exception:  # noqa: BLE001 - housekeeping, not a dependency
        logger.warning("Could not prune oauth_connections", exc_info=True)
        return 0

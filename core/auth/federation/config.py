"""How federation finds its broker: env floor, SystemConfig override.

Two channels, one rule: the environment is the operator's floor (empty
means off — there is no enabled-by-default here), and the ``auth.oidc``
SystemConfig row, written through the settings surface, can supply the
same non-secret values at runtime and act as a kill switch without a
restart. The client secret never travels either channel — it is read
through ``get_secret``, the one credential-read channel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from core.config import get_settings
from core.secrets import get_secret

logger = logging.getLogger(__name__)

#: The SystemConfig key an operator's toggle writes, mirroring
#: ``mcp.server_enabled``.
CONFIG_KEY = "auth.oidc"

#: The secret name. Not the value — that never passes through here.
CLIENT_SECRET_NAME = "OIDC_CLIENT_SECRET"


@dataclass(frozen=True)
class OidcConfig:
    """The federation settings one sign-in runs under."""

    issuer_url: str
    client_id: str
    scopes: Tuple[str, ...]
    groups_claim: str
    redirect_uri: str
    post_login_redirect: str
    enabled: bool
    client_secret: Optional[str] = None


def load_oidc_config() -> OidcConfig:
    """Merge the env floor with the SystemConfig row.

    A database that cannot be read is not a yes and not a no: the env
    floor stands, like the MCP surface gate does.
    """
    settings = get_settings()
    stored = _stored_config()

    def pick(env_value: str, stored_key: str) -> str:
        env = (env_value or "").strip()
        if env:
            return env
        stored_value = stored.get(stored_key)
        return str(stored_value).strip() if stored_value else ""

    issuer_url = pick(settings.oidc_issuer_url, "issuer_url")
    client_id = pick(settings.oidc_client_id, "client_id")
    scopes = pick(settings.oidc_scopes, "scopes") or "openid profile email"
    groups_claim = pick(settings.oidc_groups_claim, "groups_claim") or "groups"

    # Disabled until an issuer and a client exist; the SystemConfig row
    # can then only ever turn it off, never silently on.
    enabled = bool(issuer_url and client_id)
    if "enabled" in stored and not bool(stored["enabled"]):
        enabled = False

    return OidcConfig(
        issuer_url=issuer_url,
        client_id=client_id,
        scopes=tuple(s for s in scopes.split() if s),
        groups_claim=groups_claim,
        redirect_uri=pick(settings.oidc_redirect_uri, "redirect_uri"),
        post_login_redirect=pick(
            settings.oidc_post_login_redirect, "post_login_redirect"
        ),
        enabled=enabled,
    )


def resolve_client_secret() -> Optional[str]:
    """The broker's client secret, through the one credential-read channel."""
    return get_secret(CLIENT_SECRET_NAME)


def _stored_config() -> dict[str, Any]:
    try:
        from core.storage.config_service import get_config_service

        stored = get_config_service().get_system_config(CONFIG_KEY)
    except Exception:  # noqa: BLE001 - a database that cannot be read is not a yes
        logger.warning("Could not read the OIDC federation setting; using env only")
        return {}
    return stored if isinstance(stored, dict) else {}

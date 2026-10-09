"""OAuth connection metadata for remote MCP servers.

One row per OAuth-configured MCP server: what Vigil knows about the
connection, never what could be used to make one. A client secret and a
refresh token are credentials -- they live in the encrypted secrets store
(``core.secrets``), reached through the token provider. Everything a row
holds is what an operator reads on the integrations screen: which grant,
which issuer, whether a token is live, and a safe reason when it is not.

The rows are the last-known state, so the status surface can answer
"which of disabled / dormant / needs_consent / connected / error is this
server in" across a restart, when the token provider's in-memory state is
gone. The resolution rules live with the MCP code
(``core.integrations.mcp.connection_state``); this table only remembers.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

#: The operator-visible connection states. The semantics live in
#: ``core.integrations.mcp.connection_state``; stored here as strings so the
#: table reads without the enum and survives its refactors.
VALID_CONNECTION_STATUSES = frozenset(
    {"disabled", "dormant", "needs_consent", "connected", "error"}
)


class OAuthConnection(Base):
    """Last-known OAuth state of one remote MCP server.

    Non-secret by construction: a reviewer can read every column, the API
    can return every field, and nothing here authenticates anything.
    """

    __tablename__ = "oauth_connections"

    # The server's name in mcp-config.json -- one connection per server, so
    # the name is the key. A server whose auth block is removed has its row
    # deleted by the state machine, not here.
    server_name: Mapped[str] = mapped_column(String(200), primary_key=True)

    # Which grant the connection was built for: the state machine refuses to
    # read a row whose grant disagrees with the server's current auth block,
    # so a reconfigured server starts from blank rather than from a stale
    # story about the old configuration.
    grant: Mapped[str] = mapped_column(String(50), nullable=False)

    # Discovered or configured authorization-server issuer, and the client
    # identity Vigil presents. Identifying, not authenticating.
    issuer_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Requested scopes and the RFC 8707 resource indicator the tokens are
    # bound to. A list, not a joined string: scopes arrive as a list.
    scopes: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    resource: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # One of VALID_CONNECTION_STATUSES. Not a database enum: the vocabulary
    # is a code contract (tests pin it), and a string keeps SQLite tests and
    # the snapshot honest.
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    # When the connection last reached a working token, and a safe reason
    # for the current state when it is not a working one. Sanitized on the
    # write path -- an error message that named a token would make this
    # column a leak, so nothing unsanitized can enter it.
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )

    def to_dict(self) -> dict:
        """What an operator may see. Every field is metadata; none is a secret."""
        return {
            "server_name": self.server_name,
            "grant": self.grant,
            "issuer_url": self.issuer_url,
            "client_id": self.client_id,
            "scopes": list(self.scopes or []),
            "resource": self.resource,
            "status": self.status,
            "last_refreshed_at": (
                self.last_refreshed_at.isoformat() if self.last_refreshed_at else None
            ),
            "last_error": self.last_error,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

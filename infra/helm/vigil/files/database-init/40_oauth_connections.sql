-- Last-known OAuth connection state, one row per remote MCP server.
--
-- The token provider (core/integrations/mcp/oauth.py) keeps access tokens in
-- memory only and its client secrets and refresh tokens in the encrypted
-- secrets store, so nothing survives a restart except what is written here.
-- This table is that memory: the status surface resolves each server's
-- disabled / dormant / needs_consent / connected / error state against it
-- when the process that last talked to the issuer is gone.
--
-- Every column is metadata an operator may read. A client secret or a
-- refresh token must never land in a row -- the write path sanitizes
-- last_error so an error message that carried token material cannot enter,
-- and the token itself never has a column to land in at all.

CREATE TABLE IF NOT EXISTS oauth_connections (
    -- The server's name in mcp-config.json. One connection per server: the
    -- name is the key, and a reconfigured server updates its row in place.
    server_name VARCHAR(200) PRIMARY KEY,

    -- Which grant the connection was built for (client_credentials or
    -- authorization_code). The state machine ignores a row whose grant
    -- disagrees with the server's current auth block, so a reconfigured
    -- server starts from blank rather than from a stale story.
    grant VARCHAR(50) NOT NULL,

    -- Discovered or configured authorization-server issuer, and the client
    -- identity Vigil presents. Identifying, not authenticating.
    issuer_url VARCHAR(500),
    client_id VARCHAR(500),

    -- Requested scopes and the RFC 8707 resource indicator the tokens are
    -- bound to. JSONB because scopes arrive as a list.
    scopes JSONB,
    resource VARCHAR(500),

    -- One of disabled / dormant / needs_consent / connected / error.
    status VARCHAR(32) NOT NULL,

    -- When the connection last reached a working token, and a safe reason
    -- for the current state when it is not a working one.
    last_refreshed_at TIMESTAMP,
    last_error TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

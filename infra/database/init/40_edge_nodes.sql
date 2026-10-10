-- 40_edge_nodes.sql
-- Enrolled edge daemons: one row per daemon, carrying only what enrollment,
-- sync cursors, and revocation need.
--
-- The bearer credential itself is never stored: credential_hash is the
-- SHA-256 hex of it, compared constant-time on every authenticated node call
-- (the same fail-closed shape as AGENT_INTERNAL_TOKEN, per node instead of
-- shared). Status 'revoked' answers every further call with 401 — revocation
-- beats any local allowance the daemon still holds.
--
-- TIMESTAMP (not TIMESTAMPTZ) matches the naive-UTC DateTime columns the ORM
-- declares for this table (core/edge/models.py), as in 35_ip_exclusions.sql.

CREATE TABLE IF NOT EXISTS edge_nodes (
    node_id             VARCHAR(64)  PRIMARY KEY,
    segment_scope       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    credential_hash     VARCHAR(64)  NOT NULL,
    status              VARCHAR(16)  NOT NULL DEFAULT 'active',
    enrolled_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMP,
    last_boot_id        VARCHAR(64),
    last_bundle_version INTEGER,
    revoked_at          TIMESTAMP,
    revoked_by          VARCHAR(100),
    revoke_reason       TEXT,

    CONSTRAINT ck_edge_nodes_status CHECK (status IN ('active', 'revoked')),
    CONSTRAINT ck_edge_nodes_revocation_pair
        CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_edge_nodes_status
    ON edge_nodes (status);

COMMENT ON TABLE edge_nodes IS
    'Enrolled edge daemons: per-node credential hash, sync cursor, revocation state.';

-- down: DROP TABLE IF EXISTS edge_nodes;

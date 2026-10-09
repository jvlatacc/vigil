-- Edge nodes: the identity of every Warden runtime allowed to sync policy and
-- reconcile a journal.
--
-- The control plane had no concept of a managed endpoint before this table:
-- "agent" meant an AI agent, and nothing enrolled, authenticated, or revoked a
-- node. The Local Autonomy Mesh embeds a defending runtime in cluster nodes
-- and VPC gateways, and the first thing that runtime needs is an identity the
-- control plane can issue, recognize, and revoke — because a segment that
-- defends itself while partitioned is only as trustworthy as the node doing
-- the defending.
--
-- The bearer token a node presents is never stored here, only the sha256 of
-- it, the way a password is stored: a read of this table cannot mint a token
-- that authenticates. The hash is unique across nodes, so one token can never
-- stand for two identities and revoking a node cannot silently revoke a
-- second one.
--
-- last_seen is touched by every authenticated contact — a policy fetch, a
-- journal push. It is the control plane's only liveness signal for a node;
-- nothing phones home on a schedule. A NULL last_seen is a node enrolled but
-- never heard from.
--
-- Revocation is recorded, not deleted: status flips to 'revoked' and the row
-- keeps when and by whom, because "when did this node stop being ours" is a
-- question the status bit alone cannot answer. The edge router treats a
-- revoked node as unknown — fail-closed, like every other receiver.

CREATE TABLE IF NOT EXISTS edge_nodes (
    node_id VARCHAR(50) PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL,

    -- Selector labels the control plane matches against a policy pack's
    -- node_selectors ("segment:dmz", "role:gateway"). Empty is legal: a node
    -- can be enrolled before anyone decides which segments it defends.
    segment_labels TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

    status VARCHAR(16) NOT NULL DEFAULT 'active',
    last_seen TIMESTAMP,

    enrolled_at TIMESTAMP NOT NULL DEFAULT NOW(),
    enrolled_by VARCHAR(100) NOT NULL,

    revoked_at TIMESTAMP,
    revoked_by VARCHAR(100),
    revocation_reason TEXT,

    CONSTRAINT ck_edge_nodes_status
        CHECK (status IN ('active', 'revoked')),
    CONSTRAINT ck_edge_nodes_revocation
        CHECK ((status = 'revoked') = (revoked_at IS NOT NULL)),
    CONSTRAINT ck_edge_nodes_revoked_by
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);

-- One token hash ever belongs to one node identity.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_edge_nodes_token_hash
    ON edge_nodes (token_hash);

CREATE INDEX IF NOT EXISTS idx_edge_nodes_status
    ON edge_nodes (status);

COMMENT ON TABLE edge_nodes IS
    'Enrolled Warden edge runtimes: per-node bearer-token identity the control plane can issue and revoke.';
COMMENT ON COLUMN edge_nodes.token_hash IS
    'sha256 hex of the per-node bearer token. The token itself is never stored; a row leak cannot authenticate.';
COMMENT ON COLUMN edge_nodes.last_seen IS
    'Last authenticated contact (policy fetch or journal push). NULL until first contact.';

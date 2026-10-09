-- Signed containment-policy packs, as distributed to edge nodes.
--
-- A Warden node keeps defending its segment while the control plane is
-- unreachable, on the strength of a policy pack it received while connected.
-- This table is the control plane's record of what it signed and handed out:
-- the DSSE envelope exactly as issued, which trust-root keys signed it, and
-- the validity window the signature commits to. Warden verifies the envelope
-- offline against its baked-in trust root before parsing it; this table is
-- the authority the edge router serves from, not a second copy of the truth
-- inside the envelope.
--
-- Versions are monotonic per node: the primary key is (node_id,
-- policy_version), so a node's version stream cannot repeat, and a re-presented
-- version with a different payload hash — a signed pack replayed with different
-- content — is detectable by comparing payload_hash on conflict. One signed
-- pack aimed at a selector ("segment:dmz") lands here once per addressed node.
--
-- At most one policy per node is 'active' — the partial unique index below is
-- what makes "the current policy for this node" a row, not a debate. draft is
-- a pack composed but not yet cleared to serve; revoked withdraws it. The
-- not_before/not_after columns mirror the signed payload for queryability;
-- the payload inside the envelope is authoritative, and these exist so the
-- edge router can judge freshness without opening JSON.
--
-- Status transitions keep their timestamps for the same reason the node's
-- revocation does: an audit that cannot say when a policy stopped applying
-- cannot explain what a node was allowed to do at 13:02.

CREATE TABLE IF NOT EXISTS edge_policies (
    node_id VARCHAR(50) NOT NULL REFERENCES edge_nodes(node_id) ON DELETE CASCADE,
    policy_version INTEGER NOT NULL,

    -- The full DSSE envelope as issued: payload, payloadType, signatures.
    -- Warden verifies before parsing; nothing here needs the plaintext to be
    -- queryable, so it is stored whole.
    envelope JSONB NOT NULL,

    -- sha256 over the payload this version carried. A re-presented version
    -- whose payload hashes differently is tampered or replayed — refuse it.
    payload_hash VARCHAR(64) NOT NULL,

    -- Trust-root key ids of the envelope's signatures, for "which policies
    -- did a since-revoked key sign" without unwrapping every envelope.
    signing_key_ids TEXT[] NOT NULL,

    status VARCHAR(16) NOT NULL DEFAULT 'draft',

    -- Mirrors of the signed payload's validity window, for freshness checks
    -- without parsing the envelope. The payload is authoritative.
    not_before TIMESTAMP NOT NULL,
    not_after TIMESTAMP NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100) NOT NULL,
    activated_at TIMESTAMP,
    revoked_at TIMESTAMP,

    PRIMARY KEY (node_id, policy_version),

    CONSTRAINT ck_edge_policies_status
        CHECK (status IN ('draft', 'active', 'revoked')),
    CONSTRAINT ck_edge_policies_activation
        CHECK ((status IN ('active', 'revoked')) = (activated_at IS NOT NULL)),
    CONSTRAINT ck_edge_policies_revocation
        CHECK ((status = 'revoked') = (revoked_at IS NOT NULL)),
    CONSTRAINT ck_edge_policies_window
        CHECK (not_before <= not_after)
);

-- "The current policy for this node" is at most one row.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_edge_policies_active_per_node
    ON edge_policies (node_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_edge_policies_status
    ON edge_policies (status);

COMMENT ON TABLE edge_policies IS
    'Signed containment-policy packs per node: DSSE envelope, signing key ids, monotonic per-node version, draft/active/revoked.';
COMMENT ON COLUMN edge_policies.envelope IS
    'The full DSSE envelope as issued (payload, payloadType, signatures). Warden verifies offline before parsing.';
COMMENT ON COLUMN edge_policies.payload_hash IS
    'sha256 over the pack payload; a re-presented version hashing differently is tampered or replayed.';

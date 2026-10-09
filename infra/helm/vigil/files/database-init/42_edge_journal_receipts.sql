-- Reconcile receipts: what the control plane accepted from a Warden journal.
--
-- While partitioned, a node journals every decision it makes (a hash-chained
-- JSONL file, the agent_events pattern) and pushes the journal when the
-- control plane answers again. The edge API verifies each batch's chain —
-- sha256(prev_hash ‖ record), gaps rejected with a 409 — merges the accepted
-- records into approval_actions with source=edge provenance, and writes one
-- receipt per accepted batch here.
--
-- A receipt says: "records first_seq..last_seq of this node's journal, citing
-- policy_version, chained up to chain_head, were verified and merged at
-- accepted_at." The node's current chain head is the chain_head of its latest
-- receipt — the server-held head a reconnecting node resumes from, and the
-- position a 409 chain-gap resends after.
--
-- The range is unique per node, so re-pushing a batch the server already
-- accepted (at-least-once delivery is the norm on a flaky link) resolves to
-- the existing receipt instead of a second merge. Idempotency of the merge
-- itself lives on the approval_actions idempotency_key; the unique range
-- makes the receipt side of the same push just as idempotent.

CREATE TABLE IF NOT EXISTS edge_journal_receipts (
    receipt_id VARCHAR(80) PRIMARY KEY,

    node_id VARCHAR(50) NOT NULL REFERENCES edge_nodes(node_id) ON DELETE CASCADE,

    -- The policy version the accepted records cite; legality of a reconciled
    -- record is judged by the policy version, never by wall time.
    policy_version INTEGER NOT NULL,

    first_seq INTEGER NOT NULL,
    last_seq INTEGER NOT NULL,

    -- sha256 of the last accepted record: the server's chain head after this
    -- batch, and where the next push resumes.
    chain_head VARCHAR(64) NOT NULL,

    record_count INTEGER NOT NULL,

    accepted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_edge_journal_receipts_range
        CHECK (last_seq >= first_seq),
    CONSTRAINT ck_edge_journal_receipts_count
        CHECK (record_count >= 1)
);

-- Re-pushing an accepted batch resolves to this receipt, not a second merge.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_edge_journal_receipts_node_range
    ON edge_journal_receipts (node_id, first_seq, last_seq);

-- The per-node chain head is the latest receipt by last_seq.
CREATE INDEX IF NOT EXISTS idx_edge_journal_receipts_node_last_seq
    ON edge_journal_receipts (node_id, last_seq DESC);

COMMENT ON TABLE edge_journal_receipts IS
    'Accepted ranges of a Warden journal: one receipt per verified batch, carrying the per-node chain head the next push resumes from.';
COMMENT ON COLUMN edge_journal_receipts.chain_head IS
    'sha256 of the last accepted record — the server-held chain head after this batch.';

-- 42_edge_node_watermark.sql
-- Reconciliation watermarks (T3, edge sync & reconciliation).
--
-- commit_watermark is the highest local_sequence durably imported for the
-- node — a monotonic max maintained by the event importer (core/edge/
-- events.py), never decreased and never advanced ahead of a durable commit.
-- last_acked_seq is the node's own durable-ack watermark, reported with
-- every heartbeat. Their difference is committed-but-unacknowledged work:
-- acks the node lost (crash before persisting) that the next replay closes
-- when the server reports the committed events back as duplicates.
--
-- TIMESTAMP convention note: no new timestamp columns in this migration.

ALTER TABLE edge_nodes ADD COLUMN IF NOT EXISTS commit_watermark INTEGER;
ALTER TABLE edge_nodes ADD COLUMN IF NOT EXISTS last_acked_seq INTEGER;

COMMENT ON COLUMN edge_nodes.commit_watermark IS
    'Highest local_sequence durably imported for this node (monotonic max).';
COMMENT ON COLUMN edge_nodes.last_acked_seq IS
    'Node-reported durable-ack watermark from its last heartbeat.';

-- down: ALTER TABLE edge_nodes DROP COLUMN IF EXISTS last_acked_seq;
-- down: ALTER TABLE edge_nodes DROP COLUMN IF EXISTS commit_watermark;

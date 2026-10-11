-- Durable snapshots of the CEP engine's in-memory correlation state
-- (core/cep/graph.py, core/cep/snapshot.py). The engine correlates in
-- flight and holds its state in the daemon's memory, so a restart loses
-- it by definition; this table is the recovery point. One row is one
-- envelope: the whole graph plus the pattern engine's machines and
-- seen-ids, written as one JSON payload so a restore reads exactly one
-- row and never stitches half a state from two.
--
-- Latest-wins: restore reads the newest row by created_at and ignores
-- the rest. Older rows are kept for operator forensics (how far apart
-- did snapshots drift during the incident) and pruned only by age.

CREATE TABLE IF NOT EXISTS cep_snapshots (
    id             bigserial   PRIMARY KEY,
    -- Stamped by the server, never by the caller: the loss window after a
    -- crash is measured from this clock, so the daemon cannot shrink it
    -- retroactively by writing its own created_at.
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- The envelope format version the writer used (core.cep.snapshot.
    -- SNAPSHOT_VERSION). Denormalized out of the payload so an operator
    -- can see which rows a given daemon build wrote without opening the
    -- JSON; restore re-checks the copy inside the payload.
    engine_version integer     NOT NULL,
    payload        jsonb       NOT NULL
);

-- The restore query's only access path, and the retention prune's.
CREATE INDEX IF NOT EXISTS idx_cep_snapshots_created
    ON cep_snapshots (created_at DESC);

COMMENT ON TABLE cep_snapshots IS
    'Versioned snapshots of the CEP engine''s in-memory correlation state: entity graph, pattern machines and seen-ids in one JSONB envelope. vigil_app may SELECT and INSERT only; retention prunes by age through prune_cep_snapshots, never through a DELETE grant.';

COMMENT ON COLUMN cep_snapshots.engine_version IS
    'Envelope format version of the writer; a restore from a different version starts fresh rather than guessing.';

-- Retention: the app role holds no DELETE (the agent-ledger pattern in
-- 30_vigil_app_role.sql), so age-based pruning runs through this function.
-- SECURITY DEFINER executes it with the table owner's rights, and the
-- body deletes by age only — the app can prune old snapshots, and can do
-- nothing else to them. search_path is pinned because a definer function
-- that resolves names on the caller's path is a hijack vector.
CREATE OR REPLACE FUNCTION prune_cep_snapshots(max_age interval)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    pruned integer;
BEGIN
    DELETE FROM cep_snapshots WHERE created_at < now() - max_age;
    GET DIAGNOSTICS pruned = ROW_COUNT;
    RETURN pruned;
END;
$$;

COMMENT ON FUNCTION prune_cep_snapshots(interval) IS
    'The only delete path on cep_snapshots: rows older than max_age, executable by vigil_app without a table-level DELETE grant.';

-- The daemon writes and restores snapshots and must never mutate or
-- delete one: an UPDATE path would let a corrupted engine rewrite its own
-- recovery point, and a DELETE path would tempt in-process retention.
-- 30_vigil_app_role.sql blanket-grants all verbs (including via default
-- privileges) to tables created after it runs, so the narrowing is
-- explicit here, exactly as it is for agent_events.
GRANT SELECT, INSERT ON TABLE cep_snapshots TO vigil_app;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE cep_snapshots FROM vigil_app;
GRANT USAGE, SELECT ON SEQUENCE cep_snapshots_id_seq TO vigil_app;

-- Prune is callable by the app role and by nobody else by accident:
-- functions grant EXECUTE to PUBLIC by default.
REVOKE EXECUTE ON FUNCTION prune_cep_snapshots(interval) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION prune_cep_snapshots(interval) TO vigil_app;

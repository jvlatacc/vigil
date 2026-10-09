-- Deception lease registry and recon probe log (feature 5: honey-routing)
--
-- Dynamic honey-routing steers a corroborated recon source into instrumented
-- decoys on a short, reversible lease instead of denying them. These tables
-- are the durable state that makes that safe and auditable:
--
--   deception_leases — one row per attacker redirect. This is the single
--   place the daemon, the API and the console can all see a lease (they are
--   separate processes); the TTL lifecycle (expire, renew under the
--   max-duration cap, kill-switch release) reconciles from here, and the
--   row is the rollback record: backend_ref names the rule the controller
--   created, rollback_result holds the unsteer outcome.
--
--   deception_probes — the recon observations corroboration counts over.
--   The honey-routing posture fires on a count of distinct observations per
--   source inside a window, never on a single finding; this log is that
--   count's evidence, and the sweep prunes anything older than twice the
--   window.
--
-- A lease is born 'pending' (approval row written, backend not yet
-- steered), becomes 'active' on steer success, and leaves the non-terminal
-- states only to 'released' (expiry, kill-switch, operator release) or
-- 'failed' (backend error). Terminal rows are never deleted — they are the
-- audit trail — and every constraint here is mirrored in
-- core/storage/models/deception.py so create_all and this file agree.
--
-- Idempotent via IF NOT EXISTS; safe to re-run.

CREATE TABLE IF NOT EXISTS deception_leases (
    lease_id            VARCHAR(60)  PRIMARY KEY,               -- lease-<hex16>
    attacker_ip         VARCHAR(45)  NOT NULL,                  -- canonical attacker address

    -- The approval row that authorized this lease. approval_actions is the
    -- record of record; SET NULL only on the theoretical day an approval is
    -- purged, so a lease never blocks that table's hygiene.
    action_id           VARCHAR(80)  REFERENCES approval_actions (action_id) ON DELETE SET NULL,

    -- What the redirect covers: the internal targets the probes hit, the
    -- suspicious service ports (never "all traffic"), and the backend that
    -- programmed it (dry_run ships; the reference controller lands later).
    destination_ips     JSONB        NOT NULL DEFAULT '[]'::jsonb,
    ports               JSONB        NOT NULL DEFAULT '[]'::jsonb,
    backend             VARCHAR(40)  NOT NULL DEFAULT 'dry_run',
    backend_ref         TEXT,

    status              VARCHAR(16)  NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'released', 'failed')),

    -- Lease lifetime. The lease, not the approval row, is what expires:
    -- ttl_seconds is (re)set on each steer/renew, expires_at moves with it.
    ttl_seconds         INTEGER      NOT NULL DEFAULT 3600,
    started_at          TIMESTAMP,
    expires_at          TIMESTAMP,
    renewal_count       INTEGER      NOT NULL DEFAULT 0,

    -- Rollback record. Terminal rows always carry released_at (see the
    -- released check); release_reason says expiry, kill-switch or operator;
    -- rollback_result is the unsteer outcome in the executor-result shape.
    released_at         TIMESTAMP,
    release_reason      TEXT,
    rollback_result     JSONB,

    created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_deception_leases_status
        CHECK (status IN ('pending', 'active', 'released', 'failed')),
    CONSTRAINT ck_deception_leases_released
        CHECK ((status IN ('released', 'failed')) = (released_at IS NOT NULL))
);

-- The sweep's hot query: non-terminal leases by expiry.
CREATE INDEX IF NOT EXISTS idx_deception_leases_status_expires
    ON deception_leases (status, expires_at);

-- Per-attacker lookups: dedupe, console lease list, corroboration joins.
CREATE INDEX IF NOT EXISTS idx_deception_leases_attacker_ip
    ON deception_leases (attacker_ip);

CREATE TABLE IF NOT EXISTS deception_probes (
    probe_id            VARCHAR(60)  PRIMARY KEY,               -- deception-probe-<hex16>
    source_ip           VARCHAR(45)  NOT NULL,                  -- canonical attacker address

    -- Distinct per finding: a re-delivered finding is one observation, not
    -- two. Null only when a probe arrives without a finding to name.
    finding_id          VARCHAR(50),

    -- What the predicate saw: tids, category, destination_ips, ports.
    evidence            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Corroboration's hot query: a source's probes inside the window.
CREATE INDEX IF NOT EXISTS idx_deception_probes_source_created
    ON deception_probes (source_ip, created_at);

-- The prune's hot query: age out probes older than twice the window.
CREATE INDEX IF NOT EXISTS idx_deception_probes_created_at
    ON deception_probes (created_at DESC);

COMMENT ON TABLE deception_leases IS
    'Honey-routing lease registry: one attacker redirect per row; TTL lifecycle and rollback audit (feature 5).';
COMMENT ON COLUMN deception_leases.action_id IS
    'FK to approval_actions — the approval that authorized this lease.';
COMMENT ON COLUMN deception_leases.backend_ref IS
    'Controller-side handle for the programmed rule; the rollback target.';
COMMENT ON TABLE deception_probes IS
    'Recon probe log: per-source observations the honey-routing corroboration window counts over (feature 5).';

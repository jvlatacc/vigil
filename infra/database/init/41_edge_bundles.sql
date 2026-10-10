-- 41_edge_bundles.sql
-- Signed edge policy bundles, stored exactly as signed.
--
-- envelope is the DSSE envelope verbatim (what the daemon pulls and verifies
-- against its offline trust store); payload is the decoded bundle document,
-- kept so the control plane can serve cursor comparisons and scope matches
-- without re-verifying its own signature on every pull. Bundles never mutate
-- after signing: a change is a new row at a higher version, which is what
-- makes the daemon's monotonic-version check meaningful.
--
-- The spec's endpoint table pins no bundle store; this table is the
-- control-plane's own. Nothing here widens autonomy — tiers live inside the
-- signed payload, and the signing stack refuses tier3+ outright.
--
-- TIMESTAMP (not TIMESTAMPTZ) matches the naive-UTC DateTime columns the ORM
-- declares for this table (core/edge/models.py).

CREATE TABLE IF NOT EXISTS edge_bundles (
    bundle_id       VARCHAR(100) NOT NULL,
    version         INTEGER      NOT NULL,
    segment_scope   JSONB        NOT NULL,
    autonomy_tier   VARCHAR(16)  NOT NULL,
    envelope        JSONB        NOT NULL,
    payload         JSONB        NOT NULL,
    signed_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    signed_by       VARCHAR(100) NOT NULL,

    PRIMARY KEY (bundle_id, version)
);

CREATE INDEX IF NOT EXISTS idx_edge_bundles_scope_version
    ON edge_bundles (bundle_id, version DESC);

COMMENT ON TABLE edge_bundles IS
    'Signed edge policy bundles (DSSE), immutable per (bundle_id, version).';

-- down: DROP TABLE IF EXISTS edge_bundles;

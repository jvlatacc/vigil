-- Origin trust tiers on findings: who vouches for a row, decided by the
-- receiver that accepted it.
--
-- unverified < transport < signed. Every importer stamps the tier at ingest
-- (core/response/origin.py names them): bearer-keyed pushes, credentialed
-- pulls and the daemon's own pipeline stamp transport; an HMAC-verified
-- webhook stamps signed; a webhook with no configured secret is accepted but
-- stamps unverified — never trusted. The tier is set once, never read from
-- the payload, and never inferred afterwards.
--
-- What reads it is the response gate: unattended containment whose finding
-- sits below the configured floor (DAEMON_MIN_ORIGIN_TRUST_FOR_AUTO_CONTAINMENT)
-- waits for a person unless enough distinct data sources named the same
-- target inside the corroboration window — one indexed JSONB containment
-- query over entity_context, hence the GIN index below.
--
-- Backfill: rows that predate per-importer stamping predate the notion of a
-- tier, and unverified is what they are — fail-closed, so the gate holds
-- them rather than trusts them.

ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS origin_trust VARCHAR(16) NOT NULL
        DEFAULT 'unverified';

CREATE INDEX IF NOT EXISTS idx_finding_origin_trust
    ON findings (origin_trust);

CREATE INDEX IF NOT EXISTS idx_finding_entity_context_gin
    ON findings USING gin (entity_context);

COMMENT ON COLUMN findings.origin_trust IS
    'Who vouches for this row, set by the receiver that accepted it: unverified < transport < signed. Never read from the payload.';

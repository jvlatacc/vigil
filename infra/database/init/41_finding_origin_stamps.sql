-- Origin attestation stamps on findings (#944, Feature 7).
--
-- The daemon webhook verifies a DSSE/Ed25519 attestation header that covers
-- the finding content the sender signed. origin_verified is that verdict at
-- ingest: true only when the signature checked out against a registered
-- trusted origin (DAEMON_TRUSTED_ORIGINS), the attestation was fresh, no
-- nonce replayed, and the signed payload is the body that was stored.
-- origin_id is the origin that signed; null unless verified.
--
-- Every row that predates the column is unverified by definition, hence the
-- NOT NULL DEFAULT FALSE. The guard chain reads these stamps at decision
-- time and holds unverified evidence for a person instead of auto-containing.
--
-- A file of its own (41), not an edit to an earlier one: the Helm init job
-- records each file once it has run, so edits never reach a cluster that
-- already applied the original. scripts/migrate_schema.py covers a database
-- this file never reached.

ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS origin_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS origin_id VARCHAR(255);

COMMENT ON COLUMN findings.origin_verified IS
    'True only when the ingest webhook verified an origin attestation covering this finding (#944).';

COMMENT ON COLUMN findings.origin_id IS
    'The trusted origin that signed the attestation; null unless origin_verified.';

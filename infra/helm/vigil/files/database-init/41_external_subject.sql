-- The subject an external identity provider names for this person, when the
-- deployment accepts IdP-issued tokens on the MCP surface.
--
-- Set by an administrator through the users API — never provisioned from a
-- token claim, so mapping a remote identity to a Vigil account is a decision
-- somebody makes, with users.write and an audit trail behind it. A token whose
-- subject no user holds is refused (services/api/mcp_surface.py): identity
-- mapping is additive, not self-serve.
--
-- Unique and nullable: NULL is every user who signs in with a password only,
-- and Postgres's unique constraint ignores NULLs — any number of users may
-- have no external identity, and at most one may hold any given one.
-- VARCHAR(255) because a subject is an issuer-chosen identifier (a GUID, an
-- email, an opaque id), and every mainstream issuer's fits well inside it.

ALTER TABLE users ADD COLUMN IF NOT EXISTS external_subject VARCHAR(255) UNIQUE;

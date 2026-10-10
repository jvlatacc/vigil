-- Directory-group → role mappings for federated logins.
--
-- The upstream IdP (FreeIPA, via the OIDC broker) speaks in directory groups;
-- Vigil authorizes in roles. This table is the association between the two:
-- at login the signing-in user's groups are intersected with idp_group and
-- the highest-priority match assigns the role (core.auth.group_mapping).
-- There is deliberately no default: a user whose groups match nothing here
-- signs in with the role-unmapped role seeded below, whose permission map
-- grants nothing (deny-by-default).
--
-- Mapping rows are written only through the /api/role-group-mappings admin
-- router — users.write plus the same privilege-escalation guard as user role
-- assignment — never by hand: a row here grants its role's permissions to
-- every directory member at their next login.

CREATE TABLE IF NOT EXISTS role_group_mappings (
    id BIGSERIAL PRIMARY KEY,
    role_id VARCHAR(50) NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    idp_group TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (idp_group, role_id)
);

CREATE INDEX IF NOT EXISTS idx_role_group_mappings_group ON role_group_mappings(idp_group);

-- The unmapped role: what an authenticated IdP user whose directory groups
-- match no mapping signs in with. The permission map is deliberately empty —
-- every check reads permissions.get(key, false), so an empty map denies
-- everything without enumerating keys that would drift as the vocabulary
-- grows. It is a system role so it cannot be deleted or repurposed.
INSERT INTO roles (role_id, name, description, permissions, is_system_role) VALUES
('role-unmapped', 'Unmapped', 'Authenticated via the IdP but no directory group maps to a Vigil role; grants nothing until an administrator maps one of the holder''s groups', '{}', true)
ON CONFLICT (role_id) DO NOTHING;

-- Additive vocabulary for deployments created before tools.execute existed
-- (fresh installs already carry the key in the 06 seeds). Only the seeded
-- system roles are touched: roles that may drive the agent — every one
-- holding ai_chat.use — keep doing what they could before the tool-call
-- gates existed; a role whose map lacks the key denies tool calls, and
-- custom roles stay denied until an operator grants the baseline or writes
-- a per-server `tools.server.<name>` override.
UPDATE roles SET permissions = permissions || '{"tools.execute": true}'::jsonb
WHERE role_id IN ('role-analyst', 'role-senior-analyst', 'role-manager', 'role-admin')
  AND NOT permissions ? 'tools.execute';

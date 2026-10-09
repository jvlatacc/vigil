-- An additional role a user holds, beside their primary `users.role_id`.
--
-- `users.role_id` stays the primary role: exactly one per user, written by
-- bootstrap and edited by the users API. This table adds grants on top of it.
-- Authorization reads the union of the primary role and every row here
-- (core/auth/auth_service.py), so a user's reach is every role they hold,
-- never just the newest one.
--
-- It is a table of its own rather than a repeated column because a user holds
-- a variable number of roles, and because each grant records who made it: a
-- permission change with no author is not auditable. The composite primary
-- key leads with user_id, so the per-user lookup every permission check makes
-- is the PK index; grants are unique, so re-granting an already-held role
-- changes nothing.

CREATE TABLE IF NOT EXISTS role_assignments (
    -- Deleting the person deletes their grants: an assignment cannot outlive
    -- the user it authorizes.
    user_id VARCHAR(50) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- No cascade and no ON DELETE for roles: a role deletion is a deliberate
    -- act on the roles surface, and the FK names any assignment still
    -- referencing the role rather than silently revoking it.
    role_id VARCHAR(50) NOT NULL REFERENCES roles(role_id),

    -- The username that made the grant, or "bootstrap" for the first admin.
    granted_by VARCHAR(50) NOT NULL,

    granted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_id, role_id)
);

-- Who holds a given role, for listings and for role-deletion checks. The
-- user side is covered by the primary key.
CREATE INDEX IF NOT EXISTS idx_role_assignments_role
    ON role_assignments (role_id);

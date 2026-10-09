-- Never-quarantine invariants: containment targets unattended response may
-- never touch, whatever the confidence.
--
-- One row per entry: an exact address, a CIDR range, a hostname glob, or an
-- infrastructure role. What reads it is the approval gate, the 30-second
-- approved-action executor and the responder's target validation — any of
-- them holds containment naming a row here for a person, and none creates
-- such a row on its own.
--
-- Two origins. 'env' rows mirror entries of DAEMON_NEVER_QUARANTINE, the
-- immutable floor: the floor itself is read from the environment at each
-- decision and can be undercut by nothing in this table or the Settings UI,
-- so removing an 'env' row is refused the same way (the environment wins).
-- 'operator' rows are added through Settings; they may tighten the floor and
-- never loosen it. The daemon writes nothing here: it can only demote its
-- own autonomy, and only humans promote it.
--
-- Removal is recorded, not deleted, like ip_exclusions: "this target was
-- protected from 09:10 to 14:02, by whom and why" is what explains a
-- containment that was allowed afterwards. At most one active row per
-- (kind, value); protecting a target again after removal is a new row with
-- its own reason.

CREATE TABLE IF NOT EXISTS protected_targets (
    target_id VARCHAR(50) PRIMARY KEY,

    -- What kind of thing value names. An ip is one address, a cidr a range,
    -- a hostname_glob a shell-style pattern, a role an infrastructure role
    -- a target may name verbatim ("domain_controller", "dns_server").
    kind VARCHAR(20) NOT NULL,

    -- Canonical form (Python's ipaddress for ip/cidr; lower-case for
    -- hostname_glob and role), so it compares equal to the same target
    -- written differently.
    value VARCHAR(255) NOT NULL,

    -- Why it may never be contained unattended. Required: an invariant
    -- nobody can explain is one nobody dares remove.
    reason TEXT NOT NULL,

    -- Where the entry was made: the environment floor or the Settings UI.
    origin VARCHAR(20) NOT NULL DEFAULT 'operator',

    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    removed_at TIMESTAMP,
    removed_by VARCHAR(100),
    removal_reason TEXT,

    CONSTRAINT ck_protected_targets_kind
        CHECK (kind IN ('ip', 'cidr', 'hostname_glob', 'role')),
    CONSTRAINT ck_protected_targets_origin
        CHECK (origin IN ('env', 'operator')),
    CONSTRAINT ck_protected_targets_removal
        CHECK ((removed_at IS NULL) = (removed_by IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_protected_targets_active
    ON protected_targets (kind, value) WHERE removed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_protected_targets_created_at
    ON protected_targets (created_at DESC);

COMMENT ON TABLE protected_targets IS
    'Never-quarantine invariants: containment targets unattended response may never touch. The DAEMON_NEVER_QUARANTINE environment floor cannot be removed here.';

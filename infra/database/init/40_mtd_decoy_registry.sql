-- Moving-target-defense tables: the decoy registry honey-routing may target,
-- and the addresses it must never route.
--
-- Part of the MTD feature's persistence slice: the decision plane (a later PR)
-- reads these tables; nothing else in the backend consumes them yet.
--
-- A registry row is a routing target, not a running thing. The decoy
-- workloads themselves live in the deployment (the compose `decoys` profile,
-- the Helm Deployment behind a default-deny NetworkPolicy); this table is what
-- the decision plane may pick from and what an operator cross-references
-- against the stack. Retirement is recorded, not deleted -- "what did we route
-- into last month" stays answerable -- and the unique index is partial on
-- active rows, so a new decoy may reuse a retired name.
--
-- canary_credential_ref is a pointer into the credential store (core.secrets /
-- integration config), never the credential: decoys hold canary values only,
-- and the registry must not become the leak path for them.
--
-- mtd_ip_exclusions is the mirror image of ip_exclusions (35): that table
-- hides an address from the findings queue, this one hides an address from the
-- decoys. Production hosts an analyst names here fall back to the normal
-- response path. Removal is recorded, not deleted -- a status transition,
-- active to removed, with who and when -- so "was this address ever protected
-- from routing" survives the removal. One address per row, no ranges; at most
-- one active row per address, and listing it again after removal is a new row
-- with its own reason.

CREATE TABLE IF NOT EXISTS mtd_decoy_registry (
    decoy_id VARCHAR(50) PRIMARY KEY,

    -- The name the deployment knows the decoy by (compose service, Helm
    -- Deployment).
    name VARCHAR(100) NOT NULL,

    -- What the decoy pretends to be; the decision plane picks by kind.
    kind VARCHAR(10) NOT NULL,

    -- Where the decoy is reached: host/port of the service behind it.
    endpoint VARCHAR(200) NOT NULL,

    -- active (routable) or retired (taken out of rotation, row kept).
    status VARCHAR(16) NOT NULL DEFAULT 'active',

    -- Pointer into the credential store, never the credential itself.
    canary_credential_ref VARCHAR(200) NOT NULL,

    -- Last canary rotation. NULL until the first rotation runs.
    rotated_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_mtd_decoy_registry_kind
        CHECK (kind IN ('ssh', 'http')),
    CONSTRAINT ck_mtd_decoy_registry_status
        CHECK (status IN ('active', 'retired'))
);

-- At most one active decoy per name; a retired row does not block the name.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_mtd_decoy_registry_active_name
    ON mtd_decoy_registry (name) WHERE status = 'active';

-- Decoy selection reads "an active decoy of this kind".
CREATE INDEX IF NOT EXISTS idx_mtd_decoy_registry_kind_status
    ON mtd_decoy_registry (kind, status);

CREATE TABLE IF NOT EXISTS mtd_ip_exclusions (
    exclusion_id VARCHAR(50) PRIMARY KEY,

    -- Canonical text form (Python's ipaddress: lower-case, compressed IPv6),
    -- so it compares equal to the address the decision plane reads out of
    -- entity_context.
    ip VARCHAR(45) NOT NULL,

    -- Why it must not be routed. Required: a never-route entry nobody can
    -- explain is one nobody dares remove.
    reason TEXT NOT NULL,

    added_by VARCHAR(100) NOT NULL,
    added_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- active (never route) or removed (the recorded removal of the entry).
    status VARCHAR(16) NOT NULL DEFAULT 'active',

    -- Set together with the status transition to 'removed'; the check below
    -- keeps the two from disagreeing.
    removed_at TIMESTAMP,
    removed_by VARCHAR(100),

    CONSTRAINT ck_mtd_ip_exclusions_status
        CHECK (status IN ('active', 'removed')),
    CONSTRAINT ck_mtd_ip_exclusions_status_removal
        CHECK ((status = 'active') = (removed_at IS NULL))
);

-- At most one active never-route row per address.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_mtd_ip_exclusions_active_ip
    ON mtd_ip_exclusions (ip) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_mtd_ip_exclusions_added_at
    ON mtd_ip_exclusions (added_at DESC);

COMMENT ON TABLE mtd_decoy_registry IS
    'Decoy services honey-routing may sinkhole attacker flows into: routing targets only, the workloads live in the deployment. Canary credentials live behind canary_credential_ref, never in this table.';
COMMENT ON TABLE mtd_ip_exclusions IS
    'Addresses the MTD decision plane must never honey-route; they fall back to the normal response path. Removal is a recorded status transition, never a delete.';

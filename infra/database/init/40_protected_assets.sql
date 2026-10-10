-- Assets a containment action must never be auto-executed against (#944).
--
-- Feature 7's never-quarantine invariant: an operator-declared list of DNS
-- servers, domain controllers, gateways and the like that the Responder may
-- not contain on its own, at any confidence or severity. The gate reads this
-- table through a memory-resident index (``core.response.protected_assets``);
-- a hit converts the action to a pending human approval carrying the
-- invariant's rationale. A person may still approve that pending action — the
-- deliberate emergency valve for a domain controller that genuinely is
-- compromised — and the action row records the override.
--
-- This is execution safety, deliberately separate from ``ip_exclusions``:
-- an exclusion hides *findings* from the queue, this table constrains what
-- *actions* may run. Neither reads the other.
--
-- A match is an IP (exact), a CIDR range (longest prefix wins on overlap), or
-- a hostname (case-insensitive exact). Stored canonical: Python's ``ipaddress``
-- text for addresses and networks, lower-case for hostnames, so the row
-- compares equal to the value the index matches with.
--
-- Removal is recorded, not deleted — "this asset was protected from 09:10 to
-- 14:02, by whom and why" is what an audit of an override reads afterwards. At
-- most one active row per (match kind, value); declaring it again after
-- removal is a new row with its own reason.

CREATE TABLE IF NOT EXISTS protected_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- How the asset is named: one exact address, one network range, or one
    -- hostname. No wildcards in v1: an over-broad match protects more than
    -- the operator looked at.
    match_kind VARCHAR(20) NOT NULL,

    -- Canonical form of the address, network, or hostname.
    match_value TEXT NOT NULL,

    -- What kind of thing it is, so an approval queue shows "prod DNS" and not
    -- an opaque address.
    asset_class VARCHAR(30) NOT NULL,

    -- Human-readable name, required: an invariant nobody can explain is one
    -- nobody dares remove.
    label TEXT NOT NULL,

    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    removed_at TIMESTAMP,
    removed_by VARCHAR(100),
    removal_reason TEXT,

    CONSTRAINT ck_protected_assets_match_kind
        CHECK (match_kind IN ('ip', 'cidr', 'hostname')),
    CONSTRAINT ck_protected_assets_asset_class
        CHECK (asset_class IN
            ('dns', 'domain_controller', 'gateway', 'dhcp', 'database', 'other')),
    CONSTRAINT ck_protected_assets_removal
        CHECK ((removed_at IS NULL) = (removed_by IS NULL))
);

-- At most one active row per (kind, value); hostnames compare case-insensitively.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_protected_assets_active
    ON protected_assets (match_kind, lower(match_value)) WHERE removed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_protected_assets_created_at
    ON protected_assets (created_at DESC);

COMMENT ON TABLE protected_assets IS
    'Never-quarantine invariants (#944): targets the Responder may not auto-contain. Execution safety; unrelated to ip_exclusions (finding visibility).';

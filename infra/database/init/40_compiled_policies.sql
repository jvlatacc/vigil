-- Compiled triage policies and the decisions they make (docs/adr/0001).
--
-- A workflow that resolves one threat archetype consistently is compiled, once,
-- into a versioned deterministic policy over pre-LLM finding fields, so a
-- mature archetype stops paying model time on its hundredth identical alert.
-- This file holds both ends of that: the policy (what was trusted) and the
-- per-finding decision record (what it decided, and whether it agreed with the
-- eventual LLM or analyst result).
--
-- compiled_policies: one row per policy version. The IR column is the whole
-- versioned condition tree -- the same bytes the daemon's evaluator reads and
-- the single source every export renderer (Rego, Snort, Suricata, iptables)
-- projects. content_hash pins the IR; every decision row names the hash it ran
-- under, so what was trusted is reconstructable per finding. Lifecycle is
-- human-gated forward and automatic backward (candidate -> shadow -> active,
-- drift auto-brake to suspended, re-arm through shadow, terminal retired); the
-- CHECKs pair each backward-or-forward transition with its actor and timestamp,
-- so an active row without a promotion record is a bug, not a fact.
--
-- compiled_policy_decisions: one row per evaluation, hit or miss, in both
-- modes. The shadow window's agreement evidence and the drift counters both
-- read here, which is why a miss (no policy matched) is also a row: the scan
-- happened and cost something. Agreement columns are written back when the
-- eventual result exists; until then the policy's own decision stands alone.
--
-- Findings cascade (the repo's other decision log, ai_decision_logs, does the
-- same): a decision exists for the finding it triaged. Policies are never
-- deleted while their decisions exist -- retired rows are kept for audit -- so
-- the composite FK restricts rather than cascades.

CREATE TABLE IF NOT EXISTS compiled_policies (
    policy_id VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL,

    state VARCHAR(20) NOT NULL DEFAULT 'candidate',

    -- The policy IR: the self-describing condition tree, content-hashed, that
    -- the evaluator runs and every renderer projects.
    policy_ir JSONB NOT NULL,

    -- "sha256:<hex>" over the canonical IR serialization.
    content_hash VARCHAR(80) NOT NULL,

    -- The evidence the compile ran on: window, per-outcome counts,
    -- consistency, analyst overrides. Kept beside the IR because a policy is
    -- only as believable as the record that produced it.
    maturity_evidence JSONB NOT NULL,

    compiled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    compiled_by VARCHAR(100) NOT NULL DEFAULT 'system',

    promoted_by VARCHAR(100),
    promoted_at TIMESTAMPTZ,
    suspended_by VARCHAR(100),
    suspended_at TIMESTAMPTZ,
    rearmed_by VARCHAR(100),
    rearmed_at TIMESTAMPTZ,
    retired_by VARCHAR(100),
    retired_at TIMESTAMPTZ,

    PRIMARY KEY (policy_id, version),

    CONSTRAINT ck_compiled_policies_state
        CHECK (state IN ('candidate', 'shadow', 'active', 'suspended', 'retired')),
    CONSTRAINT ck_compiled_policies_version_positive CHECK (version >= 1),
    CONSTRAINT ck_compiled_policies_promoted
        CHECK ((promoted_at IS NULL) = (promoted_by IS NULL)),
    CONSTRAINT ck_compiled_policies_suspended
        CHECK ((suspended_at IS NULL) = (suspended_by IS NULL)),
    CONSTRAINT ck_compiled_policies_rearmed
        CHECK ((rearmed_at IS NULL) = (rearmed_by IS NULL)),
    CONSTRAINT ck_compiled_policies_retired
        CHECK ((retired_at IS NULL) = (retired_by IS NULL)),
    -- The state names the record that got it there.
    CONSTRAINT ck_compiled_policies_active_has_promotion
        CHECK (state <> 'active' OR promoted_at IS NOT NULL),
    CONSTRAINT ck_compiled_policies_suspended_has_record
        CHECK (state <> 'suspended' OR suspended_at IS NOT NULL),
    CONSTRAINT ck_compiled_policies_retired_has_record
        CHECK (state <> 'retired' OR retired_at IS NOT NULL)
);

-- The fast path loads the shadow + active set per evaluation; the console
-- filters by state; both are satisfied by one small index.
CREATE INDEX IF NOT EXISTS idx_compiled_policies_state
    ON compiled_policies (state);

CREATE TABLE IF NOT EXISTS compiled_policy_decisions (
    id BIGSERIAL PRIMARY KEY,
    finding_id VARCHAR(50) NOT NULL,

    -- The policy that produced the decision, when one matched. A no-match row
    -- leaves these NULL and says so in outcome.
    policy_id VARCHAR(50),
    policy_version INTEGER,
    content_hash VARCHAR(80),
    mode VARCHAR(10),

    -- applied: active hit, triage keys written. shadow_logged: evaluated,
    -- nothing written. no_match: scanned, nothing matched.
    outcome VARCHAR(20) NOT NULL,

    -- The policy's own decision (severity, confidence, recommended_action,
    -- category, reasoning); NULL when nothing matched.
    decision JSONB,

    -- The eventual result measured against, written back when it exists: the
    -- LLM's triage of the same finding, or the analyst's word. Which one is
    -- agreement_source.
    actual_decision JSONB,
    agreement_source VARCHAR(20),
    agrees BOOLEAN,

    evaluation_us INTEGER NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_compiled_policy_decisions_finding
        FOREIGN KEY (finding_id) REFERENCES findings (finding_id) ON DELETE CASCADE,
    CONSTRAINT fk_compiled_policy_decisions_policy
        FOREIGN KEY (policy_id, policy_version)
        REFERENCES compiled_policies (policy_id, version) ON DELETE RESTRICT,

    CONSTRAINT ck_compiled_policy_decisions_mode
        CHECK (mode IN ('shadow', 'active')),
    CONSTRAINT ck_compiled_policy_decisions_outcome
        CHECK (outcome IN ('applied', 'shadow_logged', 'no_match')),
    CONSTRAINT ck_compiled_policy_decisions_no_match
        CHECK ((outcome = 'no_match') = (policy_id IS NULL)),
    CONSTRAINT ck_compiled_policy_decisions_mode_outcome
        CHECK ((outcome = 'applied') IS NOT DISTINCT FROM (mode = 'active')),
    CONSTRAINT ck_compiled_policy_decisions_agreement_source
        CHECK (agreement_source IN ('llm', 'analyst')),
    CONSTRAINT ck_compiled_policy_decisions_agreement_pairing
        CHECK (
            (agrees IS NULL) = (actual_decision IS NULL)
            AND (agreement_source IS NULL) = (actual_decision IS NULL)
        ),
    CONSTRAINT ck_compiled_policy_decisions_evaluation_us_nonnegative
        CHECK (evaluation_us >= 0)
);

-- The drift counters read a policy's recent window; the audit reads a finding.
CREATE INDEX IF NOT EXISTS idx_compiled_policy_decisions_policy
    ON compiled_policy_decisions (policy_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_compiled_policy_decisions_finding
    ON compiled_policy_decisions (finding_id, evaluated_at DESC);

COMMENT ON TABLE compiled_policies IS
    'Versioned deterministic triage policies compiled from workflow maturity evidence; lifecycle candidate/shadow/active/suspended/retired with actor+timestamp per transition. See docs/adr/0001.';
COMMENT ON TABLE compiled_policy_decisions IS
    'One row per fast-path evaluation, hit or miss, shadow or active, with the policy version+content_hash trusted, the decision, agreement with the eventual LLM/analyst result, and the evaluation cost in microseconds.';

-- Speculative containment lifecycle on approval_actions.
--
-- A speculative action is a live, time-boxed restriction the fast path
-- applies without a person or a model call in the loop, that the slow
-- path (an adjudicate run), a human, or the TTL sweep later resolves.
-- Three things make the ledger carry that:
--
-- expires_at bounds the restriction, and the sweep's partial index
-- reads only the rows still live. The status CHECK learns speculative
-- / rolled_back / escalated. The idempotency unique index — unique
-- among non-failed rows (#827) — stops treating a rolled-back row as
-- the live one for its key, so the same target can be restricted again
-- after a rollback instead of deduping into the dead row.
--
-- Idempotent via IF NOT EXISTS / IF EXISTS drops; safe to re-run.

ALTER TABLE approval_actions
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- The status column was born with a five-value CHECK (13_approval_actions.sql);
-- the speculative lifecycle adds three values, two of them terminal.
ALTER TABLE approval_actions
    DROP CONSTRAINT IF EXISTS approval_actions_status_check;
ALTER TABLE approval_actions
    ADD CONSTRAINT approval_actions_status_check
        CHECK (status IN ('pending', 'approved', 'rejected', 'executed', 'failed',
                          'speculative', 'rolled_back', 'escalated'));

-- The TTL sweep's working set: every live speculative row and the moment it
-- stops being live. Rows the sweep can no longer act on stay out of the index.
CREATE INDEX IF NOT EXISTS idx_approval_actions_speculative_expires
    ON approval_actions (expires_at)
    WHERE status = 'speculative' AND expires_at IS NOT NULL;

-- Same key, wider exclusion: a rolled-back row is no longer the live one,
-- so re-containment of the same target fires fresh instead of deduping
-- into the dead row. Recreated rather than IF NOT EXISTS — the definition
-- changed, and IF NOT EXISTS would silently keep the old one.
DROP INDEX IF EXISTS uq_approval_actions_idempotency_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_actions_idempotency_key
    ON approval_actions (idempotency_key)
    WHERE idempotency_key IS NOT NULL
      AND status NOT IN ('failed', 'rolled_back');

COMMENT ON COLUMN approval_actions.expires_at IS
    'When a speculative restriction stops being live; the TTL sweep releases the row past it. Null for ordinary approvals.';

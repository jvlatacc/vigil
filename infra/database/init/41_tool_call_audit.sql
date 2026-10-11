-- Per-call audit for tool execution. Every tool call Vigil allows or denies
-- lands exactly one row here: who ran it, on what server and tool, the
-- arguments by digest, how it was decided, and what came of it. Allowed and
-- denied are both first-class -- a call that leaves no row is the one an
-- investigation cannot see.
--
-- The rows are append-only: vigil_app holds SELECT and INSERT, the same
-- treatment 30_vigil_app_role.sql gives agent_events. The event_hash chain
-- makes silent edits detectable: each row hashes the previous row's hash
-- together with its own content, so mutating any row breaks every row after
-- it. 31_agent_ledger_hash_chain.sql is the pattern; the difference is that
-- this chain is one global sequence ordered by id (tool calls are not
-- partitioned by a run), so the trigger takes a transaction advisory lock to
-- keep concurrent inserts from reading the same tail and forking the chain.

CREATE TABLE IF NOT EXISTS tool_call_audit (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_username TEXT NOT NULL,
    idp_subject TEXT,
    surface TEXT NOT NULL,
    server_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_sha256 CHAR(64),
    args_bytes INTEGER,
    decision TEXT NOT NULL,
    deny_reason TEXT,
    outcome TEXT,
    duration_ms INTEGER,
    trace_id TEXT,
    run_id TEXT,
    prev_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_call_audit_ts ON tool_call_audit(ts);
CREATE INDEX IF NOT EXISTS idx_tool_call_audit_actor ON tool_call_audit(actor_username);
CREATE INDEX IF NOT EXISTS idx_tool_call_audit_server_tool ON tool_call_audit(server_name, tool_name);

COMMENT ON TABLE tool_call_audit IS
    'One row per tool call, allowed or denied: actor, surface, server, tool, args digest, decision, outcome.';
COMMENT ON COLUMN tool_call_audit.actor_username IS
    'The verified local user the call ran as, or "agent" when no person was bound.';
COMMENT ON COLUMN tool_call_audit.idp_subject IS
    'The upstream IdP subject (`sub`) of a federated session; NULL while no federation is configured.';
COMMENT ON COLUMN tool_call_audit.surface IS
    'Where the call entered: agent (/internal/tools/invoke), mcp-inbound (/mcp), mcp-client (outbound vendor dispatch), in-process (Vigil''s own tools), or vstrike (outbound VStrike calls).';
COMMENT ON COLUMN tool_call_audit.decision IS 'allow or deny; a deny is a first-class outcome, not an error path.';
COMMENT ON COLUMN tool_call_audit.deny_reason IS 'Why the call was denied: "permission" at the RBAC gates.';
COMMENT ON COLUMN tool_call_audit.outcome IS 'For allowed calls: ok, or error when the tool could not answer.';
COMMENT ON COLUMN tool_call_audit.prev_hash IS
    'event_hash of the previous row by id, or empty at the first row.';
COMMENT ON COLUMN tool_call_audit.event_hash IS
    'sha256(prev_hash || canonical(row)), assigned on INSERT and never by the caller.';

-- The one row spelling the trigger, the Python writer and the Python verifier
-- (core/audit/tool_calls.py) must agree on. Fields in a fixed order, joined
-- with the ASCII unit separator -- a byte no audit field can carry, since
-- names and digests cannot contain control characters -- so no two different
-- rows render as the same text. Timestamps are deliberately excluded: the
-- ledger does the same, because a timezone-aware timestamp has no one
-- spelling across engines, and the chain links rows by id regardless.
CREATE OR REPLACE FUNCTION tool_call_audit_canonical(
    actor_username text, idp_subject text, surface text, server_name text,
    tool_name text, args_sha256 text, args_bytes integer, decision text,
    deny_reason text, outcome text, duration_ms integer, trace_id text,
    run_id text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = public
AS $$
  SELECT concat_ws(chr(31),
    coalesce(actor_username, ''),
    coalesce(idp_subject, ''),
    coalesce(surface, ''),
    coalesce(server_name, ''),
    coalesce(tool_name, ''),
    coalesce(args_sha256, ''),
    coalesce(args_bytes::text, ''),
    coalesce(decision, ''),
    coalesce(deny_reason, ''),
    coalesce(outcome, ''),
    coalesce(duration_ms::text, ''),
    coalesce(trace_id, ''),
    coalesce(run_id, '')
  );
$$;

CREATE OR REPLACE FUNCTION tool_call_audit_assign_hashes()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  prev text;
BEGIN
  -- One writer at a time: two inserts that read the same tail would both
  -- claim the same prev_hash and fork the chain. Transaction-scoped, so it
  -- releases at commit.
  PERFORM pg_advisory_xact_lock(hashtext('tool_call_audit'));
  SELECT event_hash INTO prev FROM tool_call_audit ORDER BY id DESC LIMIT 1;
  NEW.prev_hash := coalesce(prev, '');
  NEW.event_hash := encode(
    sha256(convert_to(
      NEW.prev_hash || tool_call_audit_canonical(
        NEW.actor_username, NEW.idp_subject, NEW.surface, NEW.server_name,
        NEW.tool_name, NEW.args_sha256, NEW.args_bytes, NEW.decision,
        NEW.deny_reason, NEW.outcome, NEW.duration_ms, NEW.trace_id,
        NEW.run_id
      ),
      'UTF8'
    )),
    'hex'
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tool_call_audit_assign_hashes ON tool_call_audit;
CREATE TRIGGER tool_call_audit_assign_hashes
  BEFORE INSERT ON tool_call_audit
  FOR EACH ROW
  EXECUTE FUNCTION tool_call_audit_assign_hashes();

-- Append-only at the runtime role: SELECT to read, INSERT to write, and no
-- way to rewrite or drop a row once it is in.
GRANT SELECT, INSERT ON TABLE tool_call_audit TO vigil_app;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE tool_call_audit FROM vigil_app;
GRANT USAGE ON SEQUENCE tool_call_audit_id_seq TO vigil_app;

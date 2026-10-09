# Tool-call audit — retention and SIEM export

`tool_call_audit` is the accountability record: one row per MCP tool call —
allowed **and** denied — naming actor, IdP subject, surface, server, tool,
arguments digest, decision, outcome, and the OTEL trace it sat inside
(`core/audit/tool_calls.py`; DDL and the hash-chain trigger in
`infra/database/init/41_tool_call_audit.sql`). This page is the operational
half: how long to keep it, how to ship it to a SIEM, and the one constraint
that shapes both.

## The constraint: the chain anchors at the first row

Every row's `event_hash` binds its content to the previous row's hash, and
the verifier `verify_chain()` starts from the first row by `id` with an empty
`prev_hash`. Two consequences, both load-bearing for retention:

- **Deleting a prefix of rows breaks live verification.** The first row that
  remains carries a `prev_hash` pointing at a deleted row, so
  `verify_chain()` reports `broken_at` there — even though nothing was
  tampered with. In-place pruning of old rows is therefore not a retention
  strategy for this table; rotation is (below).
- **A verifier can also be run on an export.** The hash formula is
  deterministic (`core.audit.tool_calls.row_event_hash` over
  `canonical_row`, field order fixed); a SIEM-side job can recompute it and
  detect truncation or edits in the shipped copy too.

Also know what a row does **not** hold: tool arguments are a sha256 digest
plus byte length, never the arguments themselves — an audit trail records
that a call happened, not a second copy of what was fed to it. Retention
policies written for finding or case data do not apply here; there is
nothing sensitive in the row to expire.

## Retention — the stated default

**Default: keep the live ledger whole; the SIEM, not deletion, is the
retention window.**

| Store | Default retention | Rationale |
|---|---|---|
| `tool_call_audit` (Postgres) | Keep all rows while under ~10 M rows; rotate when above | Rows are small (~a few hundred bytes + indexes); the full chain verifies in place, which is the table's whole point |
| SIEM / archive | 365 days hot, then cold storage, per your compliance policy | The queryable long-term copy; retention window is a policy decision, stated here as the default, not hidden in behavior |

At the scale where rotation is warranted (roughly >10 M rows, or a few GB of
table + indexes), use **epoch rotation** — archive-verify-delete — which
keeps every epoch's chain internally verifiable:

1. `verify_chain()` → green (`ok: true`), and record `count` + the tail
   `event_hash` (the epoch's closing seal).
2. Export every row (see export section) and confirm the SIEM copy: same
   count, spot-check a few hashes.
3. `TRUNCATE tool_call_audit` — as the database owner (e.g. `deeptempo`),
   **not** `vigil_app`, whose grants are SELECT + INSERT only, on purpose.
   The BEFORE-INSERT trigger survives; the next write starts a new epoch
   from `prev_hash = ''`.
4. Store the closing seal (`event_hash` + count) with the archive. Cross-
   epoch continuity lives in the SIEM copy and the seal, not in the live
   table.

What rotation costs: `verify_chain()` verifies only the current epoch. That
is the trade — a live table that always verifies whole, against an anchor
that resets each epoch. An operator who needs continuous multi-year
verification keeps more epochs' rows in the live table instead.

## SIEM export

Vigil writes the row and commits it before the call proceeds (a write
failure fails the call, closed) — there is no batching layer to drain. The
export hook is a **checkpointed tail read**, the same read the writer uses
to find the chain's tail:

```sql
SELECT id, ts, actor_username, idp_subject, surface, server_name, tool_name,
       args_sha256, args_bytes, decision, deny_reason, outcome, duration_ms,
       trace_id, run_id, prev_hash, event_hash
FROM tool_call_audit
WHERE id > :cursor
ORDER BY id
LIMIT :batch;
```

- **Cursor = max `id` shipped**, stored durably next to the exporter (a
  tiny state file or table). At-least-once delivery: downstream consumers
  dedupe on `id`.
- **Ordering is total** (`id` is the chain's link order) — ship in `id`
  order and the SIEM copy can be chain-verified too.
- **Run it where a read-only DB credential is enough.** A dedicated reader
  with SELECT on this table is the least privilege that works;
  `vigil_app` already has the SELECT, but reuse it only if the exporter is
  otherwise inert.

The repo already ships a Splunk helper — `scripts/export_to_splunk.sh` +
`scripts/export_postgres_to_splunk.py` (HEC url/token/index via env or
flags) — but its selection surface today is the findings and cases tables
(`--findings-only` / `--cases-only`); it does not read `tool_call_audit`.
For the audit ledger, the export hook is the checkpointed tail read above;
a minimal Splunk HEC shipper is a loop over it:

```python
# scheduled (cron / K8s CronJob) against the Postgres the backend uses
rows = db.execute(SQL, {"cursor": cursor, "batch": 500}).mappings().all()
if rows:
    payload = [{"event": dict(r), "time": r["ts"].timestamp()} for r in rows]
    requests.post(HEC_URL, headers={"Authorization": f"Splunk {HEC_TOKEN}"},
                  json=payload, timeout=30).raise_for_status()
    cursor = rows[-1]["id"]          # advance only after a 2xx
    save_cursor(cursor)
```

Elastic: same loop, `_bulk` index with `_id: <id>` so replays dedupe.
Kafka (the compose file ships a `kafka` profile): same loop, one message per
row keyed by `id` on a `vigil.tool-call-audit` topic.

### Correlation fields worth indexing at the destination

| Field | Joins to |
|---|---|
| `trace_id` | the OTEL trace — Jaeger via the compose `observability` profile |
| `run_id` | the agent run that drove the call |
| `actor_username`, `idp_subject` | the person — `idp_subject` present once the session is federated (the `sub` claim) |
| `surface` | `agent` / `mcp-inbound` (enforcement: deny rows live here), `mcp-client` / `in-process` / `vstrike` (execution) |

## Querying the live table

There is no admin API over the audit table yet — read it in SQL, as the
database owner or another read-capable role:

```sql
-- who ran tool X on server Y, and when
SELECT ts, actor_username, idp_subject, decision, outcome, trace_id
FROM tool_call_audit
WHERE server_name = 'crowdstrike' AND tool_name = 'investigate'
ORDER BY ts DESC;

-- every denial in the last day, with reasons
SELECT ts, actor_username, server_name, tool_name, deny_reason
FROM tool_call_audit
WHERE decision = 'deny' AND ts > now() - interval '1 day'
ORDER BY ts;

-- is the chain still intact?
--   python: from core.audit.tool_calls import verify_chain; print(verify_chain())
```

The test suite keeps the writer and verifier honest
(`tests/unit/audit/test_tool_call_audit.py`,
`tests/integration/test_tool_call_audit.py`); if your exporter asserts
hash-chain continuity on ingest, it will catch truncation or in-place edits
of the shipped copy as well.

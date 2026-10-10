# Edge mesh: Warden and the Local Autonomy Mesh

Vigil's containment pipeline — triage, decision, record, execute — runs centrally. Cut the path to the control plane and a segment under attack has no defense at all: denial-of-service on the WAN, congestion, or a control-plane outage all strike at the moment defense matters most.

The **Local Autonomy Mesh** closes that gap. **Warden** — a lightweight runtime deployed on cluster nodes and VPC gateways — pulls a signed containment-policy pack while connected, triages local alerts on-device, enforces only what the pack's signed autonomy envelope allows while the control plane is unreachable, and reconciles a tamper-evident decision journal on reconnect. The safety stance is the same one the rest of Vigil takes: **fail closed**. A Warden that cannot verify its authority enforces nothing; every refusal is recorded; and no configuration surface at the edge can widen what the signed pack allows.

This guide covers deployment, enrollment, the signed policy pack, the autonomy envelope, enforcement semantics, and reconciliation. Everything here is verified against the code at `services/warden/` (the runtime), `core/edge/` (the shared policy and decision domain), `services/api/routers/edge.py` (the control-plane API), and `services/api/edge_cli.py` (enrollment-token minting).

## What runs where

| Piece | Where | What it is |
|---|---|---|
| **Warden** (`services/warden/`) | each defended node or gateway | The edge runtime: policy sync, local alert intake, decision engine, executors, hash-chained journal, reconciler. |
| **Edge domain** (`core/edge/`) | shared library | The policy schema, DSSE signing + offline verification, autonomy-envelope runtime, decision ladder, protected-target guard, executors, and journal chain — one implementation used by both sides. |
| **Edge API** (`services/api/routers/edge.py`) | control plane | `/api/v1/edge/*`: enrollment, node list/revoke, signed-policy fetch, journal reconcile. |
| **Enrollment CLI** (`services/api/edge_cli.py`) | control plane | Mints one-time enrollment tokens: `python -m services.api.edge_cli`. |
| **Edge schema** (`infra/database/init/40…42_*.sql`) | control plane | `edge_nodes`, `edge_policies`, `edge_journal_receipts` — created by the standard schema init. |
| **Packaging** | infra | `infra/docker/Dockerfile.warden`, the compose `edge` profile, and the Helm `warden` DaemonSet with its own NetworkPolicy. |

Warden is a standalone asyncio process with **no database and no Redis**: its entire state is the verified policy pack and a hash-chained JSONL journal under a 0700 data dir. It speaks JSON over HTTP to the control plane and accepts alerts on a local, bearer-gated webhook. Naming note: the runtime is *Warden* (`services/warden/`); "agent", "daemon", and "federation" are reserved terms in this repo for other things.

## Before you start

Two things must exist before a Warden can do anything:

1. **A trust root on the control plane.** Warden verifies every policy pack offline against a baked-in DSSE/Ed25519 trust root (same machinery as Medic's signed packs). Generate an Ed25519 keypair, build a trust-root document (`format: "vigil.edge-trust-root/v1"` — see `core/edge/trust.schema.json`; the `policies` role signs packs, the `root` role signs trust roots), and bake the self-signed envelope into the image or mount it (see below). Trust-root updates and rotation are covered in [Trust roots](#trust-roots).
2. **An enrollment-token secret on the control plane.** The edge CLI reads the HMAC secret from the secrets manager as `EDGE_ENROLLMENT_TOKEN`. If it is not configured, minting fails with `EDGE_ENROLLMENT_TOKEN is not configured; set it before minting.`

The signing keys whose key ids appear in the trust root's `policies` role are the private halves that sign policy packs — keep them off the nodes; they never travel to Warden.

## Deploying Warden

Ports and files (the same on every surface):

| Port | Purpose | Auth |
|---|---|---|
| **8091** | Sentinel — local alert intake (`POST /alert`) | Bearer `WARDEN_SENTINEL_TOKEN` |
| **9092** | `/health` (component liveness) and `/status` (mode, journal, live actions) | none — host-local |
| **9093** | Prometheus `/metrics` | none — host-local |

State lives in `WARDEN_DATA_DIR` (default `/var/lib/vigil-warden`): `credentials.json` (node id + per-node bearer token) and `policy.json` (the verified pack), both 0600 in a 0700 directory, plus `journal.jsonl`.

### Docker Compose (edge profile)

The `warden` service ships under the `edge` profile — it is not part of the default set:

```bash
# One-time: put your trust root where the compose file mounts it.
export WARDEN_TRUST_ROOT_FILE=/etc/vigil/warden/trust-root.json

# First start: provide the one-time enrollment token.
export WARDEN_ENROLLMENT_TOKEN="vigil.enroll.v1.…"
export WARDEN_SEGMENT_LABELS="segment:dmz"
export WARDEN_SENTINEL_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

docker compose --profile edge up -d warden
```

The compose defaults do the right thing for bring-up: `WARDEN_CONTROL_PLANE_URL` points at the in-stack backend (`http://backend:6987`), the listeners bind `0.0.0.0`, health and metrics stay loopback-published on the host, state goes to the `warden_data` volume, the root filesystem is read-only, and **no capabilities are granted** — so the executor registry runs DryRun and every decision journals without blocking anything. To enforce for real on a gateway host, switch the nftables executor on:

```yaml
# docker-compose.override.yml
services:
  warden:
    cap_add: [NET_ADMIN]
```

After the first successful start, the per-node token is persisted in the data dir and `WARDEN_ENROLLMENT_TOKEN` is no longer needed — leave it empty on restarts.

### Kubernetes (Helm DaemonSet)

Set `warden.enabled=true` in the chart. The chart's own guardrails:

- **A trust root is required at render time**: `warden.trustRoot.existingConfigMap` must name a ConfigMap whose `trust-root.json` data key holds the root envelope. It is mounted read-only at `/app/trust-root/`. A node without one could never verify a pack — the chart refuses rather than hand over a node that would sit in BOOTSTRAP forever.
- **Tokens come from a warden-only Secret** (`warden.tokens.existingSecret`), are rendered by the chart from `warden.tokens.enrollmentToken` / `warden.tokens.sentinelToken`, or are materialized by the ExternalSecrets Operator (`warden.externalSecret`). The DaemonSet's token refs are `optional: true` — an enrolled node restarting legitimately has neither key present, because its credentials live in the data dir.
- **Persistence is a node-local hostPath** (`warden.persistence.hostPath`, default `/var/lib/vigil-warden`): the journal must survive pod restarts — undoable actions live in it — and a DaemonSet pod always lands back on its node. Pre-create the directory (owner `10002:10002`, mode 0700) for the strictest posture.
- **A dedicated NetworkPolicy** defaults ingress to cluster-internal traffic; set `networkPolicies.warden.sentinelAllowFrom` to the CIDRs your alert producers (EDR agents, syslog shippers) push from.
- Warden's image runs as uid/gid **10002** (Medic holds 10001, the app 1000) with `readOnlyRootFilesystem: true` and all capabilities dropped. Enabling nftables enforcement in Kubernetes is a deliberate escalation: grant `NET_ADMIN` in `warden.containerSecurityContext.capabilities.add` for the nodes that should enforce.

```bash
helm install vigil infra/helm/vigil \
  --set warden.enabled=true \
  --set warden.trustRoot.existingConfigMap=warden-trust-root \
  --set warden.tokens.enrollmentToken="vigil.enroll.v1.…" \
  --set warden.tokens.sentinelToken="…"
```

### Running from source

```bash
pip install -r requirements.lock
export WARDEN_TRUST_ROOT_PATH=/etc/vigil/warden/trust-root.json
export WARDEN_ENROLLMENT_TOKEN="vigil.enroll.v1.…"   # first start only
python -m services.warden
```

`WARDEN_TRUST_ROOT_PATH` is mandatory — without a trust root no pack can verify, and the process refuses to start. `python -m services.warden check` is the health probe the container HEALTHCHECK runs.

## Enrolling a node

Enrollment exchanges a **one-time, operator-issued token** for a per-node bearer token. The enrollment token is an HMAC-signed string that binds one node id and an expiry — and one-time is enforced by identity: a node id exists at most once, so a token is spendable exactly once.

### Mint the token

On the control plane, with `EDGE_ENROLLMENT_TOKEN` configured in the secrets manager:

```console
$ python -m services.api.edge_cli --node-id wn-7f3a --ttl-hours 24
vigil.enroll.v1.eyJub2RlX2lkIjoid24tN2YzYSIsIm5vdF9hZnRlciI6…
```

- `--node-id` must be alphanumeric with `-` or `_`, starting alphanumeric (`wn-7f3a` is the house shape).
- The token expires (default 24 h) — mint it when you are ready to enroll, not before.
- Node ids are chosen by you; a re-enrollment after revocation requires a **new** node id.

### First start

Give the node the token (`WARDEN_ENROLLMENT_TOKEN`) and its segment labels (`WARDEN_SEGMENT_LABELS`, e.g. `segment:dmz,role:gateway`). On first start Warden:

1. `POST /api/v1/edge/enroll` with the token and its segment labels → receives its `{node_id, token}` (the per-node bearer token).
2. Stores `{node_id, token}` in `credentials.json` under the data dir, 0600, and fetches + verifies the first policy pack immediately.
3. Enters `SYNCED`.

From then on the node authenticates with the per-node bearer token on every contact (`GET /api/v1/edge/policy`, `POST /api/v1/edge/journal`). Leave `WARDEN_NODE_ID` unset in normal operation — identity is persisted in the data dir; the variable, when set, is validated and shown in logs and `/status`.

Enrolling a node id that already exists → **409** (`re-enrollment requires a new identity`); an expired or otherwise invalid token → **401** with the rejection class; the control-plane secret unset → **503** (fail-closed). Nothing on the edge can extend a token's life — its expiry is inside the HMAC.

### Listing and revoking nodes

The console API (not the edge router) lists and revokes nodes; both require Settings-admin permission:

- `GET /api/v1/edge/nodes` — every node with status, labels, and `last_seen`; `?status=active|revoked` filters.
- `POST /api/v1/edge/nodes/{node_id}/revoke` — flips the node to `revoked` and records when, by whom, and why. Idempotent: revoking a revoked node re-answers without error.

Revocation is **immediate and fail-closed**: every edge route answers a revoked node's valid bearer token with **403** (`unknown token` is 401; revoked or absent node is 403), and nothing un-revokes. On its next sync the node observes the 401/403 — the one control-plane fact it accepts, and only as a tightening signal — undoes its live reversible actions best-effort, and halts permanently in `REVOKED` (see [Operating modes](#operating-modes)). Re-enrolling the same hardware means minting a token for a new node id.

`last_seen` is the control plane's only liveness signal: it is touched by every authenticated contact — a policy fetch or a journal push. Warden never phones home on a schedule beyond its sync loop.

## Operating modes

Warden's behavior changes with one question: is the control plane reachable, and is the verified pack still in force? Every transition is decided by **locally observable facts** — sync attempts, pack validity, the local clock — never by a control-plane signal that could be forged during a partition. The one exception is revocation, which can only *tighten* (halt), never loosen.

| Mode | Entry | Behavior | Enforcement | Exit |
|---|---|---|---|---|
| `BOOTSTRAP` | First start with an enrollment token | Exchanges the token for a per-node token, fetches and verifies the first pack | None | Verified pack → `SYNCED`; verification failure retries with backoff |
| `SYNCED` | Verified, unexpired pack; control plane answering | Syncs on an interval, receives alerts, triages and journals, pushes journal deltas opportunistically | None (observe) — synced-mode enforcement is off by default | 3 missed syncs → `DEGRADED`; pack expires → `PASSIVE`; revocation observed → `REVOKED` |
| `DEGRADED` | Sync failures begin | Same observation and journaling; retries with backoff; `/status` reports degraded | None | Sync recovers → `SYNCED`; grace window lapses → `AUTONOMOUS` |
| `AUTONOMOUS` | Grace window expired while the verified pack is still in force | Full local loop: triage → decide → enforce → journal, inside the signed envelope | Envelope-allowed reversible actions only, rate-capped, each with a TTL and a journal record | Link restored → `RECONCILING`; pack expires → `PASSIVE` (live actions undone first) |
| `RECONCILING` | Control plane answers again | Pushes the journal batch-by-batch with chain-head verification; undoes live actions the reconciled policy no longer authorizes | Blocked, except journal-driven undos | Journal drained → `SYNCED` |
| `PASSIVE` | Pack expired, or verification failed on a refresh | Undoes actions whose authority lapsed, keeps journaling, keeps retrying sync | None — never enforces on stale authority | Fresh verified pack → `SYNCED` |
| `REVOKED` | Server revocation observed at sync | Undoes live reversible actions best-effort, halts the loop, leaves the journal for forensic pull | None, permanently | Terminal |

**What gates AUTONOMOUS, exactly:** the node must have entered `DEGRADED` (the default `WARDEN_MISSED_SYNCS_THRESHOLD=3` consecutive sync misses), the grace window (default `WARDEN_GRACE_WINDOW_SECONDS=900`, 15 minutes) must have elapsed, and a verified pack whose `not_after` has not passed must still be in force. Nothing enforces during the grace window; a node whose pack expired while partitioned drops to `PASSIVE`, not `AUTONOMOUS`.

## The signed policy pack

A policy pack is a DSSE v1 envelope with an Ed25519 signature over a strict-JSON payload:

```json
{
  "payload": { "…": "the containment policy" },
  "payloadType": "application/vnd.deeptempo.vigil.edge-policy.v1+json",
  "signatures": [ { "keyid": "…", "sig": "…" } ]
}
```

Warden **verifies before parsing**: the envelope's signature is checked against the baked-in trust root before the payload is parsed — a tampered or unknown-key pack is rejected as bytes, with the rejection class recorded, not parsed into life. Strict JSON throughout: duplicate keys, NaN/Infinity, and trailing data are rejections.

### Payload fields

| Field | Meaning |
|---|---|
| `format` | Always `"vigil.edge-policy/v1"`. |
| `policy_version` | Monotonic per node (≥ 1). A node holding v42 refuses v41; a re-presented v42 whose payload hashes differently from the stored one is rejected (tamper or replay). |
| `issued_at` / `not_before` / `not_after` | Validity window, `YYYY-MM-DDTHH:MM:SSZ`. `issued_at ≤ not_before`, the window is at most **7 days**, and `not_after` is fail-closed: at that instant live actions are undone and the node drops to `PASSIVE`. |
| `node_selectors` | `key:value` labels the control plane targets the pack at (e.g. `segment:dmz`). Must include at least one of the receiving node's labels. |
| `autonomy_envelope` | The hard ceiling on local enforcement — see below. |
| `protected_targets` | Which target classes the guard refuses, from `self`, `gateway`, `control_plane`, `dns_resolvers`. |
| `rules` | Rule list (may be empty — a pack that only tightens the envelope is legal). Each rule: `rule_id` (`edge-…`), `match` (`indicator: "ip"`, optional `mitre` list, optional `min_local_confidence`), `action` (`type: "block_ip"`, `ttl_minutes`). |
| `model_manifest` | Optional — present when the pack expects an on-device SLM: `{name, sha256, format: "gguf"}`. |

Semantic checks run after signature and schema: an expired, not-yet-valid, over-long-window, unenforceable-rule, or rule-TTL-exceeding pack is rejected with its class (`P-WINDOW`, `P-LIFETIME`, `P-EXPIRED`, `P-NOT-YET-VALID`, `P-RULE-ID`, `P-RULE-UNENFORCEABLE`, `P-RULE-TTL`). A rejected pack never takes force; the node keeps its previous verified pack (or has none).

## The autonomy envelope

The envelope is the signed ceiling on everything Warden may do while partitioned. It travels **inside the signature** — it is not configurable at the edge, not DB-overridable, not env-overridable. An env var or database row cannot widen it, and every knob below is enforced by the decision ladder regardless of what a rule claims.

| Field | What it caps |
|---|---|
| `allowed_actions` | Which action types may enforce at all. v1 ships one: `block_ip`. Anything outside the list refuses (`action-not-in-envelope`). |
| `max_actions_per_hour` | The hourly rate cap, 0–1000. **0 is valid**: an envelope that allows nothing. Judged in fixed wall-hour buckets — not a rolling window — so the budget refills at the top of each hour from `not_before`; a restart forgives spent budget (it is in-process state, not persisted), but the cap itself can only be changed by a new signed pack. |
| `max_action_ttl_minutes` | The longest a single action may live (1–1440). A rule asking for more refuses (`ttl-exceeds-envelope`), it is not clamped down. |
| `require_reversible` | When true (the sane setting), an action the node cannot undo never enforces (`irreversible-not-allowed`). v1's only action, `block_ip`, is reversible by construction (delete the element). |
| `confidence_floor` | The minimum local confidence a match must reach, 0–1. The effective floor is `max(envelope.confidence_floor, rule.match.min_local_confidence)`. Out-of-range confidence (NaN, 5.0) refuses outright — it never reads as high. |
| `allow_slm_decisions` | Whether the on-device SLM's confidence may *decide* (see [Optional SLM triage](#optional-slm-triage)). Default false: the SLM's output is advisory ranking only. |

The ladder evaluates in a fixed order and **refuses by default** — no check "loosens" a previous one. Refused decisions that fail before the rate-cap check never spend the budget: a flood of guard refusals cannot exhaust the hour for legitimate enforcement.

## Enforcement semantics

### The decision ladder

Every candidate enforcement runs `core/edge/decision.py`'s ladder, in order, each step returning a refusal class or moving down:

| # | Check | Refusal class |
|---|---|---|
| 1 | Action type in the envelope's `allowed_actions` | `action-not-in-envelope` |
| 2 | Confidence in `[0, 1]`, then at or above the effective floor | `below-confidence-floor` |
| 3 | SLM-sourced confidence only when `allow_slm_decisions` is true | `slm-decisions-not-allowed` |
| 4 | Action reversible when `require_reversible` is true | `irreversible-not-allowed` |
| 5 | Target not protected (guard runs **before** the cap) | `protected-target` |
| 6 | Rule TTL within `max_action_ttl_minutes` | `ttl-exceeds-envelope` |
| 7 | Hourly budget available (and the runtime's budget not derived wider than the signed cap) | `rate-cap-reached` |
| 8 | Pack not expired on the node's clock (`now < not_after`) | `policy-expired` |

Only an `allow` at the bottom reaches an executor. Every decision — allow **and** refuse — is rendered into a `decision_rule` line (e.g. `edge-001 met (slm 0.93 >= floor 0.90, ttl 30 <= 30, cap 3/5)`) and journaled, so any autonomous action reconstructs from the journal alone.

### Protected targets

Before any executor runs, the target is checked against the **protected-target guard** (`core/edge/target_guard.py`):

- **Always protected, unconditionally**: loopback, unspecified, multicast, and reserved addresses, plus every address the operator listed as this node's own (`WARDEN_SELF_ADDRESSES`) — self-lockout is impossible by construction.
- **Signed categories** (`gateway`, `control_plane`, `dns_resolvers`) are protected when the pack lists them, using **node configuration** (`WARDEN_GATEWAY_ADDRESSES`, `WARDEN_CONTROL_PLANE_ADDRESSES`, `WARDEN_DNS_RESOLVERS`) — the operator's own view of the segment, never alert data. A rule can never nominate a protected target.
- Link-local targets are treated as the gateway. An unparseable target is refused, not guessed.

This closes the hole in the central responder's `_actionable_ip`, which filters loopback and reserved space but acts on whatever IP an alert carries.

### The nftables executor

v1 ships one local action: **`block_ip`** via a dedicated nftables table — Warden touches nothing else in your firewall.

- Table `inet vigil_warden`, set `blocked_ips` (IPv4, `flags timeout`), chain `ingress_guard` hooked on `input` at priority `filter`, policy `accept`, with the drop rule `ip saddr @blocked_ips drop`.
- Enforce = add the element with a timeout of `ttl_minutes` × 60 s; the block then expires in the kernel even if Warden dies. Undo = delete the element. Both are idempotent on retry.
- **IPv4 only in v1.** An IPv6 target fails with an `unsupported-address-family` execution result — recorded honestly, never claimed as a block.

### DryRun fallback

When nftables is unavailable, or Warden runs without the privileges it needs (the compose default — no capabilities), the executor registry selects the **DryRun** executor: every decision still triages, decides, and journals, the execution records carry `status: dry-run, executor: dry-run`, and nothing actually blocks. The health surface reports the mode. A success is never recorded for containment that did not happen — the lesson from the central `isolate_host` stub, kept by construction.

### Undo paths

A reversible live action is undone, and the undo journaled, on any of:

- **TTL expiry** — swept on every tick (`ttl-expired`), even before the kernel timeout fires.
- **Policy expiry** — `not_after` reached; the node drops to `PASSIVE` after undoing (`policy-expired`).
- **Policy change** — a new verified pack whose rules no longer authorize a live action (`policy-version-change`), including the reconcile-path undo in `RECONCILING`.
- **Revocation** — observed at sync; best-effort undo, then permanent halt (`revoked`).

## Feeding alerts to the Sentinel

Warden's local alert intake is the daemon-webhook pattern: a fail-closed bearer receiver.

```bash
curl -sS -X POST "http://warden-host:8091/alert" \
  -H "Authorization: Bearer $WARDEN_SENTINEL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "edr-8842", "indicator": "ip", "value": "198.51.100.7",
       "mitre": ["T1071"], "confidence": 0.93}'
```

- **Auth is fail-closed**: `WARDEN_SENTINEL_TOKEN` unset → 503 for every push; wrong token → 401.
- A push is **one alert object** or `{"alerts": […]}` (batch up to `WARDEN_MAX_ALERT_BATCH=100`); body cap 1 MiB (413 over).
- Alert fields: `id` (required — deduped per node), `indicator` (`"ip"` in v1), `value` (the IP), `mitre` (optional list; rules with MITRE matchers require a subset of it), `confidence` (optional sensor confidence, 0–1).
- Accepted → **202** `{"queued": n}`; queue full → **503** (hold-and-retry is the producer's job — the connector pattern); malformed → **400**.

Whatever a rule needs beyond the indicator arrives as alert fields; the SLM (below) can rank and refine the confidence, but never invents a target.

## Reconciliation

While connected, Warden pushes journal deltas opportunistically (`WARDEN_RECONCILE_INTERVAL_SECONDS=30`). When the control plane comes back after a partition, the same push drains the journal — the loop is `AUTONOMOUS → RECONCILING → SYNCED`.

`POST /api/v1/edge/journal` (per-node bearer token) carries the node's current chain head and a batch of records (default ≤ 100). Each record is the full decision provenance:

```json
{ "seq": 1338, "ts": "2026-10-09T13:02:11Z", "mode": "AUTONOMOUS",
  "idempotency_key": "block_ip:198.51.100.7", "action_type": "block_ip",
  "target": "198.51.100.7",
  "decision_rule": "edge-001 met (slm 0.93 >= floor 0.90, ttl 30 <= 30, cap 3/5)",
  "execution": { "status": "executed", "executor": "nftables", "at": "2026-10-09T13:02:12Z" },
  "prev_hash": "77be…" }
```

The chain is `sha256(prev_hash ‖ record)` — the `agent_events` pattern — so gaps and edits are detectable on the server:

- **200** → `{accepted_through, duplicate_ids, rejected, receipt_id, merged_count}`. Accepted records merge into the existing **`approval_actions`** table: `created_by = "edge:{node_id}"`, `parameters.source = "edge"` with node/policy-version/seq/mode preserved, `idempotency_key` deduping re-pushes, `execution_result` preserved. A dry-run execution merges as a **pending** row with `requires_approval: true` — the control plane sees what the node *would* have done and nobody treats it as containment. One **receipt row** (`edge_journal_receipts`) records the accepted range and the new per-node chain head.
- **409 (chain problem)** → `{reason, server_last_seq, server_head, resend_from}` with `reason` one of `empty-batch`, `seq-order`, `seq-gap`, `chain-mismatch`, `head-mismatch`. Warden resends from `resend_from` — the server-held head — so at-least-once delivery over a flaky link costs nothing: re-pushed batches resolve to the existing receipt, and merges dedupe on `idempotency_key`.
- **Legality is re-checked at merge time, by policy version** — never by wall time: a record whose cited policy version is unavailable or whose action the cited pack never allowed (`policy-version-unavailable`, `action-not-in-envelope`) is returned in `rejected[]` and refused from the merge, though the chain still advances past it.
- **403** (revoked node) / **401** (unknown token) — both fail-closed; a revoked node's journal stays on the node for forensic pull.

If the node's own journal cannot reproduce the server's chain head (edited or trimmed records), the reconciler **halts sticky** rather than push a chain it cannot verify — the journal's health, including any poisoned-line reason, is on `/status`.

## Optional SLM triage

Warden can run a quantized security SLM on-device (llama.cpp GGUF, 1B–3B class) to rank and confirm rule matches. It is an **optional dependency group** — deliberately absent from `requirements.lock` so a native-build dependency never lands in every image:

```bash
pip install -r requirements-warden-slm.txt   # llama-cpp-python>=0.3.0
export WARDEN_SLM_MODEL_PATH=/var/lib/vigil-warden/models/security-slm-1b-q4.gguf
```

- **Model files are never committed or fetched.** The signed pack's `model_manifest` carries `{name, sha256, format}`; Warden verifies the on-disk file's sha256 against it **before every load**. Any mismatch (`hash-mismatch`, `format-unsupported`, `file-missing`) or a failed load refuses the model — the runtime degrades to **rules-only triage**, never to an unverified binary.
- **Advisory by default.** `allow_slm_decisions` is false unless a signed pack says otherwise: the SLM's ranking refines the local confidence as *advisory* (annotated `slm advisory rank=N (advisory only, not deciding)` in the decision rule), and SLM-sourced confidence that would *decide* refuses with `slm-decisions-not-allowed`. Granting decision authority is an operator opt-in, signed into the pack — per policy, not per node config.
- The SLM channel's state (`ready`, and every failure state) is on `/status` and counted in `warden_slm_opinions_total{deciding|advisory|unavailable}`.

## Publishing policy packs

The control plane serves whichever `edge_policies` row is `active` for a node (exactly one per node, enforced by a partial unique index; a pack aimed at a selector lands once per addressed node). Today the authoring step is a **library surface, not a product surface**: there is no shipped CLI or API endpoint that composes, signs, or publishes packs. The control-plane operator path is:

1. Compose the payload per `core/edge/policy.schema.json` (every field closed — unknown fields are rejections).
2. Sign it with the trust root's `policies`-role keys via `core.edge.signing.sign_envelope(payload_bytes, "application/vnd.deeptempo.vigil.edge-policy.v1+json", [keys])`.
3. Insert the `edge_policies` row (`envelope`, `payload_hash`, `signing_key_ids`, the mirrored validity window) with status `draft`, then flip it to `active` — the status transition timestamps give the audit its "when did this policy stop applying" answer.

Versions are monotonic per node: publish vN+1 to change anything; a re-presented vN whose payload hash differs is tamper or replay and is refused.

## Trust roots

The trust root is the same TUF-shaped document Medic uses (`core/edge/trust.schema.json`): versioned, expiring (a root may live at most **400 days**), with `root` and `policies` roles (thresholds 1–8, each role restricted to its payload types), `revoked_keyids`, and per-key expiry. It is baked into the Warden image or mounted read-only; the envelope must be self-signed by the current root role, verified at load.

Updates follow the same rules as Medic's: a root updates only to a **newer version signed by the current root's threshold** — key rotation additionally requires the new root's own signature, and **no update can un-revoke** a key. `S-ROOT-*` rejection classes cover version regressions, un-revocation attempts, threshold changes, and schema drift; a root past `expires_at` is a load-time failure, which is why rotation deadlines belong on the same calendar as pack expiry.

## Observability

- `GET :9092/health` — component liveness: 200 `{"status": "healthy"}` while every component task is alive, 503 when one has died. The container HEALTHCHECK (`python -m services.warden check`) and the Helm probes all read this — a Warden that stopped defending must look stopped.
- `GET :9092/status` — mode (and transition count), node id, policy version, journal state (`last_seq`, `head`, `poisoned` + reason), live actions, reconciled-through watermark, SLM state.
- `GET :9093/metrics` — Prometheus text. `warden_sync_attempts_total{outcome}`, `warden_decisions_total{result}`, `warden_enforcements_total{status,executor}`, `warden_journal_appends_total{result}`, `warden_undo_total{reason}`, `warden_sentinel_rejections_total{reason}`, `warden_slm_opinions_total{outcome}`, `warden_reconcile_attempts_total{outcome}`, `warden_reconcile_records_total{result}`, and the `warden_live_actions` gauge.

## Environment variables

`WARDEN_CONTROL_PLANE_URL` — control-plane base URL (default `http://127.0.0.1:6987`).
`WARDEN_NODE_ID` — optional; validated and shown in logs and `/status`. Enrollment persists identity in the data dir; leave unset in normal operation.
`WARDEN_ENROLLMENT_TOKEN` — one-time enrollment token, first start only.
`WARDEN_SEGMENT_LABELS` — comma-separated segment labels the control plane targets packs with.
`WARDEN_DATA_DIR` — 0700 state dir (default `/var/lib/vigil-warden`).
`WARDEN_TRUST_ROOT_PATH` — baked-in trust root envelope (**required**; the process refuses to start without it).
`WARDEN_SYNC_INTERVAL_SECONDS` — policy sync cadence (default 60).
`WARDEN_SYNC_TIMEOUT_SECONDS` — per-attempt HTTP timeout (default 10).
`WARDEN_MISSED_SYNCS_THRESHOLD` — consecutive misses that leave `SYNCED` (default 3).
`WARDEN_GRACE_WINDOW_SECONDS` — `DEGRADED` dwell time before `AUTONOMOUS` (default 900).
`WARDEN_RECONCILE_INTERVAL_SECONDS` — journal push cadence when connected (default 30).
`WARDEN_RECONCILE_BATCH_SIZE` — max journal records per reconcile push (default 100).
`WARDEN_SENTINEL_TOKEN` — local webhook bearer; unset = receiver fail-closed.
`WARDEN_SENTINEL_PORT` / `WARDEN_HEALTH_PORT` / `WARDEN_METRICS_PORT` — listener ports (8091 / 9092 / 9093).
`WARDEN_BIND_HOST` — bind address for all listeners (default loopback; containers set `0.0.0.0`).
`WARDEN_MAX_ALERT_QUEUE` / `WARDEN_MAX_ALERT_BATCH` / `WARDEN_MAX_ALERT_BYTES` — Sentinel queue depth (1000), batch size (100), and body cap (1 MiB).
`WARDEN_SELF_ADDRESSES` / `WARDEN_GATEWAY_ADDRESSES` / `WARDEN_CONTROL_PLANE_ADDRESSES` / `WARDEN_DNS_RESOLVERS` — the address groups the protected-target guard uses; node configuration, never alert data.
`WARDEN_SLM_MODEL_PATH` — optional GGUF model file; sha256-verified against the signed pack's manifest before load.
`WARDEN_LOG_LEVEL` — `DEBUG|INFO|WARNING|ERROR` (default `INFO`).

Nothing on this list widens the signed autonomy envelope — the environment configures the process, never the authority.

## v1 limitations

Block-IP over IPv4 via nftables only; no process-kill or EDR-write executors; revocable bearer tokens rather than mTLS; no multi-tenancy; pack authoring/publishing is a library-plus-SQL surface, not a product UI. These are scope decisions recorded in the feature spec, not omissions to work around.

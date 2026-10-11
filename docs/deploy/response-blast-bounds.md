# Response Blast Bounds (Feature 7)

Three fail-closed gates sit between the Responder's confidence and the
containment actuator, so forged or excessive findings cannot turn Vigil's
auto-approval into the outage:

1. **Protected assets** — never-quarantine invariants for operator-declared
   critical infrastructure (a DNS server, a domain controller, the egress
   gateway).
2. **Blast-radius quotas** — bounded containment volume per window, with a
   circuit breaker on breach.
3. **Origin trust** — findings must carry a cryptographically verified origin
   attestation before they can evidence an automated block.

Every gate rejects toward the same place: the action becomes a pending human
approval carrying the gate's rationale. Nothing is dropped silently, and
nothing is executed against a held target.

---

## What changes on upgrade

If you run `daemon_auto_response=true` (the default), Feature 7 changes
upgrade behavior on purpose:

> Enforcement of origin validation is ON by default — deployments without
> registered signing keys get human approval instead of auto-execution, and
> registering keys restores machine speed.

In other words: until you register Ed25519 signing keys for your sensors (see
[Origin trust](#origin-trust)), auto-approval is suspended and every
containment proposal waits for a person. That is the documented, intended
safe failure mode. Deployments with `daemon_auto_response=false` are
unaffected — the gates only interpose on the automated path.

The default quota and breaker values are safe-first guesses, not
measurements. Ship with them, watch the audit surfaces listed at the end of
this page, and tune.

---

## The guard chain

When the Responder decides an action, the chain runs
**invariant → breaker → origin → quota** — cheapest and most specific first —
inside action creation, before the confidence-based approval gate. The same
invariant and breaker checks run again inside the approved-execution loop
before anything dispatches, closing the create→execute gap when configuration
changes or the breaker trips in between.

| Gate | Question it answers | On rejection |
|------|--------------------|--------------|
| Protected asset | Is the target operator-declared critical? | Pending approval, always |
| Breaker | Is auto-response currently suspended? | Pending approval, always |
| Origin | Does every evidencing finding carry a verified stamp? | Pending approval |
| Quota | Is the containment budget spent? | Pending approval (soft), breaker trip (hard) |

A rejection is not a drop: the action row is created as `pending_approval`
with the gate's rationale on the row, and the decision is recorded in
`ai_decision_logs` (decision type `response_guard`). The escalation path is
the existing Slack/PagerDuty flow. Dry-run mode evaluates and logs the guards
without creating, executing, or spending quota.

The happy path is unchanged: when every gate passes, the confidence band
behaves exactly as before.

---

## Protected assets

A protected asset is a declared invariant: the Responder never auto-executes
against it, at any confidence, at any severity. A person may still approve a
pending protected-asset action — the deliberate emergency valve for a domain
controller that genuinely is compromised — and the audit row records the
override.

### Declaring protected assets

Two ways; they compose.

**Seed from environment at daemon boot** — `DAEMON_PROTECTED_ASSETS` takes a
JSON array. Malformed JSON prevents startup (fail closed):

```bash
DAEMON_PROTECTED_ASSETS='[{"match_kind":"ip","match_value":"10.0.0.53","asset_class":"dns","label":"prod-dns-1"}]'
```

**Manage through the admin API** (authenticated, writes `config_audit_log`):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/response/protected-assets` | List active assets (`?include_removed=true` for history) |
| `POST /api/v1/response/protected-assets` | Declare an asset — active immediately; the index cache drops so the next action sees it |
| `DELETE /api/v1/response/protected-assets/{asset_id}` | Retire protection (soft delete; reason goes in the body) |

Fields: `match_kind` (`ip` | `cidr` | `hostname`), `match_value`,
`asset_class` (`dns` | `domain_controller` | `gateway` | `dhcp` |
`database` | `other`), `label`. At most one active row per (kind, value);
duplicates return 409.

### Matching semantics

- **IP** — exact match.
- **CIDR** — longest-prefix wins when ranges overlap (a /32 row beats a /24
  row covering the same address).
- **Hostname** — case-insensitive exact match. Domain-suffix matching is
  deliberately not used: `db-primary` matches `db-primary`, not
  `db-primary.lab.example.com`.

### Fail-closed behavior

The in-memory index is backed by PostgreSQL. If the cache is empty and the
database is unreachable, the gate treats **every** target as protected —
machine-speed response waits for a person rather than acting on an
unverified invariant set.

Protected assets govern action execution only. `ip_exclusions` remains a
finding-visibility mechanism and is untouched by Feature 7; the two are
kept deliberately separate.

---

## Blast-radius quotas

Quotas bound how much containment automation may execute per window. There
is no subnet registry in the product, so per-subnet scope is derived from
the target IP at a configurable prefix (default /24): a /24 yields 254
usable hosts, so 5%/min means 12 actions per minute per /24 (a floor of 1
keeps tiny scopes enforceable).

| Limit | Default | On breach |
|-------|---------|-----------|
| Per-subnet actions/min (`DAEMON_CONTAINMENT_QUOTA_SUBNET_PCT_PER_MIN`) | 5% of usable hosts at `DAEMON_SUBNET_SCOPE_PREFIX` | Soft — pending approval for the rest of the window |
| Global actions/min (`DAEMON_CONTAINMENT_QUOTA_GLOBAL_PER_MIN`) | 30 | Soft — pending approval |
| Global actions/hour (`DAEMON_CONTAINMENT_QUOTA_GLOBAL_PER_HOUR`) | 200 | **Hard — trips the circuit breaker** |

Operational notes:

- Quota is consumed when an action is approved for auto-execution. The
  execution re-check refuses if the window has since gone over the hard
  ceiling; a person-approved action still passes.
- Counters are Redis keys with window TTL. When Redis is unavailable, a
  per-process in-memory fallback keeps enforcing **but is not shared across
  replicas** — multi-replica deployments need Redis for accurate global
  enforcement. Every degradation transition is logged loudly.
- Disable entirely with `DAEMON_CONTAINMENT_QUOTAS_ENABLED=false` (not
  recommended for auto-response deployments).

---

## Circuit breaker

The breaker is daemon-wide: while it is open, **every** action becomes a
pending approval — verified, under-quota, whatever. It exists to catch the
volume weapon (a flood of forged findings) and to contain the one race the
quota windows cannot (the create→execute gap).

### Trip conditions

| Condition | Threshold | Feed |
|-----------|-----------|------|
| Quota hard ceiling | Hourly global quota breached | `DAEMON_CONTAINMENT_QUOTA_GLOBAL_PER_HOUR` |
| Protected-asset probing | ≥ `DAEMON_BREAKER_INVARIANT_PROBE_TRIP` (3) blocked attempts in 10 min | Someone is probing critical assets |
| Origin-unverified flood | ≥ `DAEMON_BREAKER_ORIGIN_FLOOD_TRIP` (10) blocked attempts in 10 min | A spoofing flood, which also protects the human queue |

### Lifecycle

The breaker opens for `DAEMON_BREAKER_COOLDOWN_SECONDS` (default 900 s),
then auto-closes with trip counters decaying over twice the cooldown; any
new condition re-trips immediately. While open, exactly one escalation event
fires — not one per action — so the human queue is not drowned by the very
flood that tripped the breaker.

**The honest trade-off:** an adversary can trip the breaker and switch
auto-response off. That is the safe side of the failure — forced human
approval is the correct degraded state. An attacker can force human mode;
they cannot force bad containment.

### Admin surface

```bash
# State, trip counters, and cooldown remaining
GET /api/v1/response/breaker

# Manually close the breaker and clear trip counters (audited, permission-gated)
POST /api/v1/response/breaker/reset
```

Breaker transitions are written to `config_audit_log`.

---

## Origin trust

Every finding may carry an origin attestation: a DSSE envelope signed with
Ed25519 by the sensor that produced it, sent on the webhook alongside the
existing bearer token:

```
X-Vigil-Origin-Attestation: {"payload_type":"https://vigil.example/schemas/finding/v1",
                             "payload":"<base64 canonical finding JSON>",
                             "signatures":[{"keyid":"sensor-edge-01","sig":"<base64>",
                                            "iat":1760000000,"jti":"01J…"}]}
```

The signature covers the full payload, so it cannot be transplanted onto a
forged finding. Verification happens at webhook ingest: bad signature,
unknown key, `iat` older than 300 s, or a replayed `jti` still stores the
finding — but with `origin_verified=false`, a security-log entry, and a
counter toward the breaker's origin-flood trip.

### Registering trust roots

Trust roots live in `DAEMON_TRUSTED_ORIGINS` (JSON array; malformed JSON
prevents startup):

```bash
DAEMON_TRUSTED_ORIGINS='[{"origin_id":"sensor-edge-01","public_key":"<base64 Ed25519>","scope":"auto_response","enabled":true}]'
```

- `origin_id` — matches the attestation `keyid`.
- `public_key` — base64 Ed25519 public key.
- `scope` — `auto_response` scopes the origin for automated containment.
- `enabled` — flip to `false` to revoke without deleting.

Auto-response requires every evidencing finding to be origin-verified from
an origin scoped for auto-response. Unsigned or unverified evidence routes
the action to human approval. Registering keys is what restores machine
speed — see [What changes on upgrade](#what-changes-on-upgrade).

Sensor-side signing is not implemented in this repository; this feature
ships the wire format, the verifier, and this documentation. Senders adopt.

---

## Configuration reference

All knobs are typed settings on the daemon (env prefix `DAEMON_`), documented
in `env.example`. Defaults are safe-first, operator-tunable; changing them
changes config, not code.

| Env var | Default | Controls |
|---------|---------|----------|
| `DAEMON_PROTECTED_ASSETS` | `[]` | Boot seed of never-quarantine invariants (JSON) |
| `DAEMON_CONTAINMENT_QUOTAS_ENABLED` | `true` | Master switch for blast-radius quotas |
| `DAEMON_SUBNET_SCOPE_PREFIX` | `24` | Prefix length deriving quota scope from the target IP |
| `DAEMON_CONTAINMENT_QUOTA_SUBNET_PCT_PER_MIN` | `5.0` | Per-subnet actions/min, as % of usable hosts |
| `DAEMON_CONTAINMENT_QUOTA_GLOBAL_PER_MIN` | `30` | Global actions/min (soft limit) |
| `DAEMON_CONTAINMENT_QUOTA_GLOBAL_PER_HOUR` | `200` | Global actions/hour (hard limit — trips the breaker) |
| `DAEMON_BREAKER_COOLDOWN_SECONDS` | `900` | How long the breaker stays open |
| `DAEMON_BREAKER_INVARIANT_PROBE_TRIP` | `3` | Protected-asset blocks in 10 min that trip the breaker |
| `DAEMON_BREAKER_ORIGIN_FLOOD_TRIP` | `10` | Unverified-origin blocks in 10 min that trip the breaker |
| `DAEMON_TRUSTED_ORIGINS` | `[]` | Ed25519 origin trust roots (JSON) |

---

## Known limitations

Stated plainly, because they shape what an operator can expect:

- **No EDR executor for `isolate_host`.** Host isolation still reports
  `unsupported_action_type`; quotas and gates are physically real today for
  `waf_block`, `gateway_block`, and `access_revoke`. Host isolation inherits
  the same gates for the day an executor lands.
- **No asset inventory.** The protected set is whatever the operator
  declares — there is no auto-discovery of critical assets.
- **The breaker is daemon-wide in v1.** One noisy subnet suspends
  auto-response everywhere until the cooldown elapses. Per-subnet breakers
  are the follow-up if that bites.

## Audit surfaces

Every gate outcome is observable:

- Action rows carry the gate's rationale; guard denials land in
  `ai_decision_logs` (decision type `response_guard`).
- Protected-asset and trust-root changes, breaker transitions, and manual
  breaker resets write `config_audit_log`.
- Rejected attestations are logged on the security log and counted toward
  the breaker's origin-flood trip.

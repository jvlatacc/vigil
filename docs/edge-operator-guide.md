# Edge daemons — operator guide

Lightweight daemons on cluster nodes and VPC gateways that keep defending
their segment with pre-distributed signed policies when the Vigil control
plane is unreachable — then reconcile everything when it returns. The
architecture, autonomy tiers, and conflict-precedence rules live in the
design spec; this guide covers deploying, enrolling, and operating them.

- Cluster mode: a Kubernetes DaemonSet talks to the API server and contains
  with reversible egress-deny NetworkPolicies. No host privileges needed.
- Gateway mode: a container (or bare process) on a VPC gateway manages a
  dedicated `vigil_edge` nftables table. Needs host networking and
  `NET_ADMIN`.

The daemon is off unless enabled: every entry point below assumes
`VIGIL_EDGE_ENABLED=true` on the daemon and the deployment surface
(Helm values or the compose `edge` profile) switched on explicitly.

## Before you enroll anything

Three things must exist and be distributed out-of-band. They are the trust
boundary of the whole feature — treat them like keys, not config:

1. **Bundle signing key** (`VIGIL_EDGE_SIGNING_KEY_FILE` on the control
   plane). Ed25519 private key; every policy bundle is DSSE-signed with it.
2. **Enrollment secret** (`VIGIL_EDGE_ENROLLMENT_SECRET` on the control
   plane). HMAC root for one-time enrollment tokens. If it is unset, the
   enroll endpoint fails closed (503) — no token can be minted or honored.
3. **Trust root** (`VIGIL_EDGE_TRUST_STORE` on each daemon). The offline
   TUF-shaped trust-root document the daemon uses to verify bundles
   without ever calling home. Distribute it when you provision the node —
   see the decision point below on baked-in vs fetched-at-enrollment.

Compose exposes 1 and 2 on the backend service; both fail closed when the
files/secrets are absent.

## Kubernetes — cluster mode

The chart ships an `edgeDaemon` values surface, off by default:

```yaml
edgeDaemon:
  enabled: true
  mode: cluster
  nodeId: gw-cluster-east-01        # must be unique per node
  segmentScope:                      # JSON scope document; bundles must match
    cidrs: ["10.42.0.0/16"]
    nodeSelector:
      vigil.ai/edge-role: gateway
  trustStore:                        # mount an operator-provided ConfigMap
    configMapName: vigil-edge-trust-root
    key: trust-root.dsse.json
  enrollment:
    existingSecret: vigil-edge-enrollment   # or externalSecret below
    # externalSecret:
    #   name: vigil-edge-enrollment
    #   secretStoreRef:
    #     name: vault-backend
    #     kind: ClusterSecretStore
```

What the templates create when enabled:

| Template | Content |
|---|---|
| `edge-daemonset.yaml` | The DaemonSet: nodeSelector/tolerations from values, health probe on `:9091`, state volume, trust-root + credential mounts |
| `edge-rbac.yaml` | Dedicated ServiceAccount and a namespace-scoped Role: `create`/`delete` on `networkpolicies` in the managed namespaces only — no secrets, no workload mutation |
| `edge-enrollment-secret.yaml` | Chart-managed enrollment Secret (used when `existingSecret` is empty and ESO is off) |
| `edge-enrollment-externalsecret.yaml` | ExternalSecret via External Secrets Operator, same shape as the platform secrets |

Enrollment in cluster mode: put the one-time token for the node in the
Secret under `VIGIL_EDGE_ENROLLMENT_TOKEN` (or let ESO sync it from your
secret store). The daemon exchanges it for a per-node bearer credential on
first boot, stores the credential at `VIGIL_EDGE_CREDENTIAL_FILE`, and
burns the token. The token never needs to exist again — re-enrollment is a
new token.

Cluster mode talks to the API server with the pod's service-account
token; `VIGIL_EDGE_K8S_API_URL` stays empty unless you deliberately point
the daemon at a remote API.

## Docker Compose — gateway mode

The `edge` profile adds an `edge` service to `infra/docker/docker-compose.yml`:

```bash
cd infra/docker
docker compose --profile edge up -d
```

The profile is opt-in and fails closed: the service refuses to start
without `VIGIL_EDGE_NODE_ID` and a real trust-root file mounted at
`/etc/vigil-edge/trust-root.dsse.json`. The compose env file carries the
enrollment token; the state volume (`vigil-edge-data`) holds the journal,
policy cache, and credential across restarts.

Gateway reality check: real gateway containment requires the daemon's
network namespace to be the segment's path — a `hostNetwork`-style
override plus `NET_ADMIN` (already granted in the compose service). The
compose file ships with bridge networking and documents the override in
comments; **leaving it bridged means the nftables table applies inside the
container namespace only** — right shape for e2e drills, wrong for
production containment. The same applies to bare-metal installs: run the
daemon where the traffic actually flows.

## Configuration

The full variable list with defaults lives in `env.example` under the
`Edge daemon` section — env.example is the ratchet-enforced source of
truth, not this guide. The ones operators actually touch:

| Variable | Notes |
|---|---|
| `VIGIL_EDGE_NODE_ID` | Unique per daemon; part of every decision's actor string |
| `VIGIL_EDGE_SEGMENT_SCOPE` | JSON scope document the bundle must match; accepts the rich form (cidrs + node_selector) |
| `VIGIL_EDGE_MODEL` | Any 1B–3B quantized model via Ollama or an OpenAI-compatible endpoint. **Set it explicitly empty to disable the advisor** — deterministic rules only |
| `VIGIL_EDGE_MODEL_DIGEST` | Pin the model by digest; a tier-2 bundle refuses to run unpinned models |
| `VIGIL_EDGE_EVE_PATH` | JSON-lines telemetry to tail (Suricata EVE and similar). Cold start reads from EOF — create the file before the daemon starts |
| `VIGIL_EDGE_NODE_LABELS` | Labels the bundle's `node_selector` matches |

Caps, TTLs, confidence bands, and the action allowlist are **not** env
vars — they live in the signed bundle, where changing them is a reviewed
document plus a signature, not a flag flip on a box.

## Operating states

The daemon has four states; a partition changes what it may do, never
whether it runs. Health exposes the current state on `:9091/health`
(`{"state": ..., "tier": ...}`), and every transition is journaled.

| State | You should… |
|---|---|
| `synced` | Nothing. Normal operation: live sync, bundle current |
| `partitioned` | Leave it alone. It is enforcing the last-known-good bundle within its signed caps; everything is journaled. Restoring connectivity is the fix, not poking the daemon |
| `reconciling` | Let it drain. Bounded batches upload with durable acks; a drift report follows as an `offline_window` finding |
| `degraded` | Investigate: bundle expired, signature untrusted, or trust-store unreadable. The daemon is observing-only until a valid bundle arrives — it will not extend an expired one locally by design |

The drift report (an `offline_window` finding with `phase: close`) is the
reconciliation artifact: what executed and why (rule string + confidence
+ model version), what TTLs already reverted, and what still needs an
analyst decision. Offline actions import as executed rows with edge
provenance — undo is an explicit analyst decision in the existing
approval surface, never automatic.

## Revocation

To pull a node's autonomy: `POST /internal/edge/nodes/{node_id}/revoke`
with operator credentials. The credential dies and bundle revocation
propagates on the node's next pull; a revoked node fails closed to
observe-only and cannot re-enroll with an old token. Revocation beats
every local allowance.

## Decision points left open (deliberately)

Three questions in the design spec are owned by the platform owner. v1
ships env-configurable defaults; changing them is config, not code:

1. **Signing-key ceremony — file vs KMS.** Default: file-based DSSE key
   (`VIGIL_EDGE_SIGNING_KEY_FILE`), mounted from a Kubernetes Secret or
   your secret manager. KMS-backed signing would replace the file
   rotation story, not the bundle flow.
2. **Edge-health surfacing — metrics vs dashboard tiles.** Default:
   metrics + health endpoint only (no fleet UI in v1). The states and
   counters above are Prometheus-visible.
3. **Trust-store distribution — baked vs fetched.** Default: mounted from
   an operator-provided ConfigMap (Helm) or bind mount (compose) —
   neither image-baked (rebuild cadence) nor fetched-at-enrollment (a
   fetch path would need pinning semantics the trust root itself is
   supposed to provide). Bake or fetch later by changing the mount, not
   the daemon.

## One-time staging drill (required before production sign-off)

Mocked tests and the compose e2e cannot prove real nftables, a real WAN
cut, or a model swap under load. The drill checklist lives in
[docs/edge-staging-drill.md](edge-staging-drill.md) — run it once on a
staging gateway before production sign-off, and keep its outputs with
the release notes.

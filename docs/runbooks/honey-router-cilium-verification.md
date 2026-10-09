# Runbook: verifying honey-routing on a kind cluster with Cilium

This is the manual acceptance evidence for spec criterion 6 ("On a cluster
running Cilium, an approved route sends the attacker's flows to the decoy
Service; the generated policy manifest is golden-tested; a kind-cluster
verification is documented"). CI proves the generated manifest is *valid*
(golden test against the vendored Cilium v1.17.3
`CiliumLocalRedirectPolicy` CRD, `tests/unit/integrations/fixtures/`);
only a live cluster proves the policy *redirects*.

**The primitive under test is a candidate by construction.**
`CiliumBackend` emits a `CiliumLocalRedirectPolicy` whose `addressMatcher`
pins flows **destined to the decoy's endpoint address** onto pods labeled
`vigil.io/decoy-id`. LRP matching is destination-based, not
attacker-source-based — this run verifies that the redirect captures the
intended traffic and that the deployment's exposure model (the decoy
endpoint must be node-reachable) holds. What would falsify the primitive:
flows to the decoy endpoint *not* being redirected, or legitimate
non-decoy traffic being caught by the policy.

Everything in steps 1–2 is standard kind/Cilium tooling (from tool docs,
not verified this session); the CRD name and Vigil surfaces in steps 2–8
were verified against this repo and a vendored Cilium v1.17.3 CRD.

## Prerequisites

- `kind`, `kubectl`, `cilium` CLI, and docker, on the workstation.
- Cilium **v1.17.x** — the vendored CRD this feature is validated against
  is `ciliumlocalredirectpolicies.yaml` from cilium v1.17.3. A different
  minor may add or require fields; re-run the golden test against that
  version's CRD before trusting the manifest.
- A running Vigil stack with database access, and the repo checked out
  (the golden fixture and `policy_name_for` come from it).

## 1. Create the cluster and install Cilium

```bash
kind create cluster --name vigil-honey --image kindest/node:v1.31.0
cilium install --version 1.17.3
cilium status --wait   # wait for all agents healthy
```

Confirm the CRD the backend gates on is served:

```bash
kubectl get crd ciliumlocalredirectpolicies.cilium.io
# NAME                                          CREATED AT
# ciliumlocalredirectpolicies.cilium.io         ...
```

The backend's CRD detection (`ApiextensionsV1Api.read_custom_resource_definition`
on exactly this name) must succeed here; on a non-Cilium cluster it
returns 404 and every route fails with `cilium_crd_unavailable` before
anything is applied.

## 2. Deploy one decoy workload and expose it

The decoy is an ordinary workload. A minimal stand-in is enough for the
redirect verification (the real decoy images ship in the compose `decoys`
profile / Helm chart):

```bash
kubectl create namespace vigil-decoys
kubectl -n vigil-decoys create deployment ssh-decoy-01 \
  --image=nginx:alpine
kubectl -n vigil-decoys patch deploy ssh-decoy-01 -p \
  '{"spec":{"template":{"metadata":{"labels":{"vigil.io/decoy-id":"decoy-ssh-01"}}}}}'
kubectl -n vigil-decoys expose deploy ssh-decoy-01 --port 2222 \
  --target-port 80 --name ssh-decoy-01 --type NodePort
kubectl -n vigil-decoys get svc ssh-decoy-01
# note the NodePort and any node IP; this address is the decoy endpoint
```

The decoy endpoint recorded in the registry must be an address the node
sees flows for (NodePort or LoadBalancer) — that is the exposure-model
assumption this run checks.

## 3. Register the decoy in the Vigil registry

`mtd_decoy_registry` rows are routing targets; the deployment above is
what they point at. Using the Vigil database (columns per
`infra/database/init/40_mtd_decoy_registry.sql`):

```sql
INSERT INTO mtd_decoy_registry
    (decoy_id, name, kind, endpoint, status, canary_credential_ref)
VALUES
    ('decoy-ssh-01', 'ssh-decoy-01', 'ssh',
     '<node-ip>:<node-port>', 'active', 'vault:canary/ssh-01');
```

`endpoint` is the node-reachable `host:port` of the exposed decoy
service. Verify with the read-only operator tool (no cluster writes):

```bash
python3 -c "from core.integrations.honey_router.route import list_active_decoys; print(list_active_decoys())"
```

## 4. Enable the honey_router integration

Integration config comes from the descriptor's two fields —
`backend` (default `cilium`) and `namespace` (default `default`). Set
them the way your deployment sets integration config (Settings UI, or the
integrations config file), with `namespace` = `vigil-decoys` from step 2.
Enablement is the `honey-router` entry in `mcp_server_enabled.json` /
the integration-enabled gate — without it, the executor records the
honest `unsupported_action_type` failure instead of routing.

## 5. Route an attacker and observe the policy

Route through the approved path — the daemon's executor on an approved
`honey_route` action, or the operator MCP tool:

```
honey_route(attacker_ip="203.0.113.7", decoy_id="decoy-ssh-01",
            ttl_seconds=3600)
```

A success result carries `{"success": true, "backend": "cilium",
"policy": "vigil-honey-<12-hex>", ...}` — the name is
`vigil-honey-` + the first 12 hex of sha256(attacker_ip) (attacker bytes
never reach an object name). Compute it for any IP:

```bash
python3 -c "from core.integrations.honey_router.route import policy_name_for; print(policy_name_for('203.0.113.7'))"
```

Then observe it on the cluster:

```bash
kubectl -n vigil-decoys get ciliumlocalredirectpolicies -o yaml
```

Diff what you see against the golden fixture (shape, not the name —
the fixture is pinned to the `203.0.113.7` test IP):

```bash
diff <(kubectl -n vigil-decoys get ciliumlocalredirectpolicies \
        -o json | jq '.items[0]') \
     <(jq . tests/unit/integrations/fixtures/golden-lrp-manifest.json)
```

Expected: `apiVersion: cilium.io/v2`, `kind: CiliumLocalRedirectPolicy`,
an `addressMatcher` on the decoy endpoint IP with the decoy port, and a
`redirectBackend` selecting `vigil.io/decoy-id: decoy-ssh-01`.

## 6. Prove the redirect

From a pod on the cluster, connect to the decoy endpoint address; the
connection must land on the decoy pod, and the decoy must record a
session:

```bash
kubectl -n vigil-decoys run probe --rm -it --image=curlimages/curl -- \
  curl -sv http://<node-ip>:<node-port>/ --max-time 5
kubectl -n vigil-decoys logs deploy/ssh-decoy-01 --tail=20
```

Record: the probe output (connection succeeds against the decoy), the
decoy log lines for the session, and the policy YAML from step 5. That
triple is the criterion-6 evidence.

The negative path is evidence too: on a cluster (or namespace) **without**
the CRD, the same call must return
`{"success": false, "error": "cilium_crd_unavailable", ...}` with nothing
created — never a fabricated success, never a half-applied policy.

## 7. Unroute and restore

```
honey_unroute(attacker_ip="203.0.113.7")
```

or let the TTL expire — the daemon's `mtd_route_sweep` runs every 60s and
unroutes expired routes even when MTD is disabled (disabling stops new
routes; it never strands an attacker on a decoy). Either way:

```bash
kubectl -n vigil-decoys get ciliumlocalredirectpolicies
# No resources found
```

The unroute result is recorded on the action (`reversal` in
`execution_result`, with attempts and reason `ttl_expired` or the
operator path); a failed unroute keeps the row eligible and the next
sweep retries.

## 8. Tear down

```bash
kind delete cluster --name vigil-honey
```

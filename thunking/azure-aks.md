# Azure AKS — profile decisions and render evidence

Companion note for [`infra/helm/vigil/values-azure.yaml`](../infra/helm/vigil/values-azure.yaml).
Written against `origin/main` at `0564cd7` (the foundation merge) on branch
`feat/helm-profile-aks`, 2026-10-10. Values-layering rules and the shared
decision log live in [README.md](README.md); chart mechanics in
[chart-anatomy.md](chart-anatomy.md); the touchpoint master table in
[cloud-touchpoints.md](cloud-touchpoints.md).

Every AKS-specific string below carries the spec's verification against Azure
documentation on 2026-10-10 (source map: WEB-STG for storage/LB strings,
WEB-ID for workload identity). Nothing here is shipped from training memory.

## Decisions

### D1 — Storage: pin `managed-csi` at all four PVC sites

The profile pins `storageClassName: managed-csi` at `postgresql.persistence`,
`redis.persistence`, `daemon.persistence`, and `splunk.persistence`, plus
commented Bitnami-subchart equivalents (D2). `managed-csi` (Standard SSD,
Azure Managed Disks via the CSI driver) is pre-created on every AKS cluster
since v1.21 **and is the cluster default** — the profile pins it anyway,
because "empty → cluster default" makes the install follow whatever a future
cluster names as default (EKS, notably, does not default to gp3; the pin is
what keeps the three profiles symmetric).

- Premium SSD (`managed-csi-premium`) appears **only** as the commented
  `redis.persistence.storageClassName` upgrade — redis is the latency-sensitive
  queue. A default that silently bills premium storage is not a default
  (README decision #3). The Bitnami redis variant comment mirrors this.
- Splunk is a dev utility (`splunk.enabled: false`); its pin is inert while
  disabled but still correct — the splunk StatefulSet renders **two**
  volumeClaimTemplates (`var` and `etc`), both honoring the same key
  (templates/splunk-statefulset.yaml lines 74–75 and 85–86).
- Volume expansion works on `managed-csi` (Azure Managed Disks); no
  `volumeMode` override — the API default `Filesystem` is what every
  consumer here wants.

### D2 — Bitnami values-path correction (verified by render, not docs)

The base chart's `values.yaml` documents Bitnami settings under
`postgresql.bitnami.primary.*` / `redis.bitnami.master.*`. Those paths **do
not reach the subcharts**: in `Chart.yaml` both Bitnami dependencies are
*unaliased* (`name: postgresql`, `name: redis`), so each subchart's values
root is the top-level `postgresql:` / `redis:` key, and the `bitnami.` middle
segment is invisible to them. The parent's own helpers read
`postgresql.bitnami.*` for their own resources (service names, env wiring) —
that part works; persistence passthrough does not.

Empirical proof (this branch, helm v3.15.2, Bitnami variant enabled,
`values-azure.yaml` layered):

| Candidate path | Renders into subchart StatefulSets? |
|---|---|
| `--set postgresql.primary.persistence.storageClass=managed-csi --set redis.master.persistence.storageClass=managed-csi` | **Yes** — Bitnami postgres + redis StatefulSets each carry `storageClassName: managed-csi` |
| `--set postgresql.bitnami.primary.persistence.storageClass=managed-csi --set redis.bitnami.master.persistence.storageClass=managed-csi` | **No** — only the parent chart's own daemon pin renders |

So `values-azure.yaml` comments the **unsegmented** paths
(`postgresql.primary.persistence.storageClass`,
`redis.master.persistence.storageClass`) as the Bitnami equivalents. The
finding is structural (it follows from the unaliased dependencies, not from
anything AKS-specific), so the sibling profiles' Bitnami comments must use
the same shape.

### D3 — Exposure: ingress example only; LoadBalancer strings documented, not shipped

Chart default is Ingress-only and disabled. The profile comments an example
using the **Web App Routing add-on**: `ingress.className: webapprouting`
(`az aks approuting enable`). A self-managed nginx (class `nginx`) is the
alternative — nginx is **not** default on AKS, so the profile does not assume
either is present; it stays a commented example either way.

The LoadBalancer Service path (e.g. for SIEM webhook pushes to the daemon)
needs this template work first: **no Service template renders annotations**
(`backend-service.yaml` renders `type` and `port` only), so
`service.beta.kubernetes.io/azure-load-balancer-sku: "standard"` and
`.../azure-load-balancer-internal: "true"` have nowhere to land as values.
Those strings are recorded here for the follow-up that adds a Service
annotations passthrough; the existing
`networkPolicies.daemon.webhookAllowFrom` CIDR hook is the values-side half
of that same use case. The standard SKU is the cluster default on AKS anyway.

`networkPolicies.ingressControllerNamespaceSelector` (chart default
`ingress-nginx`) needs adjusting per exposure choice: `app-routing-system`
for the Web App Routing add-on, `ingress-nginx` for self-managed nginx. Left
to the operator — it depends on which exposure they enable.

### D4 — Workload identity: documented hook, not wired

Azure Workload Identity needs three things; the chart can express less than
one of them values-only, and the locked decision (README #4) is that a values
PR does not silently flip a security default:

1. **Pod label** `azure.workload.identity/use: "true"` — a *label*, not an
   annotation (Azure's webhook matches on pod template labels). The chart
   renders `podLabels` only on the backend Deployment, daemon StatefulSet,
   and enforcer DaemonSet; `llmWorker`, `agentWorker`, and `agentServe` have
   no `podLabels` plumbing, so a label set in values cannot reach every
   Vigil pod. That is a template gap, not a values gap.
2. **SA annotation** `azure.workload.identity/client-id: <id>` — this one
   *is* plumbed (`serviceaccount.yaml` renders
   `.Values.serviceAccount.annotations`); the profile comments it.
3. **Projected SA token** — `serviceAccount.automountServiceAccountToken:
   false` (chart default, deliberate) blocks the token the identity webhook
   mints. Flipping it is a security decision for the operator, same caveat
   as the EKS note's IRSA block.

Cluster prerequisites for whoever wires it: `az aks update --enable-oidc-issuer
--enable-workload-identity` plus a federated credential on a user-assigned
managed identity.

### D5 — ACR pull-through and node scheduling: commented hooks

Docker Hub rate limits are a proven failure mode in this repo (the 2026-10-09
429 incident behind chart vendoring). The optional hook is
`global.imagePullSecrets` → an ACR pull-through cache secret; the profile
comments the shape. Node scheduling comments use the standard AKS pool label
(`kubernetes.azure.com/agentpool`) and the spot taint
(`kubernetes.azure.com/scalesetpriority:spot`) — Ubuntu 22.04 / Azure Linux
nodes carry no kernel-level surprises for anything in this chart (the
enforcer DaemonSet's hostPath/BPF needs are documented in
`services/enforcement/runbook.md` and are node-OS-agnostic on these images).

### D6 — Cilium: the honey-router's hard dependency on AKS

The daemon's honey-router emits `CiliumLocalRedirectPolicy` objects at
runtime and fails honestly when the `cilium.io` CRDs are absent. On AKS the
default network policy is Azure NPM and the default CNI ships **no**
`cilium.io` CRDs — enabling honey-routing requires the Cilium CNI option.
Nothing in this chart installs Cilium; the profile documents the requirement,
and `docs/mtd-enablement.md` remains the runbook.

### D7 — What is portable (no profile keys needed)

Decoy NetworkPolicy containment (default-deny egress; daemon webhook 8081 +
kube-dns 53/TCP+UDP in `kube-system`) is cloud-portable — CoreDNS lives in
`kube-system` on AKS as everywhere else. Policy enforcement semantics (Azure
NPM here) are a cluster property, already handled by documented chart knobs
(`networkPolicies.agentServe.allowProbesFromAnyNamespace`).

## Render evidence (run on this branch, helm v3.15.2, kubeconform v0.6.7)

| Check | Result |
|---|---|
| `helm lint . -f values-azure.yaml` | 1 chart linted, 0 failed |
| `helm lint . -f values-azure.yaml` + Bitnami variant sets | 1 chart linted, 0 failed |
| `helm template` (CI shape: profile + anthropic key only) | 18 resources; `grep -c 'storageClassName: "managed-csi"'` = **3** (postgres `data`, redis `data`, daemon `investigations`; splunk disabled) |
| `helm template` + `--set splunk.enabled=true` (evidence render) | 21 resources; same grep = **5** (adds splunk `var` + `etc` — all four values sites proven) |
| kubeconform `-strict -ignore-missing-schemas -summary` on both renders | 39 resources, Valid 39, Invalid 0, Errors 0 |
| Env-name ratchet (`tests/unit/_ratchets/test_helm_env_names_are_read.py`) | glob discovers `values-azure.yaml`; `test_config_keys_are_read[values-azure.yaml]` passes (profile sets no `config.*`/`extraConfig.*` keys) |
| Unit suite (`tests/unit/ tests/security/ -m "not external_service"`) | with-profile failure set is a strict subset of the clean-`main` baseline (14 vs 18 failures; the 4-test delta is flaky timing-sensitive attestation/replay tests that failed on clean main and passed here); zero new failures |

The storage-pin counts are the semantic evidence schema checks cannot give:
kubeconform sees free-form strings; these greps prove the class names landed
on the four volumeClaimTemplates.

## What this validation does not prove

Everything above is render- and schema-level. No AKS cluster was or could be
used: this repo's CI has no kind cluster and no `ct install`, and none was
added. A green kubeconform does not prove a working install — the first real
`az aks`-cluster deploy remains the operator's step, following the header
prerequisites (CSI driver default-on; Web App Routing/nginx choice; identity
webhook state) and this note.

## Source trail

| Identifier | Source | Used for |
|---|---|---|
| WEB-STG | Azure documentation (learn.microsoft.com), verified 2026-10-10 per the spec's source map: `managed-csi` pre-created and default, `managed-csi-premium`, LB annotation strings | D1, D3 storage/LB strings |
| WEB-ID | Azure Workload Identity documentation, verified 2026-10-10 per the spec's source map: pod **label** `azure.workload.identity/use`, SA annotation `client-id` | D4 |
| R-B §1–§2, §5–§6 | `thunking/cloud-touchpoints.md` master table (adapted from research artifact `art_STBiFZDA`) | PVC template sites, exposure state, RBAC gap, NetworkPolicy portability |
| TREE | This branch at `0564cd7`: `Chart.yaml` (unaliased Bitnami deps), `templates/{serviceaccount,backend-service,splunk-statefulset}.yaml`, base `values.yaml` | D2 render experiment, D3 no-annotation-passthrough, D4 podLabels plumbing gap, D1 splunk dual claims |
| RENDERS | The evidence table above, run 2026-10-10 in this branch's sandbox | All counts |

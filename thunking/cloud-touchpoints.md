# Cloud-provider touchpoints — EKS / AKS / GKE

**Repo:** `jvlatacc/vigil` · **Chart:** `infra/helm/vigil` v0.7.0
(`kubeVersion >=1.25.0-0`, deps pinned in `Chart.lock`: Bitnami `postgresql`
16.2.2, Bitnami `redis` 20.3.0, `opentelemetry-collector` 0.108.0, all vendored
under `charts/` since `39df634`).

**Tree this document describes: `b28bc372`** (first drafted against `c8b4826`,
re-surveyed after the foundation PR rebased onto `b28bc372`). Adapted from the
research artifact _"Research: Vigil cloud-provider touchpoints"_ (read-only
inspection at `f5b3153`, 2026-10-10); the spec re-verified against `5628e17`.
Chart values and templates were unchanged from `5628e17` through `c8b4826` —
verified by diffing. The `c8b4826` → `b28bc372` window landed the **kernel
enforcer DaemonSet** (see §3 and the [README drift log](README.md)) —
re-surveyed from the working tree and folded into this note; everything else
surveyed is unchanged. Facts below were read directly from the working tree;
anything inferred is marked *Inference*.

**Load-bearing premise for the profiles work:** every provider divergence
found below can be absorbed by per-provider **values files**
(`values-aws.yaml`, `values-azure.yaml`, `values-gcp.yaml`, following the
existing `values-dev.yaml` precedent) — *except* items that deliberately ship
as documented hooks, not wired defaults: LoadBalancer exposure (new Service
annotations + type), workload identity (needs template work plus a
security-relevant token-automount flip), and the Cilium LRP honey-router
(needs Cilium CNI on the cluster). Values-only covers storage classes, image
mirrors, scheduling, OTel endpoints, and secret backends.

## Executive summary

1. **The chart is cloud-agnostic today by omission**: zero
   `service.beta.kubernetes.io/*` or `cloud.google.com/*` annotations, zero
   LoadBalancer/NodePort Services, zero cloud-provider references repo-wide.
   External exposure is Ingress-only (`className: nginx`, disabled by
   default), and everything else is ClusterIP.
2. **All four StatefulSets** (postgres 50Gi, redis 5Gi, daemon 10Gi, splunk
   50Gi dev-only) use `storageClassName: ""` → each cloud resolves a
   *different* default storage class (gp3 / managed-csi / standard-rw-family).
   "Empty = default" is portable but non-deterministic across clouds;
   profiles pin explicitly.
3. **The kernel enforcer DaemonSet now exists — opt-in, off by default.**
   The survey at `f5b3153` found none anywhere in the tree; `ed94f2c9`
   (between `c8b4826` and `b28bc372`) landed
   `templates/enforcer-daemonset.yaml` (`enforcer.enabled: false` — not
   rendered unless enabled). It is deliberately the chart's one
   policy-divergent workload: `hostNetwork: true`, dedicated uid 10002,
   kernel capabilities from values (`BPF, NET_ADMIN, PERFMON, SYS_ADMIN`
   added; `ALL` dropped first), and three `hostPath` mounts (`/sys/fs/bpf`,
   cgroup2, `/sys/kernel/btf`) with `type: Directory` so a node missing a
   prerequisite fails at scheduling instead of half-enforcing. Kernel/node-OS
   concerns (COS vs Ubuntu vs AL2/Bottlerocket) therefore bite **only when an
   operator enables it** — §3 and the master-table row carry the per-cloud
   detail.
4. **Image registries are mixed**: Vigil's own images from
   **ghcr.io/vigil-soc** (multi-arch, pushed by `release.yml`), but seven
   support images from **Docker Hub** (`postgres:16-alpine`, `redis:7-alpine`,
   `splunk/splunk:latest`, `dpage/pgadmin4:latest`, `curlimages/curl:8.10.1`,
   `otel/opentelemetry-collector-contrib`, plus Bitnami subchart images). CI
   has already hit **Docker Hub 429 rate limits** (2026-10-09 incident —
   since mitigated for *chart* deps by vendoring, `39df634`) and the compose
   stack lost `minio/minio` ("left Docker Hub" → replaced by `pgsty/minio`).
   Registry churn + rate limits are the strongest argument for per-cloud
   mirror pinning (ECR/ACR/Artifact Registry pull-through caches).
5. **Secrets & identity are cloud-naive today**: static AWS key/secret in the
   chart Secret (`secrets.awsAccessKeyId/awsSecretAccessKey`,
   `config.AWS_REGION: us-east-1`), ServiceAccount has
   `automountServiceAccountToken: false` and **no annotations** (the natural
   IRSA / Workload Identity hook), and there are **no RBAC templates at
   all** — yet the honey-router talks to the K8s API "with the pod's
   in-cluster service account". Enabling MTD rerouting in-cluster needs SA
   token + RBAC + Cilium CRD; each cloud wants a different identity primitive
   (IRSA / AKS Workload Identity / GKE WI Federation).
6. **NetworkPolicy kube-dns assumption is portable**: decoy egress allows DNS
   to namespace `kubernetes.io/metadata.name: kube-system` on 53/TCP+UDP —
   CoreDNS lives in `kube-system` on all three clouds. The real CNI-level
   variance is *egress policy enforcement semantics* and the honey-router's
   hard Cilium dependency.

## Master table: touchpoint → current behavior → per-cloud requirements

Storage-class and LoadBalancer-annotation strings were verified against
current provider documentation on **2026-10-10** [WEB-STG]; workload-identity
strings likewise [WEB-ID]. Where the survey's training-knowledge guesses were
wrong, the corrected string is what appears here (see Adaptation notes).

| Touchpoint | Current chart behavior (evidence) | EKS requires | AKS requires | GKE requires |
|---|---|---|---|---|
| **PostgreSQL PVC** | `values.yaml` `postgresql.persistence`: 50Gi, RWO, `storageClassName: ""` (cluster default), no `volumeMode` → K8s default `Filesystem`; vendored Bitnami path: `postgresql.bitnami.primary.persistence.size: 50Gi` | Pin `gp3` (EBS CSI addon creates it but does **not** mark it default on current EKS releases; EKS Auto Mode uses `auto-ebs-sc`) | Pin `managed-csi` (Standard SSD) — pre-created and is the cluster default; pin it anyway | Pin `standard-rw` (pd-balanced, GKE 1.24+); legacy `standard` (pd-standard) is the older default |
| **Redis PVC** | `redis.persistence`: 5Gi, RWO, `""` | `gp3` — fine for the queue; provisioned-IOPS (io2) tuning is an operator option, not a profile default | `managed-csi`; `managed-csi-premium` documented as the commented latency upgrade | `standard-rw`; `premium-rw` (Hyperdisk Balanced) as the commented latency upgrade |
| **Daemon PVC** | `daemon.persistence`: 10Gi, RWO, `""`, mount `/app/data/investigations` | `gp3` | `managed-csi` | `standard-rw` |
| **Splunk PVC** (dev utility, disabled) | `splunk.persistence`: 50Gi, RWO, `""` | `gp3` | `managed-csi` | `standard-rw` |
| **External exposure** | **No LoadBalancer/NodePort anywhere.** `backend.service.type: ClusterIP` (configurable), daemon/agent-serve/decoys pinned ClusterIP; `ingress.yaml` disabled by default, `className: nginx`, `annotations: {}` passthrough | Ingress class `alb` via AWS Load Balancer Controller + `alb.ingress.kubernetes.io/group.name` group annotations; LB Service (if ever added) needs `service.beta.kubernetes.io/aws-load-balancer-type: "external"` + `...-nlb-target-type: ip` — **not** the older `"external/nlb"` value | Ingress class `webapprouting` (Web App Routing addon) or explicit `nginx` (nginx is not default on AKS); LB annotations `service.beta.kubernetes.io/azure-load-balancer-sku: "standard"` (cluster default anyway), `...-internal: "true"` for internal | Ingress class `gce` (GKE Ingress; Gateway API is the modern alternative, not used here); LB annotation `cloud.google.com/load-balancer-type: "Internal"` or `"External"` |
| **Ingress controller namespace** | `networkPolicies.ingressControllerNamespaceSelector` defaults to `kubernetes.io/metadata.name: ingress-nginx` | Same label works if nginx runs in `ingress-nginx`; ALB controller usually `kube-system`/`aws-load-balancer` | nginx addon runs in `kube-system` or `app-routing-system` | `gce` class has no namespace; nginx as usual |
| **Enforcer DaemonSet (opt-in, `enforcer.enabled`)** | Landed `ed94f2c9` (`templates/enforcer-daemonset.yaml`; **not rendered while disabled** — default renders are unchanged). `hostNetwork: true` + `dnsPolicy: ClusterFirstWithHostNet`, uid 10002 (dedicated, non-root), `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, caps `drop: ALL` then values-listed `add: [BPF, NET_ADMIN, PERFMON, SYS_ADMIN]`, three `hostPath` mounts (`bpffs`, cgroup2, kernel BTF — `type: Directory`), loopback-only API (`bind: "127.0.0.1:6986"`, **no Service by design**), no PDB. Node prerequisites (`services/enforcement/runbook.md`): bpffs at `/sys/fs/bpf`, cgroup2, kernel BTF (kernels ≥5.8); per-primitive status on `/healthz` (BPF LSM interdiction degrades to SIGSTOP suspension when `lsm=bpf` is absent) | AL2023/Ubuntu nodes fine (kernels ≥5.8 ship BTF; CAP_BPF works). **Bottlerocket** needs bpffs/cgroup hostPath allowlisting (survey training knowledge, not re-verified) | Ubuntu 22.04 / Azure Linux nodes fine | **COS**: read-only node rootfs is compatible (`readOnlyRootFilesystem: true` already); **Autopilot rejects hostNetwork/privileged DaemonSets — Standard clusters only** (survey training knowledge, not re-verified) |
| **Cilium LRP honey-router (the actual "enforcement plane")** | `core/integrations/honey_router/route.py` emits `CiliumLocalRedirectPolicy` (`cilium.io/v2`), gated on CRD detection with "honest failures"; `descriptor.py`: talks to K8s API "with the pod's in-cluster service account"; `docs/mtd-enablement.md`: requires Cilium already running, "Vigil does not install Cilium for you" | Cilium as replacement CNI (or via EKS add-on); LRP CRD present | Cilium CNI option (Azure NPM is default); install w/ LRP CRD | GKE Dataplane V2 is Cilium-derived but **does not ship cilium.io CRDs** — needs self-managed Cilium |
| **K8s API access for honey-router** | SA `automountServiceAccountToken: false`, **no RBAC templates**, no LRP `Role`/`ClusterRole` | Add SA token + RBAC; bind to Cilium LRP CRD; IRSA for any AWS API | Same + `azure.workload.identity/use: "true"` SA annotation for Azure APIs | Same + `iam.gke.io/gcp-service-account` SA annotation (WI Federation, GKE metadata server on node pools) |
| **Workload identity (documented hook only)** | `serviceAccount.annotations: {}` exists but unused; `automountServiceAccountToken: false` blocks projected-token injection | SA annotation `eks.amazonaws.com/role-arn`; **verified caveat:** the pod-identity webhook does *not* inject the projected token while `automountServiceAccountToken: false` — the chart default blocks IRSA until an operator flips it | Pod **label** `azure.workload.identity/use: "true"` (not an annotation) + SA annotation `azure.workload.identity/client-id`; same projected-token consideration | SA annotation `iam.gke.io/gcp-service-account`; node pool must run the GKE metadata server (`iam.gke.io/gke-metadata-server-enabled: "true"`) |
| **Vigil images** | `global.imageRegistry: ghcr.io`, `imageNamespace: vigil-soc/vigil` → `ghcr.io/vigil-soc/vigil-{backend,daemon,agent}`; `vigil.image` helper auto-derives; `llmWorker` reuses backend image; `imagePullSecrets: []` | Works as-is (ghcr anonymous); ECR pull-through optional | Works as-is; ACR pull-through optional | Works as-is; Artifact Registry pull-through optional |
| **Support images (Docker Hub)** | `postgres:16-alpine` (StatefulSet + db-init Job), `redis:7-alpine`, `splunk/splunk:latest`, `dpage/pgadmin4:latest`, `curlimages/curl:8.10.1` (helm test), `otel/opentelemetry-collector-contrib`; Bitnami subchart images (docker.io/bitnami/*) | CI already 429'd on Docker Hub (helm-chart.yml comment, 2026-10-09; chart deps since vendored). Pin mirrors / ECR pull-through; also pin `splunk/*` + `pgadmin4` `latest` tags | Same | Same |
| **Registry churn evidence** | `ci-cd.yml`: "minio/minio left Docker Hub; this tag is a community build" → `pgsty/minio:RELEASE.2026-08-04...` | Profiles should pin immutable tags + per-cloud mirrors | Same | Same |
| **Secrets** | `secret.yaml` plain values (`postgresPassword: change-me-before-production`, anthropic key, etc.) or `secrets.existingSecret`; **ExternalSecrets Operator** support (`secrets.externalSecret`, ClusterSecretStore, refreshInterval 1h) named for "AWS SM, Vault, etc."; static `awsAccessKeyId/awsSecretAccessKey` keys; `caBundle` for TLS-inspecting proxies | ESO + AWS Secrets Manager/Parameter Store via IRSA; retire static AWS keys | ESO + Key Vault; Workload Identity | ESO + Secret Manager |
| **OTel endpoints** | `config.OTEL_EXPORTER_OTLP_ENDPOINT` default `http://otel-collector:4317`; `otelCollector.enabled: false`; when enabled, chart rewrites endpoint to in-cluster collector; default pipeline = `debug` exporter (stdout only) | Export to X-Ray/ADOT or vendor backends via collector config | Export to App Insights / Azure Monitor | Export to Cloud Trace/Monitoring |
| **NetworkPolicy / DNS** | `networkpolicy.yaml` off by default; base policy allows all egress; **decoys**: default-deny egress, exactly two allows — daemon webhook 8081 (podSelector) + DNS to `namespaceSelector: kubernetes.io/metadata.name: kube-system` 53/TCP+UDP; kubelet-probe caveat documented (`agentServe.allowProbesFromAnyNamespace: true`) | CoreDNS in `kube-system` ✓; egress policy needs VPC CNI policy engine (or Cilium/Calico) | CoreDNS in `kube-system` ✓; Azure NPM or Cilium enforces | CoreDNS in `kube-system` ✓ (Cloud DNS optional); Dataplane V2 enforces natively |
| **Scheduling (nodeSelector/taints/tolerations/affinity)** | Empty per component (`nodeSelector: {}`, `tolerations: []`, `affinity: {}`) — plumbed through on backend, daemon, llmWorker, agentWorker, agentServe, both decoys | Managed node groups: tainted GPU/spot pools; profiles can pin `karpenter.sh`-style constraints | Agent pool labels `agentpool:`; spot taints `kubernetes.azure.com/scalesetpriority:spot` | Node pool labels `cloud.google.com/gke-nodepool`; Autopilot tolerations injected automatically |
| **State directory** | `stateDirectory.volume: emptyDir` (per-pod, cleared on restart) with documented ReadWriteMany tradeoff | RWX = EFS (needs EFS CSI + IRSA) | RWX = Azure Files (CSI built-in) | RWX = Filestore (`standard-rwx` SC, Filestore CSI) |
| **Backup / object storage** | No k8s backup resources; restic+pg_dump tested in CI against MinIO S3 (`ci-cd.yml`) | Native S3 via restic IRSA | Blob via restic azure plugin | GCS via restic gs plugin |
| **Scaling** | HPA (classic CPU) or KEDA ScaledObject on Redis queue depth (`keda.enabled: false`, external operator) | IRSA for KEDA→AWS APIs if cloud scalers used | Workload Identity for KEDA→Azure | WI Federation for KEDA→GCP |

## Section notes (file-level evidence)

### 1. Persistence

`storageClassName` is templated conditionally in all four StatefulSets
(`postgres-statefulset.yaml`, `redis-statefulset.yaml`,
`daemon-statefulset.yaml`, `splunk-statefulset.yaml`):
`{{- if .Values...storageClassName }} storageClassName: {{ ... | quote }} {{- end }}`
— an empty value **omits the field**, deferring to the cluster default. No
template sets `volumeMode`, so PVCs get the API default `Filesystem` (block
devices are not used anywhere). `accessModes` are configurable but default
`[ReadWriteOnce]`. The `stateDirectory` comment in `values.yaml` explicitly
records the ReadWriteMany constraint ("a ReadWriteOnce disk cannot be shared
by backend.replicaCount > 1, and ReadWriteMany is not available on every
cluster") — the EFS/Azure Files/Filestore mapping per cloud belongs in the
profiles doc, not a chart change.

### 2. Services & Ingress

Every Service in `templates/` is `ClusterIP`; `backend-service.yaml` and
`daemon-service.yaml` render `.service.type` from values (default ClusterIP),
while `agent-serve-service.yaml` and `decoy-services.yaml` are **pinned**
ClusterIP with comments explaining why (bearer-token + NetworkPolicy internal
surface; decoys "nothing exposes them outside the cluster"). The only
`NodePort` match in the chart is a comment saying "no NodePort". The sole
external-exposure surface is `ingress.yaml` (disabled by default,
`className: nginx` default, `annotations: {}` passthrough, single host/path,
optional TLS). Consequence: there are **no existing LB annotation patterns to
fork** — profiles must introduce them if a LoadBalancer path is wanted (e.g.,
for SIEM→daemon webhook pushes from outside the cluster; note
`networkPolicies.daemon.webhookAllowFrom` already exists as the CIDR hook for
exactly that).

### 3. Enforcement plane (DaemonSet question — answered twice: "no" at survey, "yes, opt-in" today)

The brief asked about "Enforcer DaemonSet: fake-kernel / eBPF or hostPath /
privileged assumptions". **At the survey tree (`f5b3153`, still true through
`c8b4826`) none of this existed**: a repo-wide grep for
`enforcer|fake-kernel|DaemonSet` (all files, excluding
`.git/`/`venv/`/`node_modules/`) returned zero hits; `services/` contained
only `agent, api, daemon, decoy, medic, worker`; `infra/docker/` had only
Dockerfiles `agent, backend, daemon, medic`; no compose service was
privileged, and no template mounted hostPath. What existed as enforcement
then — and still does — is:

- **Honey-router (MTD plane)**: daemon runtime-emits
  `CiliumLocalRedirectPolicy` objects; `route.py` names the CRD
  (`ciliumlocalredirectpolicies.cilium.io`), checks for it, and fails honestly
  when absent. `docs/mtd-enablement.md` prerequisites: "Cilium CNI already
  running on the cluster, with the `CiliumLocalRedirectPolicy` CRD available.
  Vigil does not install Cilium for you." The verification runbook
  (`docs/runbooks/honey-router-cilium-verification.md`) uses kind v1.31 +
  Cilium 1.17.3 and records the exposure-model constraint that "the decoy
  endpoint must be node-reachable".
- **Containment breaker** (`core/response/breaker.py`, `breaker_router.py`):
  approval-gated response logic, pure application code, no kernel assumptions.

**Update (`ed94f2c9`, now in this tree): the enforcer DaemonSet landed.**
`templates/enforcer-daemonset.yaml` + the `enforcer:` values block +
`services/enforcement/` (Go daemon + BPF objects) + `Dockerfile.enforcer` +
`.github/workflows/enforcement.yml`. What the template actually grants — read
from the file this session:

- **Off by default**: `enforcer.enabled: false`; the DaemonSet is not
  rendered unless enabled, so every render variant and the cloud profiles'
  default path are unchanged.
- **hostNetwork: true** with `dnsPolicy: ClusterFirstWithHostNet` — XDP must
  attach to the node's NIC. Not a value (comment: an enforcer without
  hostNetwork "would attach to nothing").
- **Identity**: dedicated uid/gid 10002 (not Vigil's 1000, not Medic's
  10001), non-root, `RuntimeDefault` seccomp; container-level
  `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, caps
  `drop: ALL` then `add` from `enforcer.capabilities` (`BPF, NET_ADMIN,
  PERFMON, SYS_ADMIN` defaults, trimmable per site).
- **Host filesystems**: `hostPath` mounts for bpffs (`/sys/fs/bpf`, not
  read-only — pinning writes through it), cgroup2 (`enforcer.cgroup`,
  read-only), and kernel BTF (`/sys/kernel/btf`, read-only), all
  `type: Directory` so a node missing a prerequisite fails at scheduling
  instead of half-enforcing.
- **No Service on purpose**: the API binds `127.0.0.1:6986` (node-loopback)
  and authenticates with `VIGIL_ENFORCEMENT_TOKEN` from the chart Secret
  (`secrets.enforcementToken`). `services/enforcement/runbook.md` node
  prerequisites: bpffs, cgroup2, kernel BTF (kernels ≥5.8 are the supported
  range); `/healthz` reports per-primitive status, and BPF LSM process
  interdiction degrades to SIGSTOP suspension when `lsm=bpf` is absent.

Per-cloud consequence: for the **default profile path** the only thing that
"behaves differently on managed node groups" is still the **CNI choice**
(EKS default VPC CNI + policy engine, AKS default Azure NPM, GKE Dataplane
V2) — none of which ship the `cilium.io` LRP CRD except self-managed Cilium.
**When an operator enables the enforcer**, the node-OS matrix bites: EKS
AL2023/Ubuntu nodes work as-is while Bottlerocket needs bpffs/cgroup hostPath
allowlisting; AKS Ubuntu 22.04/Azure Linux nodes work as-is; GKE COS nodes
need the BPF/BTF prerequisites present and **Autopilot must be excluded**
(hostNetwork + privileged DaemonSets are rejected there — survey training
knowledge for the Autopilot/Bottlerocket specifics, not re-verified against
provider docs this session). Per-cloud notes for this belong in each
`values-<cloud>.yaml` header comment when profiles land.

### 4. Images & registries

- Vigil-owned: `ghcr.io/vigil-soc/vigil-backend|daemon|agent|enforcer` —
  built & pushed by `release.yml` (multi-arch, `packages: write`, canonical
  repo only; the `-enforcer` Go/eBPF image arrived with `ed94f2c9` via
  `Dockerfile.enforcer`); pulled via `global.imageRegistry`/
  `global.imageNamespace` with per-component `image.repository` override and
  the `vigil.image` helper (llmWorker reuses the backend image;
  agentWorker/agentServe share the agent image and differ by command).
- Docker Hub (direct in-chart): `postgres:16-alpine` ×2 (StatefulSet +
  db-init Job), `redis:7-alpine`, `splunk/splunk:latest`, `dpage/pgadmin4:latest`,
  `curlimages/curl:8.10.1`, `otel/opentelemetry-collector-contrib` (repository
  set explicitly because the upstream chart requires it).
- Vendored subcharts (Bitnami pg 16.2.2 / redis 20.3.0, OTel 0.108.0,
  SHA-verified via `SHA256SUMS`) bring their own image defaults
  (docker.io/bitnami/* — upstream chart defaults; *Inference:* not verified
  against extracted sources this session, since CI extracts at build time).
- Evidence that this hurts: `helm-chart.yml` carried a 2026-10-09 postmortem
  comment — anonymous Docker Hub pulls 429'd `helm dependency update`
  repo-wide, wrapped in 5-step exponential backoff — until vendoring
  (`39df634`) removed chart fetching entirely. `ci-cd.yml` documents
  `minio/minio` leaving Docker Hub and substituting `pgsty/minio`.
- **Consequence for profiles:** (a) document per-cloud pull-through caches
  (ECR/ACR/Artifact Registry) via `global.imageRegistry` +
  `global.imagePullSecrets`; (b) the two `latest`-tag dev images (splunk,
  pgadmin) are a flagged follow-up for the base chart, not pinned in profiles.

### 5. Secrets, OTel, NetworkPolicy/DNS, scheduling, resources

- **Secrets**: plain `secret.yaml` with ~30 keys (skipped when
  `secrets.existingSecret` set); ExternalSecrets Operator path
  (`externalsecret.yaml`, `data`/`dataFrom`, ClusterSecretStore default) is
  already provider-agnostic. Cloud-specific work is only the *store backend*
  wiring. Static `awsAccessKeyId/awsSecretAccessKey` exist for AWS
  integrations; `config.AWS_REGION: us-east-1` is the only region default in
  the chart. `caBundle` support anticipates TLS-inspecting proxies (common in
  enterprise AKS/EKS egress setups).
- **OTel**: collector subchart optional (`mode: deployment`, 1 replica, debug
  exporter); `OTEL_EXPORTER_OTLP_ENDPOINT` default is the in-cluster name;
  app-level `VIGIL_OTEL_ENABLED: "false"` gates emission. Daemon also exposes
  native Prometheus `/metrics` on 9090 with an optional ServiceMonitor (CRD
  from kube-prometheus-stack). Per-cloud exporter config is a values-file
  edit, no template change.
- **NetworkPolicy/DNS**: the decoy containment contract (default-deny egress,
  daemon 8081 + kube-dns 53 TCP/UDP in `kube-system`) is portable across all
  three clouds (CoreDNS location and ports are the same). Two CNI-variant
  caveats are already documented in-chart: kubelet-probe admission differs by
  CNI (`allowProbesFromAnyNamespace`, Calico/Cilium permit node-sourced
  checks), and policy *enforcement* semantics differ (EKS VPC CNI needs its
  policy engine enabled; AKS default is Azure NPM; GKE Dataplane V2 enforces
  natively). `webhookAllowFrom` CIDRs are where external SIEM webhooks get
  punched through.
- **Scheduling & resources**: every component exposes empty
  `nodeSelector/tolerations/affinity`; resource requests are already sized
  generously (backend 250m/512Mi→1c/1Gi; daemon 500m/1Gi→2c/4Gi; postgres
  250m/512Mi→2c/4Gi). Profiles only need to append cloud node-pool
  labels/taints — no template changes.

### 6. Existing cloud references repo-wide (negative-ish result)

- **No `terraform/`, no eksctl/gcloud/az manifests, no per-env cloud values
  beyond `values-dev.yaml`** (dev-only overrides: DEV_MODE, small resources,
  1–5Gi PVCs, dev password).
- Grep for
  `eks|aks|gke|aws-load-balancer|azure-load-balancer|cloud.google|IRSA|workload.?identity`
  across yaml/md/sh/tf/py: the only substantive hits are the
  `storageClassName` templates; everything else was substring noise
  ("breaks", "speaks", "leaks").
- AWS-adjacent items that do exist: `env.example`
  `AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_REGION`; `values.yaml`
  `secrets.aws*` + `config.AWS_REGION`; `core/memory/entity_keys.py` notes
  AWS key/ARN case-significance (app-level, not deployment); `ci-cd.yml`
  restic→S3/MinIO backup tests; ExternalSecrets docstring naming "AWS SM,
  Vault". Nothing Azure- or GCP-specific anywhere.

## Profile shape (decision recorded)

The recommended-shape analysis that lived here moved into the
[README decision log](README.md#decision-log) when the values-profiles
decision was locked. Summary: follow the `values-dev.yaml` precedent with
`values-aws.yaml`, `values-azure.yaml`, `values-gke`… — pin the four PVC
storage classes, comment out (don't set) exposure/identity/pull-through/
scheduling examples, never touch `dbInit.*`/`secrets.*`/new `config.*` keys.
One scaffolding note kept from the research: RBAC + SA-token templates for
the honey-router (currently a latent gap: it needs the K8s API but the chart
ships `automountServiceAccountToken: false` and no Role/RoleBinding) are
**provider-independent** and belong in the base chart behind a documented
flag — a flagged follow-up, not part of any profile PR.

## Adaptation notes

- **Source:** artifact _"Research: Vigil cloud-provider touchpoints"_
  (survey at `f5b3153`, 2026-10-10). Re-verified against the working tree at
  `c8b4826`: the storageClassName conditional templating, ClusterIP-only
  Services, disabled ingress, empty scheduling knobs, and `automountServiceAccountToken: false`
  all re-read and confirmed; no chart-value drift since the survey (only the
  vendoring + docs commits — see [chart-anatomy.md](chart-anatomy.md) §11).
- **Correction carried from the spec's provider-doc verification
  (2026-10-10):** the survey's EKS LoadBalancer annotation row said
  `aws-load-balancer-type: external/nlb`; the spec's WEB-STG check corrected
  it to `service.beta.kubernetes.io/aws-load-balancer-type: "external"` +
  `...-nlb-target-type: ip` — the older `"external/nlb"` value is not the
  current form. The master table carries the corrected string.
- **Storage-class strings** in the master table carry the spec's WEB-STG
  verified forms: `gp3` (EBS CSI addon non-default on current releases; Auto
  Mode `auto-ebs-sc`), `managed-csi` (pre-created cluster default on AKS),
  `standard-rw` (GKE 1.24+; legacy `standard` for older clusters).
- **Identity strings** carry WEB-ID verified forms: EKS
  `eks.amazonaws.com/role-arn` (with the projected-token vs
  `automountServiceAccountToken: false` caveat cross-checked against the
  chart's base values), Azure pod-label `azure.workload.identity/use: "true"`
  + SA annotation `azure.workload.identity/client-id`, GKE
  `iam.gke.io/gcp-service-account` + node-pool metadata server.
- **Facts vs inference:** file-level evidence quotes (§1–§6) were read from
  the tree; the per-cloud *requirements* cells combine those facts with
  provider documentation verified 2026-10-10 [WEB-STG, WEB-ID]. Anything
  neither read nor verified is marked *Inference* (two instances: Bitnami
  subchart image registry defaults; the Bottlerocket hostPath-allowlist and
  Autopilot hostNetwork-rejection specifics for the enforcer, carried from
  the survey's training-knowledge tier).
- **Re-survey (`c8b4826` → `b28bc372`):** the enforcer DaemonSet landed
  (`ed94f2c9`) after this note's first draft; §3, the executive summary, the
  master-table enforcer row, and the Vigil-images bullet were re-read from
  the working tree at `b28bc372` and updated in place. The survey-era
  "does not exist" statements are preserved above with their tree labels
  rather than erased — they document what the research saw when it saw it.
- **Provider-doc trail:** the spec's source map records WEB-STG/WEB-ID as
  provider documentation verified 2026-10-10 (AWS EBS CSI/EKS docs, Azure
  learn.microsoft.com, Google cloud.google.com GKE docs, AWS IRSA docs,
  Azure Workload Identity docs, GKE WI Federation docs). Those verification
  reads happened in the spec session; this adaptation carries their
  conclusions with that date attached rather than re-deriving them.

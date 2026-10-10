# GKE profile — decisions and render evidence (`values-gcp.yaml`)

Provider note for the Google Kubernetes Engine profile. It states what the
profile pins and why, what it deliberately leaves as commented hooks, and the
render evidence backing the pins. Nothing here executes at install time —
this is a decision record, not a runbook.

**Tree state this note describes:** branch `feat/helm-profile-gke`, based on
`0564cd7` (foundation merge: `thunking/` seeds + profile-aware CI discovery).
The foundation's [README](README.md) owns the layering model, the decision
log, and the `helm dependency build` / Chart.lock pre-flight (R1); this note
references those findings rather than restating them, and re-ran the
dependency build once on the current tree (below).

## What the profile pins

All four PVC-bearing StatefulSets pin `storageClassName: standard-rw`
(pd-balanced, the GKE 1.24+ default class family). Sites and locators:

| PVC site | Key | Base (values.yaml) | Pin | Source locator |
|---|---|---|---|---|
| PostgreSQL | `postgresql.persistence.storageClassName` | `""` (cluster default), 50Gi | `standard-rw` | values.yaml `postgresql.persistence`; [cloud-touchpoints.md](cloud-touchpoints.md) master table, PostgreSQL row |
| Redis | `redis.persistence.storageClassName` | `""`, 5Gi | `standard-rw` | values.yaml `redis.persistence`; master table, Redis row |
| Daemon | `daemon.persistence.storageClassName` | `""`, 10Gi | `standard-rw` | values.yaml `daemon.persistence`; master table, Daemon row |
| Splunk | `splunk.persistence.storageClassName` | `""`, 50Gi | `standard-rw` | values.yaml `splunk.persistence`; master table, Splunk row (dev utility — inert while `splunk.enabled: false`) |

Why pin at all — *Fact:* the base chart omits the field when the value is
empty (conditional template in all four StatefulSets), deferring to whatever
the cluster resolves as its default StorageClass. *Fact* (provider side,
spec WEB-STG verified 2026-10-10): GKE 1.24+ ships `standard-rw`
(pd-balanced); the legacy `standard` class (pd-standard) is the older
default. Pinning makes storage explicit instead of inheriting a
per-cluster-version resolution — same rationale as the EKS/AKS profiles.

**Legacy `standard` (pd-standard) distinction.** On clusters older than 1.24
— and on clusters where an operator renamed classes — `standard` means
pd-standard (spinning-tier HDD-backed), not pd-balanced. This profile is
written for 1.24+ clusters (the chart itself requires `kubeVersion
>=1.25.0-0`); if you reuse it on a legacy cluster, decide deliberately
whether `standard` there is the class you want, or override to `standard-rw`
if one exists. *Inference note:* whether `standard-rw` exists on a given
legacy cluster depends on GKE version and cluster config — verify with
`kubectl get storageclass` before relying on it.

**Redis premium upgrade — commented, never a default.** Redis is the
latency-sensitive case (queues + dedup state). `premium-rw` (Hyperdisk
Balanced) is documented as the commented upgrade in the profile. Decision 3
in the [README decision log](README.md#decision-log): a default that
silently bills premium storage is not a default.

## Bitnami subchart equivalents — and a passthrough correction

The profile comments the Bitnami-variant equivalents. **Correction found by
render probe (2026-10-10, this tree):** the value paths nested under
`postgresql.bitnami.*` / `redis.bitnami.*` in the chart's `values.yaml` do
**not** reach the vendored subcharts, despite the values.yaml comment saying
"all Bitnami values below are passed through to the subchart". The working
paths are the subchart-native ones:

| Variant | Working key | Probe result |
|---|---|---|
| Bitnami postgresql | `postgresql.primary.persistence.storageClass` | renders in the subchart StatefulSet's `data` PVC template |
| Bitnami postgresql (chart's nested form) | `postgresql.bitnami.primary.persistence.storageClass` | **no-op — 0 rendered pins** |
| Bitnami redis | `redis.master.persistence.storageClass` | renders in the subchart's master PVC |
| Bitnami redis (chart's nested form) | `redis.bitnami.master.persistence.storageClass` | **no-op — 0 rendered pins** |

*Why (mechanism, read from `Chart.yaml`):* the postgresql/redis dependencies
carry **no `alias:`**, so each subchart's values namespace is the parent's
top-level `postgresql:` / `redis:` key. Anything nested deeper under
`postgresql.bitnami.*` arrives at the subchart as an unknown `bitnami:` key,
which Bitnami ignores. (The `import-values` on the postgresql dependency
flows child→parent — it exports resolved auth state up to the parent; it
does not push `bitnami.*` down.)

Probe commands (helm v3.16.4, vendored charts extracted):

```bash
helm template rel infra/helm/vigil \
  --set secrets.anthropicApiKey=test-key \
  --set postgresql.enabled=false --set postgresql.bitnami.enabled=true \
  --set redis.enabled=false --set redis.bitnami.enabled=true \
  --set postgresql.bitnami.primary.persistence.storageClass=probe-a
# → 0 occurrences of storageClassName (no-op)
helm template rel infra/helm/vigil \
  --set secrets.anthropicApiKey=test-key \
  --set postgresql.enabled=false --set postgresql.bitnami.enabled=true \
  --set redis.enabled=false --set redis.bitnami.enabled=true \
  --set postgresql.primary.persistence.storageClass=probe-b
# → 1 occurrence: storageClassName: probe-b in the Bitnami postgresql PVC
# (redis probed identically: master path renders, bitnami.master path no-ops)
```

**Consequences:**

- This profile's commented equivalents use the subchart-native paths above.
- The chart's values.yaml comment and `postgresql.bitnami.primary.persistence.size` /
  `redis.bitnami.master.persistence.size` defaults are affected by the same
  finding — flagging for the chart owners as a follow-up. **Not fixed in this
  PR** (pure file addition by design; fixing the nesting is a chart change).

## Exposure (documented hook)

Chart default: no LoadBalancer Services anywhere; `ingress.yaml` disabled
with `className: nginx` (master-table evidence in
[cloud-touchpoints.md](cloud-touchpoints.md)). The profile ships a commented
`gce`-class example:

- `ingress.className: gce` — GKE Ingress, created by GKE's managed
  ingress-gce controller (spec WEB-STG verified 2026-10-10). Gateway API is
  the modern alternative and is deliberately not used here.
- `cloud.google.com/load-balancer-type: "Internal"` (or `"External"`) — the
  GKE Ingress annotation controlling LB reachability (spec WEB-STG verified
  2026-10-10).
- *Training knowledge, verify on your cluster:* the `gce` class has no
  controller namespace the way self-hosted nginx does; if you enable
  `networkPolicies` alongside, align
  `networkPolicies.ingressControllerNamespaceSelector` with where your
  controller actually runs (the profile comments the `kube-system` selector
  as a starting point). Semantic mistakes here are exactly the kind schema
  checks cannot catch — see "What validation does not prove".
- If exposure ever needs a bare LoadBalancer Service (e.g. SIEM webhook
  pushes to the daemon), the documented annotation is
  `cloud.google.com/load-balancer-type` — but the chart has no LB Service
  template to annotate today; `networkPolicies.daemon.webhookAllowFrom` is
  the existing CIDR hook for that flow.

## Workload Identity (documented hook, not wired)

GKE Workload Identity Federation is the per-cloud identity primitive
([cloud-touchpoints.md](cloud-touchpoints.md) master table; strings spec
WEB-ID verified 2026-10-10):

- ServiceAccount annotation `iam.gke.io/gcp-service-account` (the profile
  comments an example value in the `<GSA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com`
  form — *training knowledge* for the value shape; the annotation key is the
  spec-verified string).
- Node pools must run the GKE metadata server: node label
  `iam.gke.io/gke-metadata-server-enabled: "true"` (spec WEB-ID verified).
- **Caveat, cross-checked against the chart's base values (Fact):** the chart
  ships `automountServiceAccountToken: false`
  (values.yaml `serviceAccount` block). The projected/KSA token is what the
  GKE metadata server flow authenticates with — while the automount is off,
  identity wiring stays inert (same shape as the IRSA caveat recorded for
  EKS in [thunking/aws-eks.md](aws-eks.md)). Flipping it is a security decision for the
  operator; this profile documents the hook and does not flip it (decision 4
  in the README decision log; the identity-template work is flagged follow-up
  R8 in the spec).

## Images: Artifact Registry pull-through (documented hook)

*Fact:* Vigil's own images come from `ghcr.io/vigil-soc` and pull
anonymously; support images come from Docker Hub, and this repo's CI has
already been rate-limited by anonymous Docker Hub pulls (the 2026-10-09 429
incident recorded in `helm-chart.yml` and the foundation's README). The
profile comments the Artifact Registry override shape:

- `global.imageRegistry: <REGION>-docker.pkg.dev` +
  `global.imageNamespace: <PROJECT_ID>/<REPO>/vigil` — *Fact (helper
  mechanism):* the `vigil.image` helper concats
  `<registry>/<namespace>-<component>` (templates/_helpers.tpl), so the
  namespace carries the AR project/repo path segments and images resolve to
  `<REGION>-docker.pkg.dev/<PROJECT_ID>/<REPO>/vigil-backend` etc.
- `global.imagePullSecrets` — for key-based AR auth only; node or Workload
  Identity access needs none.
- This is optional hygiene, not a requirement — decision 4 (documented hook,
  not wired default).

## Node scheduling, COS, Autopilot (background constraints)

- Scheduling knobs (`nodeSelector`/`tolerations`/`affinity`) are empty per
  component and plumbed through on every workload; the profile comments one
  `cloud.google.com/gke-nodepool` pin as the example (master table,
  Scheduling row).
- **COS nodes** (GKE default): read-only rootfs, no package manager —
  standard assumptions hold for the chart today because nothing mounts
  hostPath, runs privileged, or needs node tooling. Becomes load-bearing the
  day a node-level enforcer is added (spec's node-OS matrix).
- **Autopilot:** rejects privileged/hostPath workloads outright (spec WEB-STG
  era verification; specifics carried as *inference* in the touchpoints
  note's adaptation notes). Consequence for this chart: the opt-in enforcer
  DaemonSet (`enforcer.enabled`, landed after the original survey — see the
  README's drift log) cannot run on Autopilot, and self-managed Cilium is
  not installable there. Use Standard mode clusters for enforcement/MTD
  features; the profile header says the same.

## Cilium / Dataplane V2 (the enforcement plane on GKE)

*Fact (chart side):* the honey-router emits `CiliumLocalRedirectPolicy`
objects at runtime and fails honestly when the CRD is absent; "Vigil does
not install Cilium for you" (`docs/mtd-enablement.md`).
*Fact (provider side):* GKE Dataplane V2 is Cilium-derived but ships no
`cilium.io` CRDs. So on a Dataplane V2 cluster the honey-router's LRP path
fails honestly — MTD rerouting needs self-managed Cilium, which in turn
needs a Standard-mode cluster (not Autopilot). Networks that don't run
Cilium keep every other Vigil feature; only the LRP plane is gated.

## Render evidence

Commands run against this branch (vendored subcharts extracted per the CI
workflow's steps; helm **v3.16.4** locally — CI pins **v3.15.2**;
kubeconform **v0.6.7**, matching CI):

```bash
# 1. Lint with the profile layered on defaults
helm lint infra/helm/vigil -f infra/helm/vigil/values-gcp.yaml
# → 1 chart(s) linted, 0 chart(s) failed

# 2. Render, CI-equivalent (profile + required key; splunk stays disabled)
helm template release-check infra/helm/vigil \
  -f infra/helm/vigil/values-gcp.yaml \
  --set secrets.anthropicApiKey=test-key > /tmp/manifest-values-gcp.yaml
# → 18 resources; 3 × storageClassName pins (postgres, redis, daemon;
#   splunk's StatefulSet does not render while disabled — inert by design)

# 3. Render with splunk enabled to show all four PVC sites
helm template release-check infra/helm/vigil \
  -f infra/helm/vigil/values-gcp.yaml \
  --set secrets.anthropicApiKey=test-key --set splunk.enabled=true \
  > /tmp/manifest-values-gcp-splunk.yaml
# → 21 resources; 5 × storageClassName pins, attributed:
#   release-check-vigil-daemon, -postgres, -redis, -splunk (two PVC templates)

# 4. kubeconform strict on both renders
kubeconform -strict -ignore-missing-schemas -summary /tmp/manifest-values-gcp.yaml
# → 18 resources — Valid: 18, Invalid: 0, Errors: 0, Skipped: 0
kubeconform -strict -ignore-missing-schemas -summary /tmp/manifest-values-gcp-splunk.yaml
# → 21 resources — Valid: 21, Invalid: 0, Errors: 0, Skipped: 0
```

Counting note: templates render the value **quoted** (`storageClassName:
"standard-rw"`, via the `| quote` pipeline), so the grep pattern for evidence
counts is the quoted form. With splunk disabled the CI-equivalent render
shows 3 pins; with splunk enabled, 5 (splunk contributes two PVC templates).
Either way every rendered PVC carries the pin — zero PVCs left on the
cluster-default resolution.

`helm dependency build` re-run on this tree (throwaway copy, both repos
registered, helm v3.16.4): exit 0, all three pinned subcharts re-downloaded,
`Chart.lock` byte-identical before/after (sha256), and the downloaded tgz
digests match `SHA256SUMS` — independently reproduces the foundation's R1
finding on `0564cd7`. Do not reintroduce a dependency-build step into CI (429
hazard — see the foundation README).

Ratchet evidence: `pytest tests/unit/_ratchets/test_helm_env_names_are_read.py
tests/unit/_ratchets/test_helm_db_init_sql_files.py` → **13 passed**, with
the env-name ratchet's parametrize discovering `values-gcp.yaml` via the
glob (`test_config_keys_are_read[values-gcp.yaml]` in the call log) — no
test edit was needed, which is exactly the foundation's D3 contract.

## What validation does and does not prove

Same boundary as the foundation README, restated for this cloud: all
validation above is **render- and schema-level**. Nothing in this work
installed into a real GKE cluster; there is no kind cluster and no
`ct install` in CI. kubeconform cannot catch semantic mistakes (a wrong
class name for your cluster's version, a mis-picked controller namespace,
a metadata-server label left unset) — the pins are documented here so the
first real deploy is a checklist, not an archaeology dig.

## Source trail

**Retrieved this session (files read/probed on the repo sandbox, branch
`feat/helm-profile-gke` @ base `0564cd7`):** `Chart.yaml` (no alias on
postgresql/redis; import-values direction), `values.yaml` (four PVC sites,
`serviceAccount`, `ingress`, `global`, `networkPolicies`, `splunk` blocks),
`values-dev.yaml`, `templates/_helpers.tpl` (`vigil.image` concat rule),
`.github/workflows/helm-chart.yml` (discovery loop, vendoring/extract steps,
kubeconform flags), `thunking/README.md` + `thunking/cloud-touchpoints.md`
(layering rules, decision log, R1 finding, master table), all Bitnami
passthrough probes, lint/render/kubeconform runs, ratchet test run.

**Spec-verified provider strings (WEB-STG / WEB-ID, verified 2026-10-10 in
the spec session — carried with that date, not re-derived here):**
`standard-rw` (pd-balanced, GKE 1.24+) and the legacy `standard`
(pd-standard) default; `premium-rw` (Hyperdisk Balanced); ingress class
`gce`; `cloud.google.com/load-balancer-type: "Internal"|"External"`; SA
annotation `iam.gke.io/gcp-service-account`; node label
`iam.gke.io/gke-metadata-server-enabled: "true"`; Autopilot
privileged/hostPath rejection; COS read-only rootfs.

**Training knowledge (labeled, not re-verified this session):** the
`<GSA>@<PROJECT>.iam.gserviceaccount.com` annotation value shape and the
`roles/iam.workloadIdentityUser` binding prerequisite; `standard-rw` being
pre-created on 1.24+ clusters; ingress-gce running in `kube-system`; the
metadata-server/automount interaction detail (the automount caveat itself
is Fact, cross-checked against the chart's base values).

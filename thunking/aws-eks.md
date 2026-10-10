# EKS — AWS profile decisions and render evidence

**Profile:** [`infra/helm/vigil/values-aws.yaml`](../infra/helm/vigil/values-aws.yaml)
**Branch base:** `origin/main` at `0564cd7` (foundation PR #131 merge commit).
**Validation level:** render- and schema-only. Nothing in this work installs into a
real EKS cluster — no kind cluster, no `ct install` (see
[README → What validation does and does not prove](README.md#what-validation-does-and-does-not-prove)).
The first real deploy is the operator's step.

## What the profile does

Pins one thing actively — `storageClassName: gp3` at all four PVC sites — and
ships everything else cloud-specific as commented hooks: ALB ingress, IRSA
identity, ECR pull-through cache, and node scheduling. Credentials stay
operator-side via `--set` in the header's install invocation. The profile sets
no `dbInit.*`, no `secrets.*`, and no `config.*` keys.

## Storage pins

The base chart leaves all four `storageClassName` keys empty (`""`), which
omits the field and defers to the cluster default. On EKS the default is
**not deterministic**: the EBS CSI add-on creates the `gp3` StorageClass but
does not mark it as the cluster default on current EKS releases, and EKS
Auto Mode clusters provision through `auto-ebs-sc` instead. Empty-string
"portability" silently picks whichever of these the cluster happens to run,
so the profile pins `gp3` (general purpose SSD) explicitly at every site.

| PVC site | Chart locator | Pinned class |
|---|---|---|
| postgresql | `values.yaml` `postgresql.persistence.storageClassName` → `postgres-statefulset.yaml` volumeClaimTemplates | `gp3` |
| redis | `values.yaml` `redis.persistence.storageClassName` → `redis-statefulset.yaml` | `gp3` |
| daemon (investigations) | `values.yaml` `daemon.persistence.storageClassName` → `daemon-statefulset.yaml` | `gp3` |
| splunk (dev utility, disabled by default) | `values.yaml` `splunk.persistence.storageClassName` → `splunk-statefulset.yaml` (two claims: `var` + `etc`) | `gp3` |

Bitnami subchart equivalents are shipped as commented examples (the subchart
paths take `storageClass`, not `storageClassName`):
`postgresql.bitnami.primary.persistence.storageClass` and
`redis.bitnami.master.persistence.storageClass`.

Redis on provisioned-IOPS EBS (io2) is the documented latency upgrade, left
commented in the profile — a default that silently bills premium storage is
not a default (decision log #3 in [README](README.md)).

**Sources (provider-side):** EBS CSI add-on / gp3 non-default behavior and EKS
Auto Mode `auto-ebs-sc` were verified against AWS documentation on 2026-10-10
during the spec phase (source id `WEB-STG` in the
[spec](https://app.obvious.ai/p/prj_43ysv7Jj?blueprint=art_S6S8vxuB)). This
note carries those strings forward; they were not re-fetched when this file
was written (2026-10-10, same day).

## Render evidence

Recorded 2026-10-10 in the repo sandbox, helm **v3.15.2** and kubeconform
**v0.6.7** (both the same versions CI pins), subcharts extracted per the CI
recipe (`sha256sum -c SHA256SUMS`, then `tar -xzf` each `charts/*.tgz` — see
the loader caveat below). Branch `feat/helm-profile-eks`, base `0564cd7`.

| Check | Command shape | Result |
|---|---|---|
| `helm dependency build` | throwaway chart copy, repos registered | exit 0; `Chart.lock` honored as-is, pinned versions pulled byte-identical to `SHA256SUMS` |
| Checksums | `sha256sum -c SHA256SUMS` | all three tgz OK |
| lint | `helm lint infra/helm/vigil -f infra/helm/vigil/values-aws.yaml` | `1 chart(s) linted, 0 chart(s) failed`, no warnings |
| render (default) | `helm template release-check infra/helm/vigil -f …values-aws.yaml --set secrets.anthropicApiKey=test-key` | 18 resources; `storageClassName: "gp3"` × **3** (splunk disabled) |
| render (splunk on) | same + `--set splunk.enabled=true` | 21 resources; `storageClassName: "gp3"` × **5** — daemon, postgres, redis, splunk (`var` + `etc`) |
| kubeconform strict | `-strict -ignore-missing-schemas -summary` on both renders | 21/21 and 18/18 valid; 0 invalid, 0 errors, 0 skipped |

The spec's `grep -c "storageClassName: gp3"` example needs the quoted form —
the chart templates pipe the value through `\| quote`, so the render carries
`storageClassName: "gp3"`. The splunk-enabled render is what demonstrates the
fourth pin, because `splunk.enabled` defaults to `false` and the splunk
StatefulSet does not render otherwise. Its pin is inert while disabled.

**Loader caveat (cost us a debug cycle — recorded so it costs nobody else
one).** The chart's `.helmignore` contains `*.tgz`. Helm's directory loader
applies `.helmignore` while walking the chart, so vendored subcharts left as
tgz files are silently skipped and `helm template` fails in
`CheckDependencies` with *"found in Chart.yaml, but missing in charts/
directory"* — even though `helm dependency list` reports them `ok` and lint
passes with only a warning. CI handles this by extracting the tgz into
`charts/<name>/` directories after verifying checksums ("Helm 4 wants
directories, not just tgz" in `helm-chart.yml`). Run local checks the same
way; do not "fix" it by deleting `*.tgz` from `.helmignore` — that would
re-package the vendored subcharts into any `helm package` output.

## Documented hooks (not wired by the profile)

**Ingress / ALB.** Chart default is ClusterIP everywhere plus a disabled
Ingress. The commented hook enables the AWS Load Balancer Controller path:
`ingress.className: alb` with `alb.ingress.kubernetes.io/group.name` and
`alb.ingress.kubernetes.io/scheme` annotations (`ingress.annotations` is a
free-form passthrough in the chart). If `networkPolicies` are enabled, the
controller's namespace must be added to
`networkPolicies.ingressControllerNamespaceSelector` — the chart default
selector matches `ingress-nginx` only, while the ALB controller typically
runs in `kube-system` or `aws-load-balancer`.

**NLB (LoadBalancer Service) — a values gap, flagged not fixed.** The NLB
annotation strings are
`service.beta.kubernetes.io/aws-load-balancer-type: "external"` plus
`service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip` (the
`"external"` value, not the older `"external/nlb"` form; verified 2026-10-10,
`WEB-STG`). But no Service template in the chart passes annotations through —
`backend-service.yaml` and `daemon-service.yaml` render `.service.type` and
nothing else cloud-relevant, and the other Services are pinned ClusterIP.
So an NLB Service cannot be reached from values alone; wiring it needs the
same kind of small template change as the workload-identity follow-up. Until
then the strings live here, not in the profile.

**Identity / IRSA.** The hook is a commented pair, because the two keys only
work together:

```yaml
serviceAccount:
  automountServiceAccountToken: true        # chart default: false
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<ACCOUNT>:role/vigil-<cluster>
```

The annotation itself renders fine today — `serviceaccount.yaml` passes
`serviceAccount.annotations` through via `toYaml`. The blocker is the other
key: IRSA's pod-identity webhook does not inject the projected token while
`automountServiceAccountToken: false` (the chart default). Flipping token
automount is a security decision for the operator, so the profile documents
the pair instead of setting it (decision log #4). Related known gap:
the honey-router needs Kubernetes API access but the chart ships no
RBAC scaffolding — provider-independent, tracked as a follow-up in
[cloud-touchpoints.md §5](cloud-touchpoints.md).

**Images / ECR pull-through.** Vigil's own images come from
`ghcr.io/vigil-soc` and pull anonymously everywhere, but seven support
images come from Docker Hub and CI has already been rate-limited by it
(429, 2026-10-09 — see [chart-anatomy.md](chart-anatomy.md)). The commented
`global.imagePullSecrets` hook points operators at an ECR pull-through
cache.

**Node scheduling.** All components expose empty `nodeSelector`/`tolerations`/
`affinity`; the commented example pins the daemon to a dedicated managed node
group.

## Cilium note (the honey-router's per-cloud dependency)

The daemon's honey-router emits `CiliumLocalRedirectPolicy` objects at
runtime and fails honestly when the `cilium.io` CRDs are absent
(`core/integrations/honey_router/route.py`; prerequisites in
`docs/mtd-enablement.md`: "Cilium CNI already running on the cluster… Vigil
does not install Cilium for you"). On EKS the default VPC CNI ships neither
Cilium nor its CRDs, so MTD rerouting on EKS means installing Cilium as the
replacement CNI (or alongside with proper wiring) before enabling the
honey-router. Per-cloud CNI comparison lives in
[cloud-touchpoints.md §3](cloud-touchpoints.md).

## Enforcer note (drift since the spec survey)

The spec's research recorded no enforcer workload; `ed94f2c` has since landed
an opt-in kernel enforcer (`templates/enforcer-daemonset.yaml`,
`enforcer.enabled: false`, hostPath + BPF). It adds no PVC, so the four-pin
model above is unchanged. EKS-specific constraint if it is ever enabled:
Bottlerocket nodes restrict arbitrary hostPath mounts — the enforcer needs
AL2023 nodes or a Bottlerocket allowlist. Recorded in
[cloud-touchpoints.md §3](cloud-touchpoints.md); the profile leaves
`enforcer.enabled` at the chart default of `false`.

## Source trail

**Chart-side (read this session, branch base `0564cd7`):**
`values.yaml` (all four `persistence` blocks, `ingress`, `serviceAccount`,
`networkPolicies`, `global`), `templates/{postgres,redis,daemon,splunk}-statefulset.yaml`
(`storageClassName` guards + `| quote`), `templates/serviceaccount.yaml`
(annotation passthrough, `automountServiceAccountToken` default),
`templates/backend-service.yaml` / `daemon-service.yaml` (no annotation
passthrough), `Chart.yaml`, `Chart.lock`, `SHA256SUMS`, `.helmignore`,
`values-dev.yaml`, `.github/workflows/helm-chart.yml` (discovery loops,
checksum+extract recipe), `tests/unit/_ratchets/test_helm_env_names_are_read.py`
(glob discovery).

**Provider-side:** carried from the spec's 2026-10-10 verification
(`WEB-STG` storage/LB strings, `WEB-ID` IRSA) — not re-fetched while writing
this note. Same-day, but if you read this much later, re-verify the gp3
non-default and Auto Mode behaviors against current AWS docs before trusting
the pins' rationale.

**Render evidence:** the table above was captured from this session's runs —
every count in it is from a command output recorded during this PR's
preparation, not from memory.

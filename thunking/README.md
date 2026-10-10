# thunking/ — research and decision trail for cloud deployment

Research notes and decision records for running the Vigil SOC Helm chart
(`infra/helm/vigil`) on managed Kubernetes clouds. Nothing here executes at
install time. The folder exists so the choices behind the per-cloud values
profiles ship with the code instead of living in a chat thread.

The spelling `thunking/` is the requested folder name — kept as asked.

## Tree state this folder describes

| State | Commit | Meaning |
|---|---|---|
| Surveyed | `f5b3153` | Read-only chart + touchpoint inspection the research artifacts were written against (2026-10-10) |
| Spec-verified | `5628e17` | `origin/main` re-verification for the spec; intervening commits touched API/digital-twin code only, no chart or CI paths |
| Adapted | `c8b4826` | Tree the first draft of this folder was written against. One chart-CI change since `5628e17` — see Drift, below |
| Current | `b28bc372` | `origin/main` when the foundation PR rebased. The kernel enforcer landed in between — see Drift, below |

Anything a research claim did not survive into the current tree is recorded as
a correction in the *Adaptation notes* section of the affected file, not
silently rewritten.

**Drift since `5628e17`:** `39df634` ("ci(helm): vendor subcharts to stop
Docker Hub 429 failures") vendored the three pinned subcharts into
`charts/*.tgz` with `SHA256SUMS` verification and deleted CI's
`helm dependency update` fetch step; `d0d2a54`/`c8b4826` imported operator
docs into `docs/deploy/` and repointed in-chart comment links. Chart values,
templates, and `Chart.yaml`/`Chart.lock` are otherwise unchanged — verified by
diffing `f5b3153..c8b4826`.

**Drift `c8b4826` → `b28bc372` (caught by re-running the survey before this
PR rebased — the spec's own rule for survey/`origin/main` drift):**
`ed94f2c9` ("Release: eBPF and XDP enforcement daemons") landed the kernel
enforcer the research had recorded as absent: `templates/enforcer-daemonset.yaml`
(opt-in, `enforcer.enabled: false`), the `enforcer:` values block
(values.yaml 1017 → 1093 lines), `secrets.enforcementToken`, the
`vigil.enforcer.fullname`/`-enforcer` image helper, `.github/workflows/enforcement.yml`
and `.github/workflows/integrations.yml`, `services/enforcement/` (Go daemon +
BPF objects), `core/integrations/ebpf_xdp/`, and the `fizzbait/` sample
datasets. `ca4863dd`/`27c0f0df`/`b28bc372` added the digital-twin screen, S3
ingestion datasets, and baked-docs reconciliation — none touch chart or CI
paths. The touchpoints and anatomy notes were re-surveyed against `b28bc372`
and updated in place; the enforcer's per-cloud implications are recorded in
[cloud-touchpoints.md](cloud-touchpoints.md) (§3) rather than in a new file.

## Reading order

1. **`chart-anatomy.md`** — what the chart *is*: layout, dependency locks,
   every values key, every template, CI workflows, ratchet tests.
2. **`cloud-touchpoints.md`** — where clouds *bite*: touchpoint → current
   behavior → per-cloud requirements master table, with file-level evidence.
3. **`aws-eks.md`, `azure-aks.md`, `gcp-gke.md`** — per-cloud decisions and
   render evidence. These land with their profile PRs
   (`values-aws.yaml`, `values-azure.yaml`, `values-gcp.yaml`) and are listed
   here as pending until those PRs merge.

## The profile-layering model

Vigil installs as **one chart plus a stack of values layers**. There are no
per-cloud charts to maintain and no forks to rebase; adding a cloud is adding
one file. Merge order per install — every layer overrides the one above it:

```
chart values.yaml  →  values-<cloud>.yaml  →  operator --set
     (defaults)         (cloud pins only)      (credentials, site choices)
```

Install shape (example: AWS):

```bash
helm install vigil ./infra/helm/vigil \
  -f ./infra/helm/vigil/values-aws.yaml \
  --namespace vigil --create-namespace \
  --set secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set secrets.postgresPassword="$(openssl rand -hex 24)" \
  --set secrets.jwtSecretKey="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
```

Profiles only pin what the cloud changes; they never redefine what the base
chart already defaults. The layering rules every profile must obey:

- **Pin `storageClassName` at all four PVC sites** (postgresql, redis, daemon,
  splunk) plus commented Bitnami-subchart equivalents. Never rely on the
  cluster default: it differs per provider and per cluster version.
- **Pin the provider's balanced SSD tier everywhere.** Premium tiers (redis is
  the latency-sensitive case) appear only as commented upgrades — a default
  that silently bills premium storage is not a default.
- **Never set `dbInit.*`** or any key whose base form is the 44-file SQL list:
  `helm -f` layering replaces whole keys, and a profile redefining `dbInit`
  would ship an incomplete SQL list (the db-init SQL ratchet fails — intended).
- **Never introduce new `config.*` keys.** The env-name ratchet fails until
  code reads them. Existing keys (e.g. `config.AWS_REGION`) are safe.
- **Ship exposure, workload identity, image pull-through, and node scheduling
  as commented examples** — see the decision log for why identity stays
  unwired.
- **Open with a header comment:** the exact `helm install` invocation and the
  cluster prerequisites (CSI addon, LB controller, identity webhook state).

CI enforces the model mechanically: the Helm Chart workflow lints, renders,
and kubeconforms **every** `values*.yaml` in the chart directory (discovered
by glob), so a profile PR is a pure file addition and its own CI validates it.

## Decision log

Decisions locked for this work, each with its reversal condition:

1. **Values profiles, not wrapper charts.** The chart was built as one chart +
   values layers (three render variants were already CI-tested; three-mode
   Postgres/Redis resolution lives in the helpers). Wrapper umbrellas
   (`infra/helm/vigil-aws/` etc.) would add three more linted charts, fork the
   install story per cloud, and inherit the local-path-only distribution the
   current chart already has — complexity with no benefit while nothing
   publishes charts. *Reversal condition:* profiles need cloud addon charts
   versioned **and upgraded in lockstep** with the app chart → reopen as a
   wrapper umbrella.
2. **Big three only.** EKS, AKS, GKE. OCI, DigitalOcean, Alibaba, et al. are
   follow-up profile files — one file each by design, reversible.
3. **Profiles pin each provider's balanced SSD tier**; premium storage appears
   only as commented upgrades — no silent premium billing.
4. **Identity, LB exposure, pull-through caches, and node scheduling ship as
   documented hooks, not wired defaults.** Wiring workload identity needs
   template changes (serviceAccount annotation passthrough exists, but the
   token automount flip is security-relevant and not something a values PR
   does silently). The honey-router RBAC gap is provider-independent and gets
   its own follow-up.
5. **No live-cluster validation.** Render- and schema-level CI only (there is
   no kind cluster or `ct install` in this repo's CI, before or after this
   work). Every per-cloud note says this out loud; a kind/`ct install` smoke
   test is flagged as a follow-up, not built here.
6. **Folder spelling is `thunking/`** — the requested name, nonstandard
   spelling kept as asked.

## Pre-flight: `helm dependency build` and the Chart.lock digest (R1)

`Chart.lock` carries a **single top-level `digest:`** field rather than the
per-dependency `digest:` entries Helm normally writes. Before building
profiles on `helm dependency build` behavior, the spec required running it
once and recording whether the lock is honored or regenerated. Run 2026-10-10
in this repo's sandbox, helm **v3.15.2** (same version as CI), on a throwaway
copy of the chart at `c8b4826` — the working tree was untouched.

**Result: honored as-is, with caveats.**

- Without `helm repo add` first, `helm dependency build` **fails immediately**
  (`Error: no repository definition for https://charts.bitnami.com/bitnami, …`
  — exit 1). `Chart.lock` untouched. `dependency build` is not
  repo-independent; the old CI registered repos for exactly this reason.
- With both repos registered, the build **succeeds and re-downloads all three
  pinned subcharts over the network** (`Saving 3 charts … Downloading
  postgresql …` — pulled from `registry-1.docker.io/bitnamicharts`). It does
  **not** reuse the vendored `charts/*.tgz`.
- **`Chart.lock` is byte-identical after the run** (sha256 before/after): helm
  neither rejected the single-top-level-digest shape nor rewrote it to the
  per-dependency format, and it followed the pinned versions exactly.
- All three vendored tgz files are **byte-identical after the re-download**
  (sha256 match) — an independent confirmation of the `SHA256SUMS` digests.

Implications:

- Profile CI may rely on the pinned lock: helm honors it as-is.
- CI's vendoring (verify `SHA256SUMS`, then extract) is what keeps the Helm
  Chart job hermetic — `helm dependency build` re-fetches from Docker Hub and
  would re-expose the anonymous-pull 429 hazard that vendoring removed. Do not
  reintroduce a `dependency build` step into CI; `ct lint` runs with
  `--skip-helm-dependencies` for the same reason.
- The absent per-dependency digests never gate anything helm runs here: the
  vendoring path verifies checksums via `sha256sum -c SHA256SUMS`, not via
  Chart.lock.

## What validation does and does not prove

All validation for this work is **render- and schema-level**: `helm lint`,
`helm template`, kubeconform (`-strict -ignore-missing-schemas -summary`),
`ct lint`, and the unit ratchets. No part of this work installs into a real
EKS/AKS/GKE cluster — this repo's CI has no kind cluster and no `ct install`,
and none was added. Semantic mistakes (a wrong ingress class name, a wrong
namespace selector) will **not** be caught by schema checks; that is exactly
what each profile's `thunking/` render-evidence counts are for. The first real
deploy remains the operator's step, guided by the per-cloud notes.

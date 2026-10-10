# Chart anatomy — `infra/helm/vigil`

**Scope:** survey of the Vigil Helm chart to ground per-cloud deployment
profiles (AWS EKS / Azure AKS / GCP GKE). Adapted from the research artifact
_"Research: Vigil Helm chart anatomy + CI"_, which inspected the tree at
`f5b3153` (2026-10-10); the spec re-verified against `5628e17`.

**Tree this document describes: `b28bc372`** (first drafted against
`c8b4826`; re-surveyed after the foundation PR rebased — the kernel enforcer
landed in between, see §6/§11 and the [README drift log](README.md)). Facts
were read directly from the working tree; anything inferred is marked
*Inference*. Every correction made during adaptation is listed in
[Adaptation notes](#adaptation-notes) and never applied silently.

---

## 1. TL;DR

- The chart lives at **`infra/helm/vigil/`** (chart name `vigil`, chart version
  **0.7.0**, appVersion **0.7.0**, `kubeVersion: '>=1.25.0-0'`).
- Subcharts are **vendored in git** since `39df634`: `charts/*.tgz` files are
  committed with SHA256 checksums in `SHA256SUMS`, so CI performs **no chart
  network I/O**. (At survey time they were fetched every run with
  `helm dependency update` and Docker-Hub-429 retry backoff — that step is
  gone; see §7.)
- Workloads: backend (Deployment), SOC daemon (**StatefulSet, `replicas: 1`
  hardcoded** — deliberately not exposed in values), llm-worker + agent-worker
  (Deployments with HPA **or** KEDA ScaledObject paths), agent-serve
  (Deployment, no autoscaling by design), two optional decoys (SSH + HTTP
  Deployments with ClusterIP Services and default-deny-egress
  NetworkPolicies), plus optional in-chart Postgres/Redis StatefulSets and
  dev-only Splunk/pgAdmin. Since `ed94f2c9` there is also an **opt-in kernel
  enforcer DaemonSet** (`enforcer.enabled: false` — not rendered while
  disabled; §6). **There is no PDB anywhere** (see §11).
- CI is two workflows: **`.github/workflows/helm-chart.yml`** ("Helm Chart":
  SQL-sync diff, vendored-checksum verify, lint/template/kubeconform per
  discovered `values*.yaml` profile + a fixed Bitnami `--set` variant,
  `ct lint`) and the **`test-helm-install-schema`** job in
  **`.github/workflows/ci-cd.yml`** (renders and executes the db-init Job
  against a real Postgres, then asserts schema parity). Nothing packages or
  publishes the chart — consumption is **local path only**.
- Two unit "ratchet" tests pin chart correctness:
  `tests/unit/_ratchets/test_helm_db_init_sql_files.py` and
  `tests/unit/_ratchets/test_helm_env_names_are_read.py`. The latter now
  discovers **every `values*.yaml` in the chart directory by glob** (this
  landed with the `thunking/` foundation PR; at survey time it was an explicit
  two-file parametrize list) — a new profile file is scanned automatically, no
  test edit needed (§7.4).
- `values-dev.yaml` is the only values profile that exists; cloud profiles are
  layered on top per the model in [README](README.md).

## 2. Chart layout

```
infra/helm/vigil/
├── Chart.yaml                  # name/version/deps (see §3)
├── Chart.lock                  # dependency pins + one top-level digest (see §3.2)
├── SHA256SUMS                  # vendored subchart checksums (see §3.3)
├── values.yaml                 # 1093 lines: every default (see §4)
├── values-dev.yaml             # 70 lines: the only profile today (see §5)
├── README.md                   # chart overview, subchart bump process, thunking/ pointer
├── .helmignore                 # default-ish ignores
├── .gitignore                  # tracks vendored charts/*.tgz, ignores extracted dirs
├── charts/                     # vendored subchart tgz (postgresql 16.2.2, redis 20.3.0,
│                               #   opentelemetry-collector 0.108.0) — committed
├── files/database-init/*.sql   # 44 SQL files bundled INTO the chart (copied from
│                               #   infra/database/init/; CI diffs the two dirs)
└── templates/                  # 32 YAML files at top level (+ tests/test-connection.yaml
                                #   = 33; enforcer-daemonset.yaml landed ed94f2c9)
                                #   (+ NOTES.txt + _helpers.tpl + _env.tpl) (see §6)
```

`.gitignore` (verbatim, post-vendoring): *"Subcharts are vendored: pinned tgz
files are committed so CI never fetches charts over the network (checksums
live in SHA256SUMS at the chart root; see README.md for the bump process).
Extracted subchart directories stay untracked."* — i.e. `charts/*` ignored,
`!charts/*.tgz` un-ignored.

## 3. Chart.yaml and dependencies

`Chart.yaml` — `apiVersion: v2`, `name: vigil`,
`description: Vigil SOC — open-source, AI-native Security Operations Center`,
`type: application`, `version: 0.7.0`, `appVersion: 0.7.0`,
`kubeVersion: '>=1.25.0-0'`, `home: https://vigilsoc.org`,
`sources: [https://github.com/Vigil-SOC/vigil]`,
`maintainers: [{name: Vigil-SOC, url: https://github.com/Vigil-SOC}]`,
`keywords: [security, soc, siem, ai, claude, anthropic, mcp]`,
`icon: https://vigilsoc.org/logo.png`,
`annotations: {artifacthub.io/category: security, artifacthub.io/license: Apache-2.0}`.

### 3.1 Dependency table (exact)

| Dependency | Version | Repository | Condition | Alias | Extra |
|---|---|---|---|---|---|
| `postgresql` (Bitnami) | **16.2.2** | `https://charts.bitnami.com/bitnami` | `postgresql.bitnami.enabled` | — | `import-values: [{child: auth, parent: postgresql.bitnami.auth}]` |
| `redis` (Bitnami) | **20.3.0** | `https://charts.bitnami.com/bitnami` | `redis.bitnami.enabled` | — | — |
| `opentelemetry-collector` | **0.108.0** | `https://open-telemetry.github.io/opentelemetry-helm-charts` | `otelCollector.enabled` | `otelCollector` | — |

All three conditions are **off by default** (`values.yaml`:
`postgresql.bitnami.enabled: false`, `redis.bitnami.enabled: false`,
`otelCollector.enabled: false`), so a fresh `helm template` renders without
fetching subcharts. The chart ships its **own** MVP Postgres/Redis as
StatefulSets (postgres:16-alpine / redis:7-alpine) and only delegates to the
Bitnami subcharts when the `*.bitnami.enabled` toggles flip.

### 3.2 Chart.lock and digest verification

`Chart.lock` (verified byte-identical at `c8b4826`):

```yaml
dependencies:
- name: postgresql
  repository: https://charts.bitnami.com/bitnami
  version: 16.2.2
- name: redis
  repository: https://charts.bitnami.com/bitnami
  version: 20.3.0
- name: opentelemetry-collector
  repository: https://open-telemetry.github.io/opentelemetry-helm-charts
  version: 0.108.0
digest: sha256:8c3e43f2e6c1aed9eb63acc905e615d146dd92245462c1f6ff873afac6dea0f1
generated: "2026-05-18T17:39:17.6291-07:00"
```

The lock carries a **single top-level `digest:`** rather than the
per-dependency `digest:` fields Helm's lock format normally writes. The R1
pre-flight (run and recorded in [README](README.md)) settled the open
question: **helm v3.15.2 honors this lock as-is** — `helm dependency build`
(needs `helm repo add` first) follows the pinned versions, downloads
byte-identical artifacts, and does not rewrite the lock.

How artifact integrity is actually enforced in this repo, as practiced:

1. **Vendored checksums, not network fetches:** CI (and any operator) verifies
   `sha256sum -c SHA256SUMS` against the committed `charts/*.tgz`. The digests
   were cross-checked against the bitnami index / OCI registry / otel release
   source at vendor time (see `SHA256SUMS` header, commit `39df634`).
2. **Helm's lock mechanism is the second layer:** `helm dependency build`
   verifies fetched artifacts against the pinned versions; the pre-flight
   showed re-downloads byte-match the vendored tgz.
3. There is no cosign/SBOM/OCI-digest pinning anywhere in the repo (no
   `helm package`, no OCI registry references, no policy controllers).

### 3.3 Bumping a subchart

Process from the chart README: run `helm dependency update infra/helm/vigil`,
refresh `SHA256SUMS` from the upstream digests, commit the new tgz files.
Extracted subchart directories stay untracked.

## 4. values.yaml — every top-level key and what it controls

`values.yaml`, 1093 lines, 31 top-level keys, in file order. Unchanged from
the survey through `c8b4826` except one header comment; `ed94f2c9` then added
the `enforcer:` block and `secrets.enforcementToken` (see Adaptation notes):

| Key | Controls |
|---|---|
| `global` | `imageRegistry` (default `ghcr.io`; set by release.yml), `imageNamespace` (`vigil-soc/vigil`; image ref becomes `<registry>/<namespace>-<component>`), `imagePullPolicy` (`IfNotPresent`), `imagePullSecrets` (`[]`) |
| `nameOverride`, `fullnameOverride` | Standard Helm name overrides; `_helpers.tpl` `vigil.name` / `vigil.fullname` |
| `commonLabels` | Labels merged into every rendered resource (`vigil.labels`) |
| `backend` | FastAPI Deployment + Service: `replicaCount: 2`, `image{repository,tag,pullPolicy}` (empty → auto-derived `<registry>/<ns>-backend` / AppVersion / global pull policy via `vigil.image` helper), `service{type: ClusterIP, port: 6987}`, `resources` (req 250m/512Mi, lim 1CPU/1Gi), `autoscaling{enabled: false, minReplicas: 2, maxReplicas: 10, targetCPUUtilizationPercentage: 70, targetMemoryUtilizationPercentage: 80}`, pod scheduling (`podAnnotations`, `podLabels`, `nodeSelector`, `tolerations`, `affinity`), `extraEnv`, `env{BIND_HOST: 0.0.0.0}` |
| `daemon` | SOC daemon singleton: `enabled: true`, `image` (→ `-daemon` suffix), `ports{webhook: 8081, metrics: 9090, health: 9091}`, `service{type: ClusterIP}`, `resources` (req 500m/1Gi, lim 2CPU/4Gi), `persistence{enabled: true, size: 10Gi, storageClassName: "", accessModes: [ReadWriteOnce], mountPath: /app/data/investigations}`, scheduling knobs, `extraEnv`. **`replicas: 1` is hardcoded in the StatefulSet, deliberately not a value** (comment: in-memory orchestrator state must not be shared) |
| `enforcer` | Opt-in kernel-enforcement DaemonSet, one privileged pod per node (landed `ed94f2c9`; **not rendered while `enabled: false`**): `image` (→ `-enforcer` Go/eBPF image, `Dockerfile.enforcer`), `bind: "127.0.0.1:6986"` (node-loopback API, **no Service by design**), `port: 6986` (also healthz/metrics), `interface: eth0` (XDP target), `cgroup: /sys/fs/cgroup`, `defaultTtlSeconds: 3600`, `sink: ""` (empty = socket-redirect capability off), `capabilities.add: [BPF, NET_ADMIN, PERFMON, SYS_ADMIN]` (trim per site), `resources` (req 100m/128Mi), scheduling knobs, `extraEnv`. Node prerequisites: bpffs, cgroup2, kernel BTF — `services/enforcement/runbook.md` |
| `llmWorker` | ARQ worker (shares backend image, runs `services.worker`): `enabled`, `replicaCount: 2`, `image` (inherits backend image when empty), `resources`, `autoscaling{enabled: false, keda{enabled: false, minReplicas: 2, maxReplicas: 20, cooldownPeriod: 300, pollingInterval: 15, queueName: "arq:llm", listLength: "5", redisAddress: ""}}` — CPU HPA and KEDA are **mutually exclusive**; `redisAddress` only when both in-chart Redis modes are off; scheduling knobs, `extraEnv` |
| `agentWorker` | TypeScript BullMQ consumer (own Node image → `-agent` suffix): `enabled`, `replicaCount: 2`, `resources`, `autoscaling{…keda{…, queueName: "bull:agent-runs:wait", …}}` (minReplicas clamped ≥1 by the template; `databaseIndex` only relevant with external Redis), scheduling knobs, `extraEnv` |
| `agentServe` | SSE/chat serve (same `-agent` image): `enabled`, `replicaCount: 2`, `service{port: 6989}` (reached by backend via computed `AGENT_URL`), `terminationGracePeriodSeconds: 120` (don't drop live SSE turns), `resources`, scheduling knobs, `extraEnv`. **No autoscaling block at all — documented decision**: CPU reads near zero while SSE streams hold, so an HPA would scale it down mid-answer |
| `postgresql` | Three modes resolved by `_helpers.tpl` `vigil.postgres.*`: **(1) MVP in-chart StatefulSet** — `enabled: true`, `image{postgres, tag: 16-alpine}`, `auth{database: deeptempo_soc, username: deeptempo, existingSecret, existingSecretKey: POSTGRES_PASSWORD}`, `service.port: 5432`, `persistence{enabled, size: 50Gi, storageClassName: ""}`, `resources`; **(2) external** — `external{host (required when enabled=false), port, database, username, existingSecret, existingSecretKey, sslRequired (documented "Unused": SSL goes through POSTGRES_SSL_MODE via extraConfig)}`; **(3) Bitnami subchart** — `bitnami{enabled: false, fullnameOverride, auth{…}, primary{service.ports.postgresql, persistence.size: 50Gi}}`; passthrough to subchart values |
| `redis` | Same three modes: **(1) MVP** `enabled: true`, `image{redis, 7-alpine}`, `service.port: 6379`, `persistence{5Gi}`, `args: [--appendonly yes, --maxmemory 512mb, --maxmemory-policy noeviction]` (AOF on, no silent eviction — Redis holds queues + dedup state), `resources`; **(2) external** `external{url (full URL, wins over in-chart), existingSecret, existingSecretKey: REDIS_URL}`; **(3) Bitnami** `bitnami{enabled: false, fullnameOverride, architecture: standalone, auth{…}, master.persistence.size: 5Gi}` |
| `dbInit` | Hook Job applying bundled SQL: `enabled: true`, `image{postgres, 16-alpine}`, `sqlFiles` — **explicit ordered list of 44 filenames** (files added under `infra/database/init/` do NOT auto-run; `test_helm_db_init_sql_files.py` fails until listed), `resources` (50m/128Mi req) |
| `ingress` | `enabled: false`, `className: nginx`, `annotations: {}` (commented examples: nginx proxy-body-size, cert-manager issuer), `hosts: [{host: vigil.local, paths: [{path: /, pathType: Prefix}]}]`, `tls: []` — comment: subdirectory deploys must set `config.VIGIL_CONTEXT_PATH` themselves; the chart does not derive one from the other |
| `serviceAccount` | `create: true`, `name: ""`, `annotations: {}` (the hook for cloud-provider IAM annotation — currently unused), `automountServiceAccountToken: false` |
| `stateDirectory` | `mountPath: /var/lib/vigil` exported as `VIGIL_DIR` to backend/daemon/llm-worker; `volume{emptyDir: {}}` **deliberately per-pod** (RWO can't be shared by `backend.replicaCount > 1`; ReadWriteMany not universal). PVC option documented in comments for ReadWriteMany clusters |
| `caBundle` | Optional operator-supplied PEM (TLS-inspecting proxies) mounted into backend/daemon/llm-worker/agent-worker/agent-serve with `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` set: `existingSecret`, `existingConfigMap`, `key: ca.crt`, `mountPath: /etc/vigil/ca-bundle.pem`. Chart does not create the Secret |
| `podSecurityContext` | `runAsNonRoot: true`, `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`, `seccompProfile: {type: RuntimeDefault}` |
| `containerSecurityContext` | `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: false`, `capabilities.drop: [ALL]` |
| `secrets` | All credential material (plain values → `secret.yaml` stringData): `existingSecret` (skips templating), decoy plane (`decoyIngestToken`, `decoyCanaryPassword`), `externalSecret{enabled: false, refreshInterval: 1h, secretStoreRef{name, kind: ClusterSecretStore}, data{}, dataFrom[]}` (ExternalSecrets Operator; comments name AWS SM / Vault / GCP Secret Manager as targets), then required keys `anthropicApiKey`, `postgresPassword: "change-me-before-production"`, `jwtSecretKey`, `agentInternalToken`, `enforcementToken` (the enforcer DaemonSet's `VIGIL_ENFORCEMENT_TOKEN`), optional integrations (`splunkPassword`, `crowdstrike*`, `elastic*`, `criblPassword`, `darktraceWebhookSecret`, `vstrike*`), threat intel (`virustotalApiKey`, `shodanApiKey`, `alienvaultOtxApiKey`, `joeSandboxApiKey`, `capeSandboxApiKey`), notifications (`slackBotToken`, `pagerdutyRoutingKey`, `teamsWebhookUrl`), **cloud (`awsAccessKeyId`, `awsSecretAccessKey`, `githubToken`)**, `smtpPassword`, `kafkaSaslPassword`, `openaiApiKey` |
| `config` | ~90 non-secret env keys rendered into the shared ConfigMap: `DEV_MODE: "false"`, secrets/auth policy, email, CORS/HSTS/CSP/CSRF headers + `VIGIL_CONTEXT_PATH`, integration endpoints, sandbox flags, `SLACK_DEFAULT_CHANNEL`, **`AWS_REGION: "us-east-1"` (non-secret)**, ~25 `DAEMON_*` keys (poll intervals, auto-triage/enrich/response, MTD/honey-routing band — default off, escalation, metrics/health ports; `DAEMON_ENFORCEMENT_FORCE_APPROVAL: "true"` added `ed94f2c9`), `ORCHESTRATOR_*` (disabled by default; cost caps), OTEL (`VIGIL_OTEL_ENABLED: "false"`, `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317`), Kafka (disabled), `PYTHONUNBUFFERED`, `BIFROST_URL`, `OLLAMA_URL` |
| `extraConfig` | `{}` — ad-hoc site env merged last; also the documented override for chart-computed values |
| `otelCollector` | Passthrough to the aliased subchart: `enabled: false`, `mode: deployment`, `replicaCount: 1`, `image{repository: otel/opentelemetry-collector-contrib}` (upstream requires it explicit), full `config` block (OTLP gRPC 4317 / HTTP 4318, batch processor, debug exporters). When enabled, the ConfigMap auto-rewrites `OTEL_EXPORTER_OTLP_ENDPOINT` to `http://<release>-opentelemetry-collector:4317` |
| `observability` | `serviceMonitor{enabled: false, …}` — Prometheus Operator CRD required; daemon metrics port only serves when `config.VIGIL_OTEL_ENABLED: "true"` |
| `sshDecoy` | `enabled: false` + image (inherits backend image; runs `python -m services.decoy.ssh_decoy`), resources, scheduling knobs, `extraEnv` |
| `httpDecoy` | Same shape (runs `python -m services.decoy.http_decoy`) |
| `decoys` | Shared decoy knobs read via `services/decoy/config.py`: `sessionTtlSeconds: 3600`, `ports{ssh: 2222, http: 8080}` (comment: fixed, part of compose + Cilium wiring — changing is a coordinated change across surfaces) |
| `networkPolicies` | `enabled: false` (comment: flipping on an existing cluster may break implicitly-allowed traffic), `ingressControllerNamespaceSelector{kubernetes.io/metadata.name: ingress-nginx}`, `daemon{webhookAllowFrom: []}` (SIEM/EDR CIDRs that may POST to the webhook), `agentServe{allowProbesFromAnyNamespace: true}` (CNI-dependent probe admission, ADR 0014 referenced) |
| `splunk` | Dev utility: `enabled: false`, `image{splunk/splunk, latest}`, `auth{existingSecret, password: changeme123}`, `hecToken`, `persistence{size: 50Gi, storageClassName: ""}`, `resources` |
| `pgadmin` | Dev utility: `enabled: false`, `image{dpage/pgadmin4, latest}`, `auth{email, existingSecret, password: admin}`, `resources` |
| `tests` | `image{repository: curlimages/curl, tag: 8.10.1}` for the `helm test` pod |

## 5. values-dev.yaml — the only existing profile

`values-dev.yaml` (70 lines), header gives the invocation:

```bash
helm install vigil infra/helm/vigil -f infra/helm/vigil/values-dev.yaml \
  --set secrets.anthropicApiKey=$ANTHROPIC_API_KEY \
  -n vigil --create-namespace
```

It overrides: `config.DEV_MODE: "true"` + `config.VIGIL_COOKIE_SECURE: "false"`
(auth bypassed — file states it is NOT production-suitable), shrinks
`backend`/`llmWorker`/`daemon`/`postgresql`/`redis` resources, shrinks
`daemon.persistence.size` to 1Gi, `postgresql.persistence.size` to 5Gi,
`redis.persistence.size` to 1Gi, and sets
`secrets.postgresPassword: "dev_password_change_me"`. No ingress, no TLS.

**This is the structural precedent the cloud profiles follow** — except the
profiles never set `secrets.*` (credentials are operator `--set`) and never
touch `config.*` beyond keys that already exist.

## 6. Template inventory — every file

33 YAML templates (32 at `templates/` top level + `tests/test-connection.yaml`;
the 32nd top-level file, `enforcer-daemonset.yaml`, landed `ed94f2c9`) +
`NOTES.txt` + `_helpers.tpl` + `_env.tpl`.

### Workloads

| Template | Kind(s) | Gate | Notes |
|---|---|---|---|
| `backend-deployment.yaml` | Deployment | unconditional (no `backend.enabled` exists) | `replicas: {{ .Values.backend.replicaCount }}`; first `if` chooses fixed replicas vs HPA; probes on port `http`: startup+liveness `GET /api/health`, readiness `GET /api/health/ready`; checksum annotations on configmap+secret |
| `backend-service.yaml` | Service | unconditional | port 6987 |
| `backend-hpa.yaml` | HPA | `.Values.backend.autoscaling.enabled` | CPU + optionally memory Resource metrics |
| `daemon-statefulset.yaml` | StatefulSet | `.Values.daemon.enabled` | `replicas: 1` hardcoded with explanatory comment; ports webhook/metrics/health; startupProbe (up to 300s grace) on `/health`, then liveness/readiness; `volumeClaimTemplates: investigations` (10Gi, RWO, optional `storageClassName`) |
| `daemon-service.yaml` | Service | `.Values.daemon.enabled` | headless-style selector service for webhook/metrics/health |
| `llm-worker-deployment.yaml` | Deployment | `.Values.llmWorker.enabled` | backend image, command override to `services.worker` |
| `llm-worker-hpa.yaml` | HPA | `and llmWorker.enabled, llmWorker.autoscaling.enabled (not keda.enabled)` | CPU |
| `llm-worker-scaledobject.yaml` | ScaledObject + TriggerAuthentication | `and llmWorker.enabled, llmWorker.autoscaling.keda.enabled` | KEDA `redis` trigger: `listName: "arq:llm"`, `listLength: "5"`; address resolved per Redis mode |
| `agent-worker-deployment.yaml` | Deployment | `.Values.agentWorker.enabled` | agent image, **no command override** (image CMD); probes `/healthz` + `/readyz` on containerPort `6990` named `health`; comment: no Service — nothing routes to it |
| `agent-worker-hpa.yaml` | HPA | `and agentWorker.enabled, agentWorker.autoscaling.enabled (not keda.enabled)` | CPU |
| `agent-worker-scaledobject.yaml` | ScaledObject + TriggerAuthentication | `and agentWorker.enabled, agentWorker.autoscaling.keda.enabled` | KEDA redis trigger, `listName: "bull:agent-runs:wait"`, `databaseIndex` clamped to `vigil.redis.database` default `0` |
| `agent-serve-deployment.yaml` | Deployment | `.Values.agentServe.enabled` | agent image; `terminationGracePeriodSeconds: 120` |
| `agent-serve-service.yaml` | Service | `.Values.agentServe.enabled` | port 6989 |
| `postgres-statefulset.yaml` | StatefulSet | `and postgresql.enabled (not postgresql.bitnami.enabled)` | postgres:16-alpine; `fsGroup: 999`; `PGDATA=/var/lib/postgresql/data/pgdata`; readiness/liveness `pg_isready` exec probes; `volumeClaimTemplates: data` (50Gi, optional `storageClassName`) |
| `postgres-service.yaml` | Service | same | port 5432 |
| `redis-statefulset.yaml` | StatefulSet | `and redis.enabled (not redis.bitnami.enabled)` | redis:7-alpine; `args` from `redis.args`; `volumeClaimTemplates: data` (5Gi) |
| `redis-service.yaml` | Service | same | port 6379 |
| `splunk-statefulset.yaml` | StatefulSet + Service + Secret | `.Values.splunk.enabled` | dev utility; its own PVC honoring `splunk.persistence.storageClassName` |
| `pgadmin-deployment.yaml` | Deployment + Service + Secret | `.Values.pgadmin.enabled` | dev utility |
| `ssh-decoy-deployment.yaml` | Deployment | `.Values.sshDecoy.enabled` | backend image, `command: [python, -m, services.decoy.ssh_decoy]`; **no probes** (no HTTP surface); comment: no host ports/NodePort; reachability = Service + enforcement routing |
| `http-decoy-deployment.yaml` | Deployment | `.Values.httpDecoy.enabled` | backend image, `python -m services.decoy.http_decoy`; liveness+readiness `GET /health` on `decoys.ports.http` |
| `decoy-services.yaml` | Service ×2 | per-decoy `sshDecoy.enabled` / `httpDecoy.enabled` | ClusterIP on `decoys.ports.ssh` (2222) / `decoys.ports.http` (8080); comment: enforcement plane targets these; nothing exposes them outside the cluster |
| `db-init-job.yaml` | Job | `.Values.dbInit.enabled` | hooks `post-install,post-upgrade`, weight `-5`, delete-policy `before-hook-creation`; `backoffLimit: 3`, `ttlSecondsAfterFinished: 600`; runs uid **70** (postgres alpine), **`readOnlyRootFilesystem: true`**; psql loop over `.Values.dbInit.sqlFiles` with `_vigil_schema_versions` marker table, idempotent on upgrade (ghost-row handling for `--reuse-values` from 0.1.x); sets `vigil_app` role password from PGPASSWORD at the end |
| `db-init-configmap.yaml` | ConfigMap | `.Values.dbInit.enabled` | hook `pre-install,pre-upgrade`, weight `-10`; `(.Files.Glob "files/database-init/*.sql").AsConfig` — the 44 SQL files bundled in-chart |
| `enforcer-daemonset.yaml` | DaemonSet | `.Values.enforcer.enabled` (false by default — not rendered) | `hostNetwork: true` + `dnsPolicy: ClusterFirstWithHostNet` (XDP attaches to the node's NIC); uid 10002 (dedicated, non-root); `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, caps `drop: ALL` + `enforcer.capabilities.add`; three `hostPath` mounts (bpffs rw, cgroup ro, kernel BTF ro — `type: Directory` fail-loud scheduling); startup probe budgets 300s for BPF load, liveness/readiness `/healthz` on `enforcer.port`; env: `VIGIL_ENFORCEMENT_TOKEN` from the chart Secret, bind/interface/cgroup/TTL/sink from values; **no Service** (loopback-only API by design); checksum/secret annotation |

### Config, secrets, policy, observability

| Template | Kind(s) | Gate | Notes |
|---|---|---|---|
| `configmap.yaml` | ConfigMap | unconditional | Renders every `.Values.config` key, then computed-at-render keys (which win): `OTEL_EXPORTER_OTLP_ENDPOINT` (when `otelCollector.enabled`), `AGENT_URL` (when `agentServe.enabled`), `VIGIL_PLAYBOOKS_URL` / `VIGIL_PRICING_URL` / `VIGIL_RUNS_URL` / `VIGIL_TOOLS_URL` (when agent layer on), `DECOY_ENABLED: "true"` + `DECOY_INGEST_URL` + `DECOY_SESSION_TTL_SECONDS` (when either decoy on); `extraConfig` renders **last** (documented override path) |
| `secret.yaml` | Secret | `and (not secrets.existingSecret) (not secrets.externalSecret.enabled)` | Opaque; `POSTGRES_PASSWORD` is `required` when this template renders; ~30 optional keys via `with` |
| `externalsecret.yaml` | ExternalSecret | `secrets.externalSecret.enabled` | `external-secrets.io/v1beta1`; `secretStoreRef` name `required`; `creationPolicy: Owner`, `deletionPolicy: Retain`; `data` xor `dataFrom` |
| `ingress.yaml` | Ingress | `.Values.ingress.enabled` | `ingressClassName` from values; hosts/paths/tls passthrough; always routes to backend Service port 6987 |
| `networkpolicy.yaml` | **10 NetworkPolicies** | `.Values.networkPolicies.enabled` (top) | (1) `deny-all` — both policyTypes, egress allow-all with per-component lockdown below; (2) backend — ingress-controller namespace selector + in-namespace pods + kubelet probes on 6987; (3) daemon — `webhookAllowFrom` CIDRs + namespace-wide on webhook/metrics/health; (4) llm-worker — `ingress: []` (no inbound at all); (5) agent-worker — kubelet probes only on 6990; (6) agent-serve — backend-only ingress, plus optional probes-from-any-namespace rule (ingress rules OR, so that rule opens the port cluster-wide; default true because kubelet probes come from the node and CNI behavior varies — set false on Calico/Cilium); (7) postgres — allow backend/daemon/llm-worker/db-init/agent-worker/agent-serve (MVP mode only; comment points to Bitnami's own `networkPolicy.*` otherwise); (8) redis — allow backend/daemon/llm-worker/agent-worker; (9) ssh-decoy — **default-deny egress** with exactly two allows: daemon webhook port + kube-system DNS 53 UDP/TCP; (10) http-decoy — same containment contract |
| `serviceaccount.yaml` | ServiceAccount | `.Values.serviceAccount.create` | `automountServiceAccountToken` from values; annotations passthrough |
| `servicemonitor.yaml` | ServiceMonitor | `and daemon.enabled, observability.serviceMonitor.enabled` | `monitoring.coreos.com/v1`; scrapes daemon `/metrics`; comments warn it 404s unless `VIGIL_OTEL_ENABLED=true` and CRD is installed |
| `tests/test-connection.yaml` | Pod | unconditional | `helm.sh/hook: test`, delete-policy `before-hook-creation,hook-succeeded`; curlimages/curl; `GET /api/health/ready` on backend, plus daemon `/health` when enabled |

### Partials and output

- `_helpers.tpl` (353 lines): `vigil.name`, `vigil.fullname`, `vigil.chart`,
  `vigil.labels` (+ `app.kubernetes.io/part-of: vigil`),
  `vigil.selectorLabels`, per-component fullnames, `vigil.componentLabels`,
  `vigil.serviceAccountName`, **`vigil.image`** (component→image-suffix
  mapping: backend & llmWorker → `-backend`, daemon → `-daemon`, agentWorker &
  agentServe → `-agent`; llmWorker inherits backend repo/tag; tag falls back
  to `.Chart.AppVersion`), `vigil.imagePullPolicy`, `vigil.imagePullSecrets`,
  **three-mode Postgres resolvers** (`vigil.postgres.host/port/database/
  username/passwordSecret/passwordSecretKey` — Bitnami → MVP → external, with
  `required` failures for missing external host and missing password),
  **`vigil.redis.url`** (three modes; bitnami auth →
  `redis://:$(REDIS_PASSWORD)@<release>-redis-master:6379/0`),
  `vigil.redis.database` (hardcoded `0`, "one definition because three have to
  agree"), `vigil.redis.bitnami.passwordSecret(Key)`, `vigil.redis.urlFromSecret`.
- `_env.tpl` (153 lines): `vigil.envFrom` (ConfigMap + Secret refs),
  `vigil.stateEnv` / `stateVolumeMount` / `stateVolume` (`VIGIL_DIR` only
  where the volume mounts), `vigil.caBundleEnv` / `caBundleVolumeMount` /
  `caBundleVolume`, `vigil.env` (HOME, discrete `POSTGRES_HOST/PORT/DB` +
  `POSTGRES_USER: vigil_app` runtime login, Redis URL per mode incl.
  `REDIS_PASSWORD` secretKeyRef for Bitnami), `vigil.agentRedisEnv` (discrete
  `REDIS_HOST/PORT/DB` for agent pods — kubelet `$(VAR)` substitution can't
  URL-encode special chars).
- `NOTES.txt` (93 lines): post-install kubectl guidance, `helm test` hint,
  DEV_MODE warning, missing-Anthropic-key warning, Splunk/pgAdmin-without-
  DEV_MODE warning, and a **retired-env-name warning table** that must stay in
  step with `test_helm_env_names_are_read.py` (comment says exactly that).

## 7. CI — what runs, when, with what commands

Workflow files in `.github/workflows/`: `ci-cd.yml`, `helm-chart.yml`,
`medic.yml`, `nightly.yml`, `release-please.yml`, `release.yml` — plus
`enforcement.yml` ("Enforcement": gofmt/go vet/go test over
`services/enforcement` with a faked kernel interface) and `integrations.yml`
("Integrations": `pull_request` + `workflow_dispatch`), both landed
`ed94f2c9`; neither triggers on chart paths.

### 7.1 `.github/workflows/helm-chart.yml` — "Helm Chart"

**Triggers:** `push` to `main`/`develop` and all `pull_request`s, with path
filters `infra/helm/**`, `infra/database/init/**`, and the workflow file
itself. (A new `values-<cloud>.yaml` lands under `infra/helm/**`, so profile
PRs trigger this workflow automatically.)

**Job `lint` ("Lint and Template")** — helm **v3.15.2** via
`azure/setup-helm@v5`, on `ubuntu-latest`. Steps, in order:

1. **"Verify db-init SQL copies are in sync"** — `diff -r infra/database/init
   infra/helm/vigil/files/database-init --exclude=README.md`. The chart
   bundles its own copy of the init SQL because Helm can only read files
   inside the chart dir; drift means the chart would ship a different schema
   than the docker-compose stack.
2. **"Verify vendored chart dependencies"** — `cd infra/helm/vigil &&
   sha256sum -c SHA256SUMS`, then extract each `charts/*.tgz` for
   lint/template ("Helm 4 wants directories, not just tgz"). **No network
   I/O** — this step replaced the old `helm repo add` + `helm dependency
   update` fetch (with 30/60/120/240/300s Docker-Hub-429 backoff) when the
   subcharts were vendored in `39df634`.
3. **`helm lint` per discovered values profile** — a loop over every
   `infra/helm/vigil/values*.yaml`: `values.yaml` lints as the default
   variant (no `-f`); every other file (`values-dev.yaml` today, cloud
   profiles later) lints with `-f`. **This loop replaced two hardcoded steps
   (default, dev) in the `thunking/` foundation PR** so a profile PR is a pure
   file addition that its own CI validates.
4. **`helm lint` (Bitnami subcharts enabled)** — fixed variant, unchanged:
   `--set postgresql.enabled=false --set postgresql.bitnami.enabled=true
   --set redis.enabled=false --set redis.bitnami.enabled=true`.
5. **`helm template` per discovered values profile** — same loop, rendering
   each profile to `/tmp/manifest-<name>.yaml` with
   `--set secrets.anthropicApiKey=test-key` (the default variant additionally
   sets `secrets.postgresPassword=test-password`; profiles keep their own
   layering). Each manifest's rendered `kind:` count is echoed.
6. **`helm template` (Bitnami subcharts)** — fixed variant, unchanged.
7. **kubeconform v0.6.7** (downloaded from GitHub releases): a loop runs
   `./kubeconform -strict -ignore-missing-schemas -summary` on **every**
   `/tmp/manifest-*.yaml` — discovered profiles and the Bitnami variant alike.

**Job `chart-testing` ("chart-testing")** — `needs: lint`, `fetch-depth: 0`,
helm v3.15.2, Python 3.11, `helm/chart-testing-action@v2.8.0`, then:

```
ct lint --check-version-increment=false --skip-helm-dependencies --target-branch <default_branch> --chart-dirs infra/helm
```

`--skip-helm-dependencies` exists because subcharts are vendored: ct would
otherwise re-resolve them from Docker Hub, which rate-limits anonymous pulls
from runner IPs.

**That is the entire workflow.** There is no `ct install` (no kind cluster),
no `helm package`, no OCI push, no chart-repo publish, no helm-docs, no
release step.

### 7.2 `.github/workflows/ci-cd.yml` — "CI/CD Pipeline", job `test-helm-install-schema`

**Triggers:** `push` to `main`/`develop`, `pull_request` to `main`/`develop`,
`workflow_dispatch`. No path filters.

**Job:** gated `if: github.repository == 'Vigil-SOC/vigil'`. Provides a
`postgres:16-alpine` service container configured *as the chart's own Postgres
runs* (`POSTGRES_DB: deeptempo_soc`, `POSTGRES_USER: deeptempo`,
`POSTGRES_PASSWORD: test`) — the comment explains the other jobs run
`init_database()` as the DB owner and cannot see what a Helm install does;
there the db-init Job applies `dbInit.sqlFiles` as the chart user first, then
the backend runs `create_all` as `vigil_app` (which holds no REFERENCES), so a
new ORM table with an FK must come from a listed SQL file or 0.6.0's
"29 of 52 tables" failure repeats.

Steps: render the db-init Job from a copy of the chart with `dependencies`
stripped (`yq -i 'del(.dependencies)'` — subcharts are off by default, and
vendored, so no fetch needed); execute the rendered Job via
`docker run --user 70:70 --read-only` against the service Postgres; then
initialize schema as `vigil_app` (`DB_STRICT_SCHEMA: "true"`,
`init_database()`); assert every ORM table exists (SQLAlchemy introspection vs
`Base.metadata.tables`); assert default rows are seeded.

### 7.3 Packaging / publishing — there is none

- `helm-chart.yml`: lint/template/kubeconform/ct-lint only.
- `ci-cd.yml` `build-images`/`build-frontend`/`scan-images` build and push
  **container images** to ghcr.io, not charts.
- `release.yml` triggers on `vX.Y.Z` tags from release-please and builds
  images + GitHub release; zero helm mentions. release-please manages version
  bumps (hence `Chart.yaml` version == appVersion == 0.7.0).
- Consequence: **no Helm repository, no OCI artifact, no versioned chart
  downloads.** Every documented install is from the local checkout path.

### 7.4 Ratchet tests (unit suite, run by ci-cd.yml's pytest jobs)

- **`tests/unit/_ratchets/test_helm_db_init_sql_files.py`** — `dbInit.sqlFiles`
  in `values.yaml` must exactly equal (and be sorted like) the `.sql` files
  under `infra/database/init/`, and every entry must exist in the chart
  bundle. Docstring cites the 0.6.0 incident where
  `34_drop_skills.sql` / `34_mcp_credentials.sql` shipped bundled but never
  ran. (Count today: **44** — see Adaptation notes.)
- **`tests/unit/_ratchets/test_helm_env_names_are_read.py`** — static parse
  (no helm binary) asserting every `config`/`extraConfig` key the chart would
  render is actually read by *something* (Settings, integration secret
  descriptors, or an explicit `OTHER_CONSUMERS` map). **Discovers values files
  by glob over the chart directory** (`values*.yaml`, sorted, with a baseline
  guard pinning `values.yaml` + `values-dev.yaml` coverage) — this landed with
  the `thunking/` foundation PR; at survey time it parametrized an explicit
  two-file list, so new profile files were invisible to the ratchet. It also
  pins the `RETIRED` env-name map (echoed in `NOTES.txt`).
- Other tests touch helm-adjacent behavior (`tests/unit/test_support_bundle.py`,
  `tests/integration/test_migrate_schema_ownership.py`,
  `tests/unit/api/test_context_path.py`,
  `tests/unit/worker/test_worker_entrypoint.py`).

## 8. How the chart is consumed (docs + scripts)

- **Root `README.md` § "Install on Kubernetes"** is the canonical install:

  ```bash
  helm install vigil ./infra/helm/vigil \
    --namespace vigil --create-namespace \
    --set secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
    --set secrets.postgresPassword="$(openssl rand -hex 24)" \
    --set secrets.jwtSecretKey="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
  ```

- **Deployment docs now live in this repo** (`docs/deploy/`, imported in
  `d0d2a54`): `helm.md` (values reference), `helm-chart.md`,
  `helm-secrets.md`, `database-init.md`, `deployment.md`,
  `production-security.md`. The chart README links to
  `docs/deploy/helm-chart.md`. (At survey time the docs site was external;
  the in-chart comment links were repointed in `c8b4826`.)
- **Chart `README.md`** covers the vendored-subchart bump process and points
  to `thunking/` for cloud profiles (one line, added by the foundation PR).
- **Support bundle**: `scripts/vigil-support/vigil-support.sh --mode helm
  [--release NAME --namespace NS]` reads a live release for diagnostics —
  relevant for per-cloud support flows.
- `helm repo` usage appears only inside CI history (to fetch dependencies
  before vendoring). No user-facing helm-repo/OCI install path exists.

## 9. Where provider-specific overrides plug in

The chart was built with a **single-chart + values-layers** architecture: one
chart, multiple render variants tested in CI, three-mode Postgres and Redis
resolution in helpers, and passthrough blocks (`extraConfig`, `extraEnv`,
`annotations`, `secretStoreRef`) for everything site-specific. The decision
(**values profiles, not wrapper charts**) is recorded in the
[README decision log](README.md#decision-log); the reversal condition is there
too. The plug-in points each profile uses:

| Provider concern | Existing plug-in point (exact key) |
|---|---|
| EBS gp3 / Azure Disk (managed-csi) / GCE pd-balanced | `postgresql.persistence.storageClassName`, `redis.persistence.storageClassName`, `daemon.persistence.storageClassName`, `splunk.persistence.storageClassName` — all four PVC sites honor it (empty = cluster default). Volume sizes already value-driven |
| Ingress: ALB / Azure webapprouting+nginx / GCE | `ingress.className`, `ingress.annotations` (free-form), `ingress.hosts`, `ingress.tls`; plus `networkPolicies.ingressControllerNamespaceSelector` if the controller's namespace labels differ |
| Workload identity (IRSA / Azure WI / GKE WI) | `serviceAccount.annotations` (exists, currently unused); **but** `automountServiceAccountToken: false` and no cloud-token wiring today — profiles document this as a hook, not a default (see R8) |
| Secrets from cloud stores | `secrets.externalSecret.secretStoreRef{kind,name}` — ESO providers for AWS SM / Azure Key Vault / GCP SM are exactly the documented use |
| Region / cloud env | `config.AWS_REGION` exists; anything new goes via `extraConfig` (renders last, no chart fork) — but new `config.*` keys fail the env-name ratchet until code reads them |
| Image pulls | `global.imageRegistry` / `global.imageNamespace` / `global.imagePullSecrets` |
| Managed Postgres/Redis (RDS, Azure FW, Cloud SQL, ElastiCache) | The three-mode helpers already support external: `postgresql.external.*`, `redis.external.url` (+ `existingSecret`) |
| Node placement / spot | per-component `nodeSelector` / `tolerations` / `affinity` already on every workload |
| KEDA against external Redis | `llmWorker.autoscaling.keda.redisAddress` + `agentWorker.autoscaling.keda.{redisAddress,databaseIndex}` |

CI cost of a new profile: zero workflow edits — the discovery loop picks the
file up (§7.1); the env-name ratchet globs it in (§7.4).

## 10. Risks for per-provider profiles

- **R1 — `Chart.lock` shape — RESOLVED by pre-flight.** The single top-level
  digest is honored as-is by helm v3.15.2 (evidence in
  [README](README.md#pre-flight-helm-dependency-build-and-the-chartlock-digest-r1)).
  Profiles may rely on the pinned versions; do not reintroduce a CI
  `dependency build` step (it re-fetches from Docker Hub).
- **R2 — Docker Hub rate limits — retired for chart CI by vendoring
  (`39df634`), still live for *image* pulls.** The seven support images
  (`postgres:16-alpine`, `redis:7-alpine`, `splunk/splunk:latest`,
  `dpage/pgadmin4:latest`, `curlimages/curl:8.10.1`,
  `otel/opentelemetry-collector-contrib`, Bitnami subchart images) come from
  Docker Hub at deploy time. Profiles document per-cloud pull-through caches
  (ECR/ACR/Artifact Registry) as commented hooks; the two `latest`-tag dev
  images are a flagged follow-up, not pinned here.
- **R3 — env-name ratchet scope — RESOLVED by glob.** The ratchet now scans
  every `values*.yaml` automatically (§7.4). A profile coining a new
  `config.*` key fails until code reads it — intended.
- **R4 — `dbInit.sqlFiles` couples profiles to the base values.** The SQL list
  lives in `values.yaml` and a Job renders from it; `helm -f` layering
  replaces whole keys, so a profile that redefines `dbInit` at all must
  redefine the complete 44-file list. Rule for profiles: never set `dbInit.*`
  (enforced by the db-init SQL ratchet if violated).
- **R5 — `helm upgrade --reuse-values` semantics.** The db-init Job's comment
  block documents ghost `_vigil_schema_versions` rows surviving
  `--reuse-values` from 0.1.x. Profile rollout guidance should prefer explicit
  `-f` layering over `--reuse-values`.
- **R6 — kubeconform runs `-strict`.** Cloud-profile renders add
  annotations/labels (ALB annotations, Azure/WI SAs) — fine for standard
  kinds; field-level typos in standard kinds fail. Annotations are free-form
  strings, so semantic mistakes (wrong class name, wrong namespace selector)
  will **not** be caught — that is what the per-cloud render-evidence counts
  are for.
- **R7 — StorageClass emptiness is the default contract.** Every PVC site
  ships `storageClassName: ""` (cluster default). On a fresh managed cluster
  the default class is provider-specific and block (RWO) storage; nothing here
  needs RWX, but `stateDirectory` stays `emptyDir` unless an operator has an
  RWX class — profiles say so explicitly instead of implying persistence.
- **R8 — Workload identity is not wired.** Cloud identity is currently static
  keys (`secrets.awsAccessKeyId/SecretAccessKey`) or ESO. `serviceAccount.create`
  exists with `annotations: {}` but `automountServiceAccountToken: false` and
  no token-volume/audience wiring anywhere in templates. Provider profiles
  that promise IRSA/Workload Identity need template work, not just values —
  this is the one place values profiles are not purely declarative, and why
  identity ships as a documented hook.
- **R9 — No chart publishing pipeline.** If the team ever wants
  `helm install vigil oci://...`, that infra must be built from zero (§7.3).
  Values profiles are unaffected.
- **R10 — Secrets templating is plain-string.** `secret.yaml` renders
  `stringData` from values unless `existingSecret`/ESO is set, and
  `secrets.postgresPassword` is `required`. Profiles ship the ESO /
  existingSecret pattern as their documented *first-class* credential story so
  users don't `--set` secrets into shell history (the `--set` flags in the
  header are the minimal path; the notes flag the tradeoff).

## 11. Corrections to prior working assumptions

Kept from the source research (all verified again at `c8b4826`):

1. **"Vendored subcharts under `charts/`"** — false at survey time, **true
   since `39df634`**: the tgz files are committed and checksummed; CI verifies
   and extracts them instead of fetching (§3.3, §7.1).
2. **"Enforcement workflow"** — none existed at survey time; **`ed94f2c9`
   added `.github/workflows/enforcement.yml`** (plus `integrations.yml`).
   The original observation — grep over the `f5b3153`/`c8b4826` tree
   returning nothing — was correct for its tree.
3. **"Enforcer DaemonSet" / `services/enforcement/`** — neither existed at
   survey time; **both exist since `ed94f2c9`** (`enforcer-daemonset.yaml`,
   opt-in behind `enforcer.enabled: false`, §6). The enforcement/deception
   plane is the SOC daemon (StatefulSet), the two decoy Deployments, their
   Services, the decoy-containment NetworkPolicies with locked default-deny
   egress — plus, now, the opt-in enforcer DaemonSet. Still **no PDB
   templates**.

New corrections found during adaptation (survey said → tree says):

4. **"42 SQL files" → 44.** `infra/database/init/` and the chart bundle both
   hold **44** `.sql` files, and `dbInit.sqlFiles` lists 44 (verified by count
   and by the CI `diff -r` parity step). The survey artifacts' "42" was a
   miscount; no SQL file changed between `f5b3153` and `c8b4826`.
5. **"External docs site" → in-repo docs.** `docs/deploy/*.md` exist since
   `d0d2a54`; the chart README and in-chart comments point at them.
6. **"Env-name ratchet is an explicit two-file list" → glob discovery** (this
   PR; §7.4).

## Adaptation notes

- **Source:** artifact _"Research: Vigil Helm chart anatomy + CI"_
  (survey at `f5b3153`, 2026-10-10). Spec verification against `5628e17` found
  the intervening commit touching API/digital-twin code only; this adaptation
  additionally re-read the chart paths at `c8b4826` and re-verified every
  count used above (values.yaml 1017 lines / 30 keys, templates 32 YAML,
  SQL 44, deps 3). **Re-survey at `b28bc372`:** the `ed94f2c9` enforcer
  commit added the `enforcer:` values block (1017 → 1093 lines, 30 → 31
  keys), `enforcer-daemonset.yaml` (31 → 32 top-level templates),
  `secrets.enforcementToken`, `DAEMON_ENFORCEMENT_FORCE_APPROVAL`, the
  `vigil.enforcer.fullname` helper + `-enforcer` image mapping, and the
  `enforcement.yml`/`integrations.yml` workflows — §4, §6, §7, and §11 were
  re-read from the working tree at `b28bc372` and updated in place.
- **Rewritten for the current tree:** §2 layout (SHA256SUMS, vendored charts),
  §3.2–3.3 (digest verification practice + bump process), §7.1 (vendored
  verify step; discovered-profile lint/template/kubeconform loops replacing
  the fixed three-variant lists), §7.4 (globbed ratchet), §8 (in-repo docs).
- **Facts carried verbatim from the survey session** (file reads on
  `cmp_Nl9HhODo`): the values-key table, template inventory, helper/NOTES
  details, ci-cd schema-job flow, and the risk register. Where the tree has
  drifted, the drift is stated inline and in §11 — nothing was silently
  updated.
- **Provider-string verification** (storage classes, LB annotations, identity
  annotations) is deliberately NOT in this file — it lives in
  [cloud-touchpoints.md](cloud-touchpoints.md) with its own source trail.

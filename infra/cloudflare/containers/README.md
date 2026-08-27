# Python tier on Cloudflare Containers

`python-tier.json` is the topology: which Python processes run as Cloudflare
Containers, from which image, on which ports, with what lifecycle, and what they
depend on that is *not* a Container. Deploy tooling renders wrangler config from
it; `tests/unit/infra/test_cloudflare_python_tier.py` asserts it against the
Dockerfiles and `env.example` so the file cannot quietly drift from the repo.

Nothing here deploys anything. The wrangler config, Hyperdrive binding, secrets
and routes are the deploy half of workstream F.

## What runs as a Container

| Container | Image | Instances | Why that shape |
|---|---|---|---|
| `vigil-api` | `Dockerfile.backend` | up to 5 | Stateless FastAPI. Scales with request volume, sleeps when idle. |
| `vigil-daemon` | `Dockerfile.daemon` | exactly 1 | One process: three unbounded loops, the Splunk/CrowdStrike pollers, the sandbox submit/poll cycle, and the Kafka consumer-group member. |
| `vigil-llm-worker` | `Dockerfile.backend` | up to 3 | ARQ worker draining the Redis queue the API writes to (`python -m services.worker`). |

The daemon is **re-hosted, not decomposed**. Its loops share in-process state and
a single Kafka consumer-group seat; splitting them into per-loop containers would
mean either double-polling every source or inventing a coordination layer that
does not exist today. The Containers equivalent of the legacy single-replica
StatefulSet is `max_instances: 1`, and the manifest test enforces it.

The LLM worker is in this manifest even though the brief named only the API,
daemon and Kafka consumer: the API enqueues every LLM request onto Redis, so an
API container with nothing draining that queue accepts work it never completes.
It is listed as its own class rather than folded into the API because a queue
consumer and an HTTP surface scale on unrelated signals — the same split compose
and the chart already make.

## What stays outside Containers

Postgres, Redis and Kafka are **not** Containers, and this is a platform
constraint rather than a preference:

- Clients cannot open non-HTTP TCP or UDP connections to a Container. Every
  request enters through a Worker, so nothing can speak the Postgres or Redis
  wire protocol to one.
- Container disk is ephemeral. A stopped instance restarts with a fresh disk
  from its image, which is disqualifying for a database's data files.

So they run as managed services with outbound reachability from the Python tier
(and, for Postgres, from the edge via Hyperdrive). Postgres must ship pgvector:
`findings.embedding` is `vector(768)` with an HNSW index, which the stock
`postgres:16` image cannot serve. Kafka is normally the customer's own broker and
Vigil is only a consumer-group member, so it needs outbound connectivity and
nothing else — no inbound listener, which is precisely why that workload survives
the move.

## Daemon workdir: still open

The legacy daemon mounts a 10Gi ReadWriteOnce PVC at
`/app/data/investigations` (`ORCHESTRATOR_WORKDIR`). Containers have no PVC
equivalent, and the manifest keeps both honest options selectable:

- `ephemeral-disk` (current default) — the instance disk. Fast, sized by
  `instance_type`, and gone on restart.
- `r2-fuse` — an R2 bucket mounted over FUSE. Durable, and explicitly not
  SSD-speed.

Which one ships depends on the `stateDirectory` inventory (spec open question 2).
If everything under the workdir is in-flight investigation artifact that a
restart can rebuild, `ephemeral-disk` is correct and cheaper. If any of it is the
only copy of something, `r2-fuse` is required and the throughput cost is the
price of not losing it. Until that inventory exists, treating this as decided
would be guessing with customer data.

## Keeping background work awake

Container instances sleep after an inactivity timeout, and only *request*
activity renews it. The API is fine — every call is activity. The daemon and the
LLM worker serve no traffic between events, so the Worker must ping the daemon's
health port on a cron trigger at an interval shorter than `sleep_after`. Without
that ping the loops stop at the timeout and resume only on the next inbound
webhook, which looks exactly like a silently broken poller.

## Telemetry

Traces go to an external OTLP endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT`, with
protocol, headers and insecure-mode knobs). There is no in-cluster collector to
fall back on. The compose `observability` profile — collector, Jaeger,
Prometheus, Grafana — is local development only.

## Verifying a change

```bash
# manifest agrees with the Dockerfiles, env.example, and loads both entry points
python -m pytest tests/unit/infra -q

# images: lint, build, scan, and load each entry point (what CI does)
hadolint infra/docker/Dockerfile.backend infra/docker/Dockerfile.daemon
docker build -f infra/docker/Dockerfile.daemon -t vigil-daemon:local .
trivy image --severity CRITICAL --ignore-unfixed --exit-code 1 vigil-daemon:local
```

Images build from the **repo root**: both Dockerfiles `COPY core/`, `services/`
and `mempalace/`. That is why CI builds and pushes them and wrangler is handed a
fully-qualified image reference, instead of pointing `image` at a Dockerfile
path whose implicit context could not satisfy those lines.

# Medic

The ops-health watcher for a Vigil install (program name: System Watcher). It
watches the install's own health — is the daemon responding, is the pipeline
moving — not security alerts. Phase 0 is observe-only: no fixes, and nothing
leaves the site.

Medic is **off by default**. `VIGIL_MEDIC_ENABLED=true` turns it on; anything
else and `run` logs why and exits 0. A SOC that wants no watcher should get
exactly that.

```
python -m services.medic run     # the service: heartbeat loop + watchdog
python -m services.medic check   # exit 0 only if the heartbeat is fresh (< 120 s)
```

| Setting | Default |
|---|---|
| `VIGIL_MEDIC_ENABLED` | off |
| `VIGIL_MEDIC_DATA_DIR` | `/var/lib/vigil-medic` (macOS: `/Library/Application Support/vigil-medic`) |

## Where it lives

| Piece | Path | What it is |
|---|---|---|
| Service | `services/medic/` | The whole program — a standalone service, not part of `core` |
| Contracts | `services/medic/contracts/` | Schemas, fixtures, evaluation vectors, reference implementations and their tests |
| Sensors | `services/medic/sensors/` | The sensor framework: scheduling, timeouts, redaction, writing |
| Store | `services/medic/store/` | The decision store: one SQLite file, one writer, one hash chain |
| Image | `infra/docker/Dockerfile.medic` | The container build |

## Isolation

Medic imports nothing from `core`, `tools` or any other service, and has its
own `pyproject.toml` and `uv.lock`; `.importlinter` enforces the first. Its
runtime dependencies go in this `pyproject.toml` only, never in the repo's
requirements. If `uv.lock` conflicts after a merge, re-run
`uv lock --project services/medic` rather than hand-merging.

The point of the fence: the watcher must keep working when the watched thing
is what broke. Code that shares a venv and an import graph with the system it
watches fails with it.

## Sensors: read one thing, return what it saw

A sensor **reads one thing and returns what it saw**. The framework
(`sensors/`) does everything else: scheduling, timeouts, ids, timestamps,
`sensor_health`, redaction, schema checks, and writing — see
`services/medic/SENSOR_AUTHORING.md` for the authoring guide.

```python
@dataclass
class MySensor:
    id: str = "daemon_health"        # stable across restarts
    service: str = "soc-daemon"
    interval_s: int = 30             # one of 30, 60, 300, 21600 — fixed
    timeout_s: float = 5.0           # hard cap per collect(); < interval_s
    covers: tuple[str, ...] = ("daemon_health",)
    uses_vigil_api: bool = False     # True reads Vigil's API via the gateway

    async def collect(self, ctx: SensorContext) -> Sequence[Reading]: ...
```

The distinction that matters is **result vs error**:

- **The source answered, even if it said "down": that's a result.** 503,
  connection refused and "0 records" are results. Results never back off.
- **Medic couldn't make the read: that's an error** — `timeout`, `refused`,
  `dns`, `tls`, `http_status`, `auth`, `parse`, `too_large`, `not_installed`,
  `other`. Three error cycles in a row read `blind`, and then the scheduler
  backs off (×2 up to 4 × interval, ≤ 5 min).

`ReadError.detail` is untrusted text: keep it short (≤ 500 chars after
redaction), and never put a response body, a traceback or a Docker `inspect`
body in it.

### The redaction choke point

`collect()` returns `Reading`s; the framework stamps ids, times, target shape
and `sensor_health`, runs the redaction choke point, validates against
`contracts/observation.schema.json` and only then writes to the sink
(`services/medic/sensors/base.py`). Redaction is not a step a sensor can
forget: every observation passes through it by construction, on the way to a
sink that accepts only redacted, schema-valid observations.

## Decision records: a hash chain, not a log file

The decision store (`services/medic/store/writer.py`) is one SQLite file, one
writer, one hash chain. Every write goes through one `DecisionWriter`, which
holds `medic.lock` for the life of the process and appends inside
`BEGIN IMMEDIATE` — nothing can slip a record in between reading the head and
writing the next one. Sealing and verifying are the contract's own code
(`services/medic/contracts/decision_chain.py`), not a copy, so the store's
hashes are the contract's by construction.

Canonical form: JSON with keys sorted, no whitespace, UTF-8, integers only
(the schema forbids floats) — the same as RFC 8785 (JCS) output for these
records. `incident_id` is deterministic: replaying a recording gives the same
ids, minted once when the incident opens; a flapping reopen keeps the stored
id even though its new `active_since` would hash differently.

The chain is what makes Medic's "no fixes" phase auditable: what the watcher
*decided* (open an incident, route it to a lane, what each autonomy level
would have done — `services/medic/contracts/lane_ref.py`) is a sealed
sequence anyone can re-verify offline.

## Contracts are the spec

`services/medic/contracts/` holds the schemas, fixtures, evaluation vectors,
reference implementations and their tests. They are the spec: a vector or
schema that looks wrong is a contract change, made in its own PR, never a
code workaround.

## Tests and lint

One command, from the repo root:

```
UV_PROJECT_ENVIRONMENT=../../.venv uv run --project services/medic pytest services/medic
```

It runs the contract tests (`contracts/tests/`) and Medic's own (`tests/`).
The venv goes in the repo root's `.venv` — left in `services/medic/.venv`, the
repo's ratchet tests, which scan every `.py` file under `services/`, would
read the venv's site-packages.

Lint, the same as the `medic-contracts` CI job:

```
UV_PROJECT_ENVIRONMENT=../../.venv uv run --project services/medic ruff check services/medic
UV_PROJECT_ENVIRONMENT=../../.venv uv run --project services/medic ruff format --check services/medic
UV_PROJECT_ENVIRONMENT=../../.venv uv run --project services/medic lint-imports
```

CI for Medic is its own path-filtered workflow — see
[`github-workflows.md`](develop/github-workflows.md).

## Deployment

`infra/docker/Dockerfile.medic`: Medic's venv from its lock, no `core`, uid
and gid 10001, read-only root filesystem, `HEALTHCHECK` running `check`.
Mount the data volume at `/var/lib/vigil-medic`.

```
docker build -f infra/docker/Dockerfile.medic -t vigil-medic .
```

The `check` command is the container's liveness: exit 0 only if the heartbeat
is fresh (< 120 s), so an orchestrator restarts a Medic that stopped
heartbeating.

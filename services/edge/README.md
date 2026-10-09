# Vigil Edge Daemon (Local Autonomy Mesh)

A standalone daemon that keeps defending its network segment with
pre-distributed, operator-signed policy bundles while Vigil's central control
plane is unreachable — then reconciles everything when it returns. The SLM
advises; the deterministic gate decides.

Like Medic, this package **imports nothing** from `core`, `tools` or any other
service, and has its own `pyproject.toml` and `uv.lock`; `.importlinter` (the
`edge` contract) enforces the first. Edge nodes are untrusted relative to the
control plane: the blast radius is bounded by construction.

## Running

```sh
uv sync --project services/edge
uv run --project services/edge python -m services.edge
```

Off by default: with `VIGIL_EDGE_ENABLED` unset or false, the entry point
prints the reason and exits 0. When enabled it needs `VIGIL_EDGE_NODE_ID` and
fails closed otherwise. The full env set is documented in the repo root's
`env.example` under "Edge daemon (services/edge)"; thresholds and caps are
deliberately absent from the environment — they live in the signed bundle.

## Layout

| Path | Role |
| --- | --- |
| `app/daemon.py` | The defense loop; lazy component init, the SOCDaemon pattern |
| `app/config.py` | `VIGIL_EDGE_*` parsing (pure functions over a mapping) |
| `app/states.py` | The four operating states and their allowed transitions |
| `app/health.py` | `GET /health` on `VIGIL_EDGE_HEALTH_PORT` |
| `gate/` | Tier bands and the deterministic decision gate |
| `policy/` | The signed bundle model, DSSE verification, and the cache |
| `journal/` | The append-only, hash-chained local record |
| `observations/` | Pluggable input adapters (v1: Suricata EVE JSON-lines tail) |
| `executors/` | The executor interface and registry (implementations land with the executors deliverable) |

## Tests

```sh
uv run --project services/edge pytest services/edge
```

The isolation fence (`tests/test_isolation.py`) runs the real
`lint-imports` against a planted `import core` to prove the contract breaks.

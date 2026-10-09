# Vigil — Agent Guidance

Vigil SOC: an open-source, agentic AI SOC. Plain-Markdown workflows, readable agent
code, MCP integrations. Four runtimes cooperate: a Python/FastAPI backend, a
React/Vite web console, a TypeScript agent layer, and Python workers, over
PostgreSQL and Redis. The Bifrost LLM gateway fronts all model traffic.

## Stack

| Part | Tech | Port | Source |
|---|---|---|---|
| API backend | Python 3.12 (uv-pinned), FastAPI + uvicorn | 6987 | `services/api/`, `core/`, `tools/` |
| Web console | React 18 + Vite (Node 20+) | 6988 | `clients/web/` |
| Agent layer | TypeScript under tsx (Node 20+), BullMQ | worker 6990, serve 6989 | `services/agent/` |
| LLM worker | Python ARQ consumer | — | `services/worker/` |
| SOC daemon (optional) | Python, headless automation | 9091 | `services/daemon/` |

External services: **PostgreSQL** (required), **Redis** (required — LLM job queue +
session store), **Bifrost** LLM gateway (LLM traffic only; the UI runs without it),
**Ollama** (optional, host-native).

## This environment (snapshot)

Docker is NOT installed in this sandbox. Postgres 17 and Redis run natively:

- Postgres: `sudo pg_ctlcluster 17 main start` — role `deeptempo`, password from
  `.env`, database `deeptempo_soc` on localhost:5432. Requires the `pg_trgm`
  extension (`postgresql-contrib`) — `scripts/init_schema.py` builds GIN
  trigram indexes and fails without it.
- Redis: `sudo redis-server --daemonize yes` on localhost:6379.
- Bifrost is not running (it ships only as a container image). Expected symptom:
  `GET /api/bifrost/routability` returns 502 and provider widgets error. Nothing
  else depends on it at boot.

## Commands

```bash
# One-time setup (creates .env, JWT secret, uv venv, all deps, frontend node_modules)
./setup_dev.sh

# Start everything — needs Docker for postgres/redis/bifrost:
./start.sh -d          # background; also runs the SOC daemon
./start.sh             # foreground

# Without Docker (this sandbox), start pieces by hand after Postgres+Redis are up:
source venv/bin/activate
set -a; source .env; set +a; export PYTHONPATH="$PWD"
export JWT_SECRET_KEY="$(cat ~/.vigil/jwt_secret)"
python scripts/init_schema.py && python scripts/seed_reference_data.py
uvicorn services.api.main:app --host 127.0.0.1 --port 6987 &
python -m services.worker &            # ARQ LLM worker
scripts/agent_up.sh                     # agent worker + serve, healthz :6990/:6989
(cd clients/web && npm run dev)         # Vite on 6988 (port fixed in vite.config.ts)

# Stop
./shutdown_all.sh                       # native procs; -d also stops containers
```

Backend port is 6987 and frontend 6988 — both are hard-coded (start.sh, vite.config.ts),
not defaults guessed by convention. API docs at http://localhost:6987/docs.

## Environment

- `.env` from `env.example`. `AGENT_INTERNAL_TOKEN` must be set (any generated
  token) or workflow runs stay queued — the agent layer's `/internal` calls 503.
- JWT secret auto-mints to `~/.vigil/jwt_secret` (or `$VIGIL_DIR`). A `.env`
  `JWT_SECRET_KEY` wins over the file.
- `VIGIL_COOKIE_SECURE=true` (env.example default) breaks login over plain HTTP.
  Local HTTP dev sets `VIGIL_COOKIE_SECURE=false` in `.env`.
- `DEV_MODE=true` bypasses auth entirely (local only; the backend warns loudly).
- First run has NO users: `GET /api/auth/bootstrap` → `{"required": true}`, the
  UI shows a bootstrap screen, or `POST /api/auth/bootstrap` with
  `{username, email, password}` creates role-admin. Email validator rejects
  reserved TLDs (`admin@vigil.local` fails; use a real-looking domain).
- Mutating API calls need CSRF double-submit: echo the `csrf_token` cookie as
  the `X-CSRF-Token` header. Exempt: `/api/webhooks/`, `/api/ingest/`, `/mcp`,
  `/internal` (bearer `AGENT_INTERNAL_TOKEN`).

## Verification

```bash
source venv/bin/activate
pytest tests/unit tests/security -m "not external_service"   # CI invocation; TESTING=true
flake8 services/ core/ && black --check services/ core/ && isort --check-only services/ core/
mypy services/ core/ --ignore-missing-imports                # non-gating in CI (lint job)
(cd clients/web && npm run lint)                             # 7 pre-existing errors on main
(cd services/agent && npm run typecheck)
pytest tests/integration -m "not external_service"           # needs live Postgres/Redis
```

Pitfall: do not `source .env` into a pytest run — the DAEMON_*/REDIS/DATABASE
vars the test suite reads live flip 4 tests to red (see SKILL.md). Run pytest
with a clean shell exporting only `TESTING=true` and `PYTHONPATH`.

## Codebase map

See [codebase-map.md](codebase-map.md).

## Snapshot

- snapshotId: `93ga2d2vjyi2gk0rs8hb:default`
- captured: 2026-10-09T20:29:16Z (dev stack running and verified at capture time)

---
name: local-dev
description: How to bring Vigil's dev stack up in this sandbox, and what bites
---

# Local dev — Vigil SOC (recorded during onboarding, 2026-10-09)

## Environment facts (this snapshot)

- **No Docker.** Postgres 17 and Redis 8 run natively (Debian 13, installed via apt).
  - Postgres: `sudo pg_ctlcluster 17 main start`; role `deeptempo` / db `deeptempo_soc`
    / password from `.env` (`deeptempo_secure_password_change_me`), port 5432.
  - Redis: `sudo redis-server --daemonize yes`, port 6379.
- Python 3.12 is NOT system Python (system is 3.13). It is provisioned by uv into
  `venv/` from `.python-version` — always `source venv/bin/activate`.
- Node 20 system-wide; frontend deps in `clients/web/node_modules`, agent deps in
  `services/agent/node_modules`.
- Bifrost is not running (container-only). `/api/bifrost/routability` 502s in the
  console are expected and harmless.

## First-run setup that worked here

1. `cp env.example .env` — then set `AGENT_INTERNAL_TOKEN` to a generated token
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Without it the
   agent layer's /internal calls 503 and workflow runs never start.
2. `VIGIL_COOKIE_SECURE=false` in `.env` — the env.example default `true` breaks
   login over plain HTTP (the browser drops the auth cookie).
3. `sudo apt-get install postgresql postgresql-contrib redis-server` — the contrib
   package matters: `scripts/init_schema.py` creates `gin_trgm_ops` indexes and
   fails with `UndefinedObject` without the `pg_trgm` extension. Create it with
   `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in `deeptempo_soc` if needed.
4. `CREATE ROLE deeptempo LOGIN PASSWORD '...';` + `createdb -O deeptempo deeptempo_soc`.
5. `./setup_dev.sh` (creates .env if missing, mints JWT secret to `~/.vigil/jwt_secret`,
   installs uv + Python 3.12 venv + requirements.lock + dev deps + frontend npm).
   It skips its Docker DB section when docker is absent — fine, DB is native here.
6. `python scripts/init_schema.py && python scripts/seed_reference_data.py`
7. Start in order: `uvicorn services.api.main:app --host 127.0.0.1 --port 6987` →
   `python -m services.worker` → `scripts/agent_up.sh` (waits on :6990/:6989 healthz) →
   `cd clients/web && npm run dev` (Vite binds 127.0.0.1:6988).
8. Check: `curl http://127.0.0.1:6987/api/health` → `{"status":"healthy",
   "storage":{"backend":"postgresql","database_available":true},"schema":{"state":"ok"}}`.

## Gotchas learned the hard way

- **First run has no users.** Bootstrap the admin via the UI screen or
  `POST /api/auth/bootstrap {username, email, password, full_name}`. The email
  validator rejects reserved TLDs — `admin@vigil.local` is a 422; use a normal domain.
- **CSRF double-submit** on all mutating API calls: GET seeds a `csrf_token`
  cookie; echo it as `X-CSRF-Token`. Exempt: /api/webhooks/, /api/ingest/, /mcp, /internal.
- **pytest vs .env:** do not export .env into a pytest shell. DAEMON_* / REDIS_URL /
  DATABASE_URL in the environment flip 4 tests (token-rotation, daemon intent,
  integrations config) to red even though the suite is green in CI. Clean env +
  `TESTING=true` + `PYTHONPATH=$PWD` is the correct invocation.
- **`./start.sh` requires Docker** (`ensure_docker` exits 1). Without Docker, start
  pieces by hand per above.
- Frontend and backend ports (6988/6987) are hard-coded in start.sh and
  clients/web/vite.config.ts; the Vite dev server proxies /api to 127.0.0.1:6987.
- After first login the SetupGate routes to /setup until localStorage
  `vigil.setupDismissed` is set ('1'); the wizard's own button writes it.

## Verification performed (2026-10-09)

- flake8 / black / isort: clean (exit 0; black 470 files unchanged).
- mypy `services/ core/ --ignore-missing-imports`: 325 pre-existing errors — the
  CI lint job runs this non-gating (continue-on-error).
- `pytest tests/unit tests/security -m "not external_service"`:
  4005 passed / 11 skipped / 4 env-contamination failures (green with clean env).
- `npm run typecheck` in services/agent: clean.
- Frontend `npm run lint`: 7 pre-existing errors in two test files
  (`CommandBar.test.tsx`, `SocConsole.test.tsx` — unused `_args`/`_permission`);
  present on main before onboarding, untouched here.
- Browser (Playwright headless): login screen renders → API login 200 →
  dashboard /home renders (nav, "Get Vigil ready" checklist) → /cases renders.
  Screenshots: /tmp/shot/01-login.png, 02-dashboard.png, 03-cases.png.
- CRUD round-trip: case created (`case-2026-10-09-aaea8378`) and listed via the API.

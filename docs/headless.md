# Running Vigil headless

Vigil is built to be operated by software. This guide takes an empty instance to
a working MCP credential and a driven workflow run without opening a browser:
boot with `--headless`, onboard with one script, connect an MCP client, drive
the run.

Booting headless removes nothing — the console stays available for whoever
wants it. What changes is that nothing *requires* it: startup, first-run
bootstrap, credential minting, and every operational function are reachable
from a shell or an MCP client.

## What `--headless` changes

The console is already optional: the backend serves the built SPA only when a
build directory exists, and mounts its own MCP server at `/mcp` before the SPA
catch-all. The only interactive parts of a dev boot are the Vite dev server on
:6988 and the browser auto-open. `--headless` skips exactly those two things
and changes what the ready banner points at. Everything else — API, worker,
agent layer, daemon — is unchanged.

## Dependency floor

| Tier | Requirement | Without it |
|---|---|---|
| Hard | PostgreSQL | the API has nothing to serve; schema init fails |
| Hard | JWT signing secret | the backend refuses to start (auth is on). `start.sh` creates one at `~/.vigil/jwt_secret` |
| Agentic | Redis | the run queue is down — runs are never enqueued |
| Agentic | `services/worker` (ARQ) | every LLM call is an ARQ job; none execute |
| Agentic | Agent layer (Node ≥ 20) + `AGENT_INTERNAL_TOKEN` | a run is accepted, reported queued, and never picked up; every `/internal` call answers 503 |
| Provider-dependent | Bifrost | Anthropic traffic has no route; see the LLM provider note below |
| Optional | Console (Vite / built SPA) | skipped by `--headless` by definition |
| Optional | Ollama | local LLM provider |
| Optional | SOC daemon | scheduled and autonomous operations |
| Optional | Profiled services | `splunk`, `kafka`, `pgadmin`, `jaeger`, `prometheus`, `grafana`, `otel-collector` |

**LLM provider.** A run's agents need a model: Anthropic (default), OpenAI,
Google Vertex, or Ollama (local, no key). With no provider key at all,
`scripts/local_model.sh` serves a small local model Bifrost can reach and
prints the model id to use. A headless install that never starts runs needs no
provider — everything else in this guide works without one.

## Boot headless

```bash
./start.sh --headless          # foreground
./start.sh --headless -d       # background: logs/ + pidfiles, also the SOC daemon
SKIP_FRONTEND=1 ./start.sh -d  # same state from the environment instead of the flag
```

`--headless` outranks everything, including a `SKIP_FRONTEND=0` in `.env` —
useful when the .env was written for a console install and the host now boots
unattended. The inverse override also exists: `SKIP_FRONTEND=1` in `.env`
makes a persistent install console-free without per-boot flags.

Before launching anything, the headless boot **warns loudly and continues** —
it never aborts, because a daemon-only deployment without an agent layer is
legitimate — when:

- `AGENT_INTERNAL_TOKEN` is empty — workflow runs cannot start: every
  `/internal` call answers 503 and nothing drains the agent-runs queue. The
  warning prints the one-liner that generates a token.
- `VIGIL_MCP_ENABLED` is not `true` — the `/mcp` endpoint is disabled and MCP
  clients have no surface to connect to.

When it is ready, the banner points at onboarding and the MCP endpoint instead
of the console URL:

```text
Vigil SOC v0.7.0 - Ready
Headless: no frontend, no browser auto-open
Backend:  http://localhost:6987
MCP:      http://localhost:6987/mcp
Docs:     http://localhost:6987/docs

First run: mint an MCP credential without a browser:
  VIGIL_BOOTSTRAP_ADMIN_PASSWORD='<password>' ./scripts/headless_onboard.py
```

Stop with `./shutdown_all.sh` (add `-d` to also stop the containers' data
keeping; see `./shutdown_all.sh --help`).

## Fresh installs: schema and reference data

The canonical headless path is `./start.sh`. In one boot it applies the schema
(`scripts/init_schema.py`), seeds reference data
(`scripts/seed_reference_data.py`), and starts the stack.

The seed step matters and is easy to miss on a hand-provisioned host: the SQL
files under `infra/database/init/` are applied by the Postgres initdb step,
which runs *before* the backend's `create_all` has built the tables they
target — so on a fresh database those rows never land there.
`scripts/seed_reference_data.py` re-applies them after the schema exists; that
is where the role rows the first-run bootstrap assigns come from.

> **A fresh install that runs only `scripts/migrate_schema.py` gets tables but
> no reference rows.** The first-run bootstrap then fails with a foreign-key
> violation when it assigns the admin role. If you manage the schema by hand,
> run `scripts/init_schema.py` and then `scripts/seed_reference_data.py` —
> both are idempotent — or simply boot with `./start.sh`, which does both.

No default admin is seeded; the operator account is created by bootstrap in the
next step. If the database already has data, neither script re-seeds anything
that exists.

## Onboard: empty instance to MCP credential

One idempotent, non-interactive command chains the four HTTP calls: bootstrap
check/create, login, MCP-surface enable, credential mint.

```bash
VIGIL_BOOTSTRAP_ADMIN_PASSWORD='…' ./scripts/headless_onboard.py \
    --base-url http://127.0.0.1:6987 --label headless-ci --json
```

```json
{"bootstrapped": true, "surface_enabled": true,
 "mcp_token": "vgl_mcp_…",
 "client_config": {"mcpServers": {"vigil": {
     "url": "http://127.0.0.1:6987/mcp",
     "headers": {"Authorization": "Bearer vgl_mcp_…"}}}}}
```

- **Identity** comes from `--username`/`--email`/`--password` or the
  `VIGIL_BOOTSTRAP_ADMIN_USERNAME` / `_EMAIL` / `_PASSWORD` environment
  variables. Prefer the env vars: a password on argv is visible in `ps`.
- **Exit codes:** `0` ok · `1` configuration (missing identity, weak password)
  · `2` authentication failed · `3` MFA required · `4` account locked ·
  `5` rate limited · `6` API unreachable · `7` unexpected API response.
- **MFA is refused on purpose** (exit `3`): headless automation cannot answer
  an MFA prompt. Use a dedicated admin account without MFA, or a credential
  minted in advance.
- **Re-running is safe.** Every step checks before it acts: a bootstrapped
  instance skips to login (`bootstrapped: false` in the output), and the last
  step mints an *additional* revocable credential rather than failing.
- **The token is printed once and never written to disk by the script.** Give
  it a lifetime with `--expires-in-days`; rotate by minting a new credential
  and revoking the old one (console, or
  `DELETE /api/mcp/surface/credentials/{id}`).
- **Behind a reverse proxy**, pass `--context-path` (or set
  `VIGIL_CONTEXT_PATH`) so the emitted client config points at the proxied
  path.

## Connect an MCP client

The surface is streamable HTTP at `http://<host>:6987/mcp`, bearer-authed with
the `vgl_mcp_` credential. It serves 49 tools (26 frozen mirrors of
`/api/v1` operations, pinned in
[`tools/mcp/frozen_tools.snapshot.json`](../tools/mcp/frozen_tools.snapshot.json);
the rest are served under the `0.x` terms in
[SECURITY.md](../SECURITY.md#supported-versions)).

**Claude Desktop** (or any client that takes an `mcpServers` entry) — paste
the `client_config` the onboarding script printed:

```json
{"mcpServers": {"vigil": {
    "url": "http://127.0.0.1:6987/mcp",
    "headers": {"Authorization": "Bearer vgl_mcp_…"}}}}
```

**A generic Python client** (the `mcp` package — the shape below is the one
Vigil's pinned `mcp==2.1.1` installs; other SDK lines spell the transport
differently):

```python
import asyncio

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOKEN = "vgl_mcp_…"

async def main():
    # The pinned SDK takes no headers argument: auth rides on the httpx2 client.
    async with streamable_http_client(
        "http://127.0.0.1:6987/mcp",
        http_client=httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {TOKEN}"},
        ),
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            workflows = await session.call_tool("list_workflows", {})
            print(workflows.content[0].text)

asyncio.run(main())
```

A client that connects while the surface is disabled sees a 404 — enable it
with the onboarding script (it does so automatically) or
`PUT /api/mcp/surface` with `{"enabled": true}`; no restart is needed.

## Drive a run over MCP

The operational core is on the surface. Runs, findings, cases, metrics, and
the workflow catalog mirror the frozen `/api/v1` contract; run control ships
under `0.x` terms.

| Tool | Does |
|---|---|
| `list_workflows` / `get_workflow` | discover what can run |
| `start_agent_run` | start a run: `playbook` (a playbook path, or `workflow:<id>` from the catalog), `config` (deployment-config path for file playbooks; leave empty for `workflow:` references, which resolve their own config), `run_kind` (must be compatible with the workflow — see below), `prompt` |
| `get_agent_run` | status of a run: `queued`, `running`, or terminal, with phase progress |
| `queue_agent_directive` | steer a running agent: `kind` is `note`, `redirect`, or `cancel` |
| `cancel_agent_run` / `resume_agent_run` | run control: cancel with a reason; resume a paused run |
| `update_finding` | triage: status, severity, assignment |
| `search_cases` / `merge_cases` / `export_case_iocs` | case search and lifecycle |
| `get_case_metrics` | the six metric views (by-priority, by-status, breached, MTTR, MTTD, summary) |
| `list_approval_actions` / `get_approval_action` | approval discovery: filter by `status` (`pending`, `approved`, `rejected`, `executed`, `failed`) and type |
| `approve_action` / `reject_action` | decide a pending action |

Worked example — an investigation that hits a human gate:

```
list_workflows()
  → pick the workflow id (e.g. "incident-response")
start_agent_run(playbook="workflow:incident-response", config="",
                run_kind="investigate", prompt="Investigate the phishing finding")
  → {"run_id": "…", "job_id": "…"}
get_agent_run(run_id)
  → running … then parked: the workflow reached its approval_required phase
list_approval_actions(status="pending")
  → the action waiting on a person, with its action_id
approve_action(action_id)
  → decision recorded … "run_resume": "enqueued"
get_agent_run(run_id)
  → the run is back in motion — no sweeper wait
```

Two argument notes the example packs in: a `workflow:` reference resolves
its own config, so `config` stays empty (a path there is rejected), and
`run_kind` must be compatible with the workflow — each definition names its
kind (`investigate` for the investigation workflows, `hunt` for
`threat-hunt`, `root_cause`, `adjudicate`). A mismatched pair is accepted at
start and then fails the run at spec build
(`arch role … needs tool(s) the config does not declare`), because the run
kind selects the agent arch and the arch's tools must exist in the workflow's
config. When in doubt, `get_workflow` reports the definition's kind.

The last two steps are the part worth noticing: a decision made over MCP does
what the `/api/v1` approvals router does — after the decision is recorded and
committed, a run-bound action wakes the parked run immediately. The response
reports `run_resume: "enqueued"`, or `"skipped: <reason>"` when the wakeup
could not be enqueued. **The decision stands either way** — the parked-run
sweeper picks the run back up within ~60 s as the fallback, so nothing is
lost. Actions not bound to a workflow run simply report
`"skipped: action is not bound to a workflow run"`.

**Who did it is recorded.** Every tool call is bound to the credential's user —
a run you started shows you as the trigger, an approval you decided shows you
as the approver. The run's own work is done by Vigil's agents under their own
identity; an MCP caller is never silently "the agent".

## Unattended operations

- **Approval discovery is pull-based.** Poll `list_approval_actions` with
  `status="pending"` over MCP, or — for a signed-in human —
  `GET /api/v1/approvals/needs-you`. There are no webhooks; poll at whatever
  cadence your operator wants.
- **Investigation-level waits** (days, not seconds) belong to the SOC daemon:
  its Slack and PagerDuty paths page a person when an investigation parks.
  The daemon's auto-responder routes by confidence — by default ≥ 0.90
  auto-approves, 0.85–0.90 gets a quick review, 0.70–0.85 needs analyst
  review, below 0.70 escalates — all configurable.
- **A run waiting on a person is never killed by the stale-run sweeper.** If
  nobody ever answers, the run is eventually marked abandoned when its park
  budget lapses — it does not spin.

## Security notes

- **The credential is actor-scoped.** Everything done with it is attributed to
  its user; there is no shared "service account" ambiguity to audit around.
- **Treat the token like a password with a lifetime.** It is printed once and
  never written to disk by the onboarding script; set `--expires-in-days`,
  and rotate by minting a new credential and revoking the old. The gate
  answers 401 with a single indistinguishable error for missing, unknown,
  revoked, and expired tokens.
- **An MCP credential opens the MCP surface only.** The REST API refuses
  `vgl_mcp_` tokens *by name* rather than as invalid —
  `core/auth/current_user.py` — because the holder has a working credential
  and needs to know it is working in the wrong place.
- **Bootstrap closes forever after the first user.** The unauthenticated
  first-account endpoint is a one-time door; on any later run it answers 403
  and the onboarding script moves on to login.
- **The surface is off by default.** It is another front door into a SOC, and
  one nobody asked for should not be listening. Enabling it — in `.env` before
  boot, or from Settings / the onboarding script — is a deliberate act, and
  the runtime toggle an operator sets wins over the environment default.
- **Headless warnings do not fail the boot** so that narrow deployments (for
  example, daemon-only) keep working. An unattended host that must run
  workflows should treat those warnings as required reading, not noise.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Runs are accepted, reported queued, never picked up | agent layer down, or `AGENT_INTERNAL_TOKEN` unset on one side | set the token in `.env` (generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`); check `logs/agent-worker.log`; `scripts/agent_up.sh` starts the layer by hand |
| Every `/internal` call answers 503 | `AGENT_INTERNAL_TOKEN` empty | same as above — a run fails before its first model call rather than at the seam |
| `/mcp` answers 404 | surface disabled | run the onboarding script, or `PUT /api/mcp/surface` with `{"enabled": true}`; no restart needed |
| `401` from `/api/…` with a `vgl_mcp_` token | MCP credentials do not open the REST API, by design | use the MCP surface for the same operation |
| Bootstrap answers `403` | a user already exists | nothing is wrong — continue with login (the script does this automatically) |
| Bootstrap fails with a foreign-key violation on a fresh database | the schema was built without reference data (a bare `migrate_schema.py` run) | run `scripts/seed_reference_data.py` (idempotent), or boot with `./start.sh` |
| "Node.js 20+ required" and no agent layer | Node missing or too old | install Node ≥ 20; without it neither the agent layer nor the frontend starts and workflows cannot run |
| A run fails at its first model call | no LLM provider reachable (Bifrost down, no key) | configure a provider or serve a local model with `scripts/local_model.sh` |
| The minted token is lost | by design it is not stored | mint a new credential and revoke the old one |
| `/mcp` behind a reverse proxy resolves the wrong path | the client config was minted without the proxy path | pass `--context-path` (or `VIGIL_CONTEXT_PATH`) when onboarding |

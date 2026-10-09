# Vigil — Codebase Map

One product, four runtimes over a shared `core/` library. Depth cap 2.

| Path | What it is |
|---|---|
| `core/` | Shared Python library: capability domains over a storage/platform tier (CONTEXT.md is the tour) |
| `core/agents/` | Built-in agent definitions (`builtins.py`) + custom-agent loading |
| `core/api/` | Console routers; versioned frozen contract in `core/api/v1/` (nothing under `core/` imports it back — `.importlinter`) |
| `core/auth/` | Users, roles, JWT sessions, MFA, password policy, token blacklist |
| `core/cases/` | Case lifecycle: grouping of Findings, SLA, timeline, templates |
| `core/findings/` | The atomic security-signal domain: evidence, entity graphs, MITRE mapping |
| `core/detections/` | Detection-rule sources and management ("the rules that produce Findings") |
| `core/ingestion/` | Normalizing external security data into Findings (SIEM/Kafka/S3) |
| `core/federation/` | Scheduled poll loop driving ingestion sources (when/how often, not what) |
| `core/integrations/` | Vendor slices (`<vendor>/tool.py`) + the MCP registry |
| `core/llm/` | Bifrost gateway clients, provider sync, ARQ-backed LLM gateway |
| `core/response/` | Autonomous containment actions + the approval gate |
| `core/threat_intel/` | STIX/TAXII ingestion, MITRE ATT&CK taxonomy resolution |
| `core/workflows/` | Workflow engine; built-in `WORKFLOW.md` files under `definitions/` |
| `core/storage/`, `core/platform/` | Shared infrastructure tier (DB connections, config, telemetry) |
| `core/chat/`, `core/memory/`, `core/reporting/`, `core/documents/`, `core/backup/`, `core/skills/` | Remaining capability domains |
| `services/api/` | FastAPI app: routers, middleware (CSRF, security headers), `main.py` |
| `services/agent/` | TypeScript agent layer: workflow runtimes (compose/investigate/root-cause/hunt), BullMQ worker + HTTP serve |
| `services/daemon/` | Headless SOC daemon: polling, triage/enrich backfill, auto-responder (INTENT.md declares autonomy) |
| `services/worker/` | ARQ LLM worker |
| `services/medic/` | Self-checks / contracts |
| `clients/web/` | React 18 + Vite console (screens, routing incl. `SetupGate`, MUI + Tailwind) |
| `clients/desktop/` | Desktop packaging (bundles backend/agent images offline) |
| `tools/mcp/` | Vigil's own MCP server; frozen tool snapshot `frozen_tools.snapshot.json` |
| `infra/docker/` | Compose file (postgres, redis, bifrost, backend, agent, profiles) + Dockerfiles |
| `infra/helm/` | Kubernetes chart |
| `infra/database/` | Postgres init SQL |
| `scripts/` | Operational scripts: schema init/migrate, seeding, agents up, setup_dev, exports |
| `tests/unit/`, `tests/security/`, `tests/integration/` | Pytest suites (CI: unit+security, `-m "not external_service"`) |
| `data/` | Bundled reference data: common passwords, taxonomy, registry |
| `docs/` | Design docs; user docs live at vigilsoc.org |

Key reading order: README.md → CONTEXT.md → INTENT.md → VERSIONING.md.

# Vigil Documentation

Product and operator documentation for Vigil, the AI security operations
center. These pages are maintained in this repository and reconciled against
the code on `main` — when this document and the implementation disagree, the
code wins and the page gets fixed.

An online mirror of older revisions of these pages is served at
[vigilsoc.org/docs](https://vigilsoc.org/docs/); this tree is the source of
truth for this fork.

## Product

What Vigil does and how it is organized.

- [Architecture](product/architecture.md) — components, data flow, and the backend tool integration model
- [Agents](product/agents.md) — agent surfaces and how they drive the platform
- [Features](product/features.md) — capability overview, including MITRE ATT&CK mapping
- [API](product/api.md) — the service API surface
- [Chat-Driven Case Management](product/chat-case-management.md) — conversational case workflows
- [Chat Case Quick Reference](product/chat-case-quick-reference.md) — common chat commands at a glance
- [Backend Tools](product/backend-tools.md) — the tool integration layer behind chat and agents
- [Detection Engineering](product/detection-engineering.md) — detection rules and repositories
- [Source Evidence](product/source-evidence.md) — how evidence is captured and cited
- [Integrations](product/integrations.md) — supported vendor integrations and their descriptors
- [SLA Usage Guide](product/sla-usage.md) — working with case SLAs
- [SLA Policy API](product/sla-api.md) — SLA policy endpoints
- [SLA Quick Reference](product/sla-quick-reference.md) — SLA defaults and shortcuts

## Deploy

Getting Vigil running and keeping it running.

- [Configuration](deploy/configuration.md) — environment and service configuration
- [Deployment Guide](deploy/deployment.md) — end-to-end deployment
- [Helm Values](deploy/helm.md) — chart values reference
- [Helm Chart](deploy/helm-chart.md) — the `infra/helm/vigil` chart
- [Helm Secrets](deploy/helm-secrets.md) — sealed secrets and SOPS
- [Production Security](deploy/production-security.md) — hardening checklist for production
- [State and Secrets](deploy/state.md) — where state lives and how secrets flow
- [Kafka Ingestion](deploy/kafka-ingestion.md) — Kafka-based alert ingestion
- [Sandbox](deploy/sandbox.md) — isolated/sandbox deployment mode
- [Bifrost Gateway](deploy/bifrost.md) — the LLM gateway layer
- [Database Init SQL](deploy/database-init.md) — database initialization and extensions

## Develop

Working on Vigil's code and shipping it.

- [Contributing to Vigil](develop/contributing.md) — how to contribute
- [Testing Guide](develop/testing.md) — running the test suites
- [DEV_MODE](develop/dev-mode.md) — the local development mode
- [CI/CD Guide](develop/ci-cd.md) — pipeline behavior and gates
- [GitHub Workflows](develop/github-workflows.md) — the workflows in `.github/`
- [Releasing](develop/releasing.md) — the release process
- [Release Setup](develop/release-setup.md) — one-time release configuration
- [AI Assistant Notes](develop/claude.md) — guidance for AI coding assistants in this repo
- [LLM Layer](develop/llm-layer.md) — the `core/llm` provider abstraction
- [Vendor Slices](develop/vendor-slices.md) — vendor integration modules
- [Splunk Testing](develop/splunk-testing.md) — testing against Splunk
- [Postgres to Splunk Export](develop/postgres-to-splunk.md) — the export pipeline
- [Default Credentials Init](develop/init-credentials.md) — seeding initial credentials

## Integrations

Vendor-specific integration guides.

- [Darktrace](integrations/darktrace.md) — Darktrace webhook ingestion
- [VStrike Kill Chain MCP](integrations/vstrike-killchain.md) — the VStrike kill chain MCP integration

## Architecture Decision Records

- [ADR 0001: Integration Descriptor](adr/0001-integration-descriptor-is-the-registry.md)
- [ADR 0014: Off-host Agent Token](adr/0014-off-host-agent-token-and-network-policy.md)

## Examples

- [Sealed Secret example](examples/sealed-secret.yaml)
- [SOPS config example](examples/sops-config.yaml)

## Local Guides

Guides written and maintained directly in this repository.

- [Headless Mode](headless.md) — running Vigil without the console
- [Logging Levels](logging-levels.md) — log level conventions and tuning
- [MTD Enablement](mtd-enablement.md) — moving target defense / decoy response
- [Runbook: Honey Router Cilium Verification](runbooks/honey-router-cilium-verification.md) — verifying the honey router path

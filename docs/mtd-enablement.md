# Enabling Automated MTD and Honey-Routing

Vigil's response vocabulary is allow, block, or record. Against automated recon
and lateral-movement probing, block is also a signal: the attacker learns
something reacted, rotates infrastructure, and returns evasive. The MTD
feature adds a fourth move — **deceive**: a suspicious probe aimed at an
internal destination is transparently routed into isolated decoy services,
which answer plausibly while Vigil records everything the attacker does as
findings, evidence, and ATT&CK-mapped intel.

Everything here is **default-off**. Enabling MTD is a human decision, made by
configuration, and every routing decision is audited, reversible, and
bound by a TTL.

## What enabling gives you

| Plane | What it does | Ships everywhere? |
| --- | --- | --- |
| Decision | The daemon's responder recognizes recon probes (T1046/T1595) and, at confidence above its own floor, proposes `honey_route` actions | Yes |
| Enforcement | A `CiliumLocalRedirectPolicy` pins the attacker's flows to the decoy Service | Only on clusters running Cilium |
| Decoys | High-interaction SSH + HTTP workloads holding canary credentials only | Yes (opt-in profile/workloads) |
| Capture | Each decoy session becomes a Finding, a CaseEvidence transcript, and CaseIOCs — ATT&CK-mapped | Yes |
| Analyst tooling | `query_decoy_sessions` reads captured sessions through the agent tool surface and MCP | Yes |

On a **Docker Compose** install you get the full decision path, the decoys,
the capture pipeline, and the analyst tooling. The enforcement executor
honestly reports an unsupported action — a routing is recorded as failed with
a structured error, never silently skipped and never faked as done. Transparent
rerouting requires Cilium; see [Prerequisites](#prerequisites).

## Prerequisites

- **Docker Compose** install (any install can run decoys + capture), or
  **Kubernetes/Helm** for transparent rerouting.
- For transparent rerouting specifically: **Cilium CNI already running on the
  cluster**, with the `CiliumLocalRedirectPolicy` CRD available. Vigil does
  not install Cilium for you, and the backend is gated on CNI/CRD detection —
  a cluster without Cilium gets the same honest unsupported failure as a
  Compose install.
- Before first enablement on a cluster, work through
  [`docs/runbooks/honey-router-cilium-verification.md`](runbooks/honey-router-cilium-verification.md)
  — it verifies the generated redirect policy against a kind cluster.

## The knobs

### Response side (the daemon)

| Env var | Default | Meaning |
| --- | --- | --- |
| `DAEMON_MTD_ENABLED` | `false` | Master switch. The MTD decision path returns no action while this is off. |
| `DAEMON_MTD_CONFIDENCE_FLOOR` | `0.60` | Minimum triage confidence for a honey-route proposal. Its own band, independent of the isolate/block confidence floors. |
| `DAEMON_MTD_SESSION_TTL_SECONDS` | `3600` | How long an approved routing may hold before it is automatically released and the normal path restored. |
| `DAEMON_MTD_INTERNAL_ONLY` | `true` | Only probes aimed at internal destinations are eligible. Never routes traffic destined outside your perimeter. |

The same settings are declared in `INTENT.md` under `deceive:` (`enabled`,
`confidence_floor`, `session_ttl_seconds`) so the autonomy posture is
reviewable in one place.

Two existing daemon switches are honored on this path exactly as on every
other response action:

- `DAEMON_FORCE_APPROVAL` — hold every routing for a human in the approvals
  queue, regardless of confidence.
- `DAEMON_DRY_RUN` — log what would be routed, write nothing.

### Decoy side (the workloads)

| Env var | Default | Meaning |
| --- | --- | --- |
| `DECOY_ENABLED` | `false` | Starts the decoy services alongside the daemon. |
| `DECOY_INGEST_URL` | `http://soc-daemon:8081/ingest` | Where decoy session events stream to. |
| `DECOY_INGEST_TOKEN` | unset | Auth token for the ingest webhook; set it to match the daemon's ingest auth. |
| `DECOY_CANARY_PASSWORD` | unset | The canary credential decoys accept. Unset, a house default is used; it is always a marked-fake canary value, never a real secret. |
| `DECOY_SESSION_TTL_SECONDS` | `3600` | Decoy-side session bound, mirroring the routing TTL. |

## Enforcement configuration

The enforcement plane is a registered integration (`honey_router`), configured
in **Settings → Integrations**:

- `backend` — which enforcement backend applies routes. Only `cilium` exists
  today. A Compose install has no backend configured, and that is the honest
  unsupported case, not a misconfiguration.
- `namespace` — the Kubernetes namespace the redirect policies are written
  into (default `default`). The policy object is namespaced by design.

The backend talks to the Kubernetes API with the pod's in-cluster service
account, or the operator's kubeconfig — no extra credentials are stored.

## Safety rails

- **Default off.** Nothing routes until a human sets `DAEMON_MTD_ENABLED=true`
  (or `deceive.enabled` in `INTENT.md`).
- **Never-route exclusions.** Certain destinations (production database hosts,
  shared infrastructure) are on an exclusion registry. A listed destination is
  never routed, and removing an entry is recorded — never deleted.
- **Reversible routing.** Every routing is undoable: an analyst can release it
  early, the TTL releases it automatically, and a failed routing restores the
  normal path. Routing never silently blocks legitimate traffic — the
  fail-safe direction is always back to normal, not closed.
- **Audited decisions.** Every proposal, auto-approval, execution result, and
  release writes its decision rule — including the rows nothing waited on.
- **Canary-only credentials.** Decoys hold marked-fake canary credentials so a
  leak is identifiable as fake. Egress from decoys is denied by default
  (Helm NetworkPolicy; the Compose profile binds no decoy host ports).

## Reading the intel

Capture reuses the models Vigil already has — no new schema:

- Each captured session is one **Finding** (`data_source="vigil-decoy"`, the
  session id as its finding id) carrying ATT&CK technique predictions, so the
  sessions flow into the existing technique rollup and coverage surfaces.
- The session transcript lands as **CaseEvidence** on the standing decoy-intel
  case, and attacker IPs / dropped-file hashes become **CaseIOCs**.
- **`query_decoy_sessions`** is the analyst read: one row per session with the
  decoy, the attacker's entity key, the session window, the routing action,
  auth attempts, commands, files dropped, and the observed techniques. It is
  read-only, bounded, and refuses a caller with no principal bound — the
  transcripts are evidence. Available through the agent tool surface (the
  investigator, responder, mitre analyst, and threat intel agents recommend
  it) and through Vigil's MCP server for external agents.
- For an attacker-scoped view across sessions, `recall_entity` their `ip:*`
  entity key instead.

## Verifying the enablement

1. Unit/integration: `tests/unit/agents/test_query_decoy_sessions.py` covers
   the tool's manifest membership, bounds, and attribution; the response and
   decoy test trees cover the decision and capture paths.
2. Cluster: work through the
   [Cilium verification runbook](runbooks/honey-router-cilium-verification.md)
   on a kind cluster before promoting autonomy past analyst-gated.
3. Operational: with MTD enabled, confirm the first routing appears in the
   approvals queue (or executes, under an explicit auto-approval policy) with
   its decision rule recorded, and that the decoy session shows up in
   `query_decoy_sessions` within the session TTL.

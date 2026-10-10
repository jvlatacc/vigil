# API

## Data Model

### Finding

Primary security observation with embeddings and MITRE predictions.

```json
{
  "finding_id": "f-2024-01-15-001",
  "embedding": [0.123, -0.456, ...],
  "mitre_predictions": {"T1071.001": 0.85, "T1048.003": 0.72},
  "anomaly_score": 0.92,
  "entity_context": {
    "src_ip": "10.0.1.15",
    "dst_ip": "203.0.113.50",
    "hostname": "workstation-042",
    "user": "jsmith"
  },
  "timestamp": "2024-01-15T14:32:18Z",
  "data_source": "flow",
  "severity": "high",
  "status": "new"
}
```

### Case

Investigation grouping related findings.

```json
{
  "case_id": "case-2024-01-15-001",
  "title": "Potential C2 Beaconing",
  "finding_ids": ["f-2024-01-15-001", "f-2024-01-15-002"],
  "status": "investigating",
  "priority": "high",
  "assignee": "analyst@example.com",
  "notes": [...],
  "timeline": [...],
  "created_at": "2024-01-15T15:00:00Z"
}
```

### Severity Calculation

```
combined = (anomaly_score * 0.6) + (max_mitre_confidence * 0.4)

>= 0.8: critical
>= 0.6: high
>= 0.4: medium
<  0.4: low
```

## MCP Tools - Findings

The operational MCP surface is the frozen Vigil server the backend mounts at
`/mcp` — `tools/mcp/vigil.py`, 26 tools, wired in `services/api/main.py`.

### `get_finding`

```json
{ "finding_id": "f-xxx" }
```

### `list_findings`

```json
{
  "filters": { "severity": "high", "data_source": "flow" },
  "limit": 50,
  "sort_by": "timestamp",
  "sort_order": "desc"
}
```

### `update_finding`

Patches status, severity, assignee, tags, and similar fields — mirrors the
frozen `PATCH /api/v1/findings/{finding_id}` contract.

(The upstream version of this page also documented `nearest_neighbors` and
`technique_rollup` as MCP tools; neither exists on the MCP surface at
current HEAD. Technique rollups are an agent-layer tool —
`get_technique_rollup` in `core/agents/tool_registry.py`.)

## MCP Tools - Case Management

### `create_case`

```json
{
  "title": "Investigation title",
  "finding_ids": ["f-xxx", "f-yyy"],
  "priority": "high",
  "description": "Case description"
}
```

### `update_case`

```json
{
  "case_id": "case-xxx",
  "updates": {
    "status": "in_progress",
    "add_findings": ["f-zzz"],
    "add_tags": ["ransomware"]
  }
}
```

### `list_cases`

```json
{
  "status": "in_progress",
  "priority": "high",
  "limit": 50
}
```

### `get_case`

```json
{
  "case_id": "case-xxx",
  "include_findings": true
}
```

The remaining case tools on the MCP surface: `close_case`,
`add_finding_to_case`, `remove_finding_from_case`, `add_case_evidence`,
`add_case_ioc`, `bulk_add_iocs`, `get_case_iocs`, `search_cases`,
`merge_cases`, `export_case_iocs` (`tools/mcp/vigil.py`).

## MCP Tools - Approval

Approval actions are proposed by the response pipeline (agents, workflows) —
the MCP surface reads and decides them; it does not create them.

### `list_approval_actions`

```json
{
  "status": "pending",
  "action_type": "isolate_host"
}
```

### `get_approval_action`

Fetch one approval action by id.

### `approve_action` / `reject_action`

Decide a pending action. Either decision on an action bound to a parked
workflow run resumes that run (`tools/mcp/vigil.py` →
`core/workflows/run_resume.resume_run`).

## Attack Layer tools (removed)

The upstream version of this page documented `get_attack_layer`,
`get_technique_rollup`, `get_findings_by_technique` and `create_attack_layer`
as MCP tools. None of them exist at current HEAD — ATT&CK Navigator layer
generation is gone from the codebase. Technique rollups remain available to
agents via `get_technique_rollup` (`core/agents/tool_registry.py`).

## Access Tiers

| Tier | Description | Rate Limit |
|------|-------------|------------|
| 1 | Findings, embeddings, aggregations | 100/min |
| 2 | Evidence snippets (redacted) | 20/min |
| 3 | Raw log export (disabled default) | 5/min |

## Error Codes

| Code | Description |
|------|-------------|
| `NOT_FOUND` | Resource not found |
| `INVALID_PARAMETER` | Invalid parameter |
| `ACCESS_DENIED` | Insufficient permissions |
| `RATE_LIMITED` | Too many requests |

Error response format:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Finding not found"
  }
}
```

## Entity Context by Data Source

### Flow

```json
{
  "src_ip": "10.0.1.15",
  "dst_ip": "203.0.113.50",
  "src_port": 54321,
  "dst_port": 443,
  "protocol": "tcp",
  "bytes_sent": 1024,
  "hostname": "workstation-042"
}
```

### DNS

```json
{
  "src_ip": "10.0.1.15",
  "query_name": "suspicious.com",
  "query_type": "A",
  "response_ips": ["203.0.113.50"]
}
```

### WAF

```json
{
  "src_ip": "203.0.113.100",
  "method": "POST",
  "uri": "/api/upload",
  "rule_matched": "942100",
  "rule_category": "SQL Injection"
}
```

## API schemas

The payload models live as Pydantic schemas in [core/storage/schemas/](../../core/storage/schemas/) — `finding.py`, `case.py`, `digital_twin.py`, `workflow.py`, and the rest. There is no standalone JSON-schema directory in the repo. (An earlier version of this page pointed at `data/schemas/*.schema.json`, which does not exist at current HEAD.)

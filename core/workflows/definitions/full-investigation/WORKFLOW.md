---
name: full-investigation
version: 2
description: "Comprehensive investigation with MITRE ATT&CK mapping, cross-signal correlation, response planning, and detailed reporting."
use_case: "Deep-dive investigation into suspicious findings or clusters, going beyond triage into full MITRE mapping, cross-signal correlation, and comprehensive response."
trigger_examples:
  - "Fully investigate this finding and all related activity"
  - "Do a complete investigation of case CASE-20260215-xyz"
  - "Deep dive into these suspicious lateral movement findings"
  - "Run full investigation workflow on this cluster of alerts"
run_kind: investigate
objectives:
  - "Collect every entity and artifact the finding touches"
  - "Map the activity to ATT&CK and place it on the kill chain"
  - "Correlate related signals into attack chains and campaigns"
  - "Plan containment across the full correlated scope and report it"
---

# Full Investigation Workflow

Investigate a finding or a cluster past triage. Collect every entity and artifact the finding touches. Map the activity to ATT&CK and place it on the kill chain. Correlate related signals into attack chains and campaigns. Plan containment across the full correlated scope and report it.

## Response Planning

Propose containment by writing one entry per action into `state.json`
`proposed_actions`, each shaped so the orchestrator can mint the approval row:

```json
{
  "action": "isolate",
  "target": "<host or ip>",
  "reason": "<the evidence>",
  "requires_approval": true
}
```

When the correlated signals show one source probing across hosts —
reconnaissance or lateral movement (for example T1046, T1595, T1135) — propose
honey-routing it as well as or instead of a deny: add
`{"action": "honey_route", "target": "<attacker ip>", "reason": "<the corroborated probes>", "requires_approval": true}`
to `proposed_actions`, or call `propose_honey_route` with the source IP, the
destination IPs and ports probed, and your evidence. Either way the proposal
becomes one `human_only` approval row per attacker (`honey_route:<ip>` is
unique, so proposing the same source twice never doubles the row) and steers
nothing by itself: a person decides, and only then does the source's traffic
move into the decoys. Do not propose it for a sanctioned scanner or a
shared-NAT source, and never report a steer as done — the row records it as
awaiting a person.

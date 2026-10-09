---
name: incident-response
version: 2
description: "Respond to active security incidents with rapid triage, deep investigation, containment, and documentation. Follows NIST IR framework."
use_case: "Active incident response -- an alert fires and the SOC needs to triage, investigate, contain, and document."
trigger_examples:
  - "Run incident response on finding f-20260215-abc123"
  - "We have an active incident -- ransomware detected on HOST-42"
  - "Respond to this critical alert"
  - "IR workflow for this phishing finding"
run_kind: investigate
objectives:
  - "Classify the alert and decide whether it warrants response"
  - "Establish root cause, attack vector and blast radius"
  - "Contain the threat and plan eradication and recovery"
  - "Produce an audit-ready record of what happened and what was done"
---

# Incident Response Workflow

Respond to an active security incident. Classify the alert and decide whether it warrants a response. Establish the root cause, the attack vector, and the blast radius. Contain the threat and plan eradication and recovery. Leave an audit-ready record of what happened and what was done.

## Response & Containment

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

When the evidence shows one source repeatedly probing — reconnaissance or
lateral movement (for example T1046, T1595, T1135) — propose honey-routing it
as well as or instead of a deny: add
`{"action": "honey_route", "target": "<attacker ip>", "reason": "<the corroborated probes>", "requires_approval": true}`
to `proposed_actions`, or call `propose_honey_route` with the source IP, the
destination IPs and ports probed, and your evidence. Either way the proposal
becomes one `human_only` approval row per attacker (`honey_route:<ip>` is
unique, so proposing the same source twice never doubles the row) and steers
nothing by itself: a person decides, and only then does the source's traffic
move into the decoys. Do not propose it for a sanctioned scanner or a
shared-NAT source, and never report a steer as done — the row records it as
awaiting a person.

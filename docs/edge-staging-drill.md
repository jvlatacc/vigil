# One-time edge staging drill

Mocked tests and the compose e2e cannot prove real nftables, a real WAN
cut, or a model swap under load. Before production sign-off of an edge
deployment, run this drill once on a staging gateway, end to end, and
keep the outputs with the release notes. Every `[ ]` is a checkbox — do
not sign off with any unchecked.

The companion guide is [docs/edge-operator-guide.md](edge-operator-guide.md).

## Setup

- [ ] Staging gateway with real nftables (not the compose e2e shim),
  daemon in gateway mode with the daemon on the segment's traffic path
  (host networking — see the guide's gateway reality check), a real
  trust root, and a tier-2 bundle signed for the staging segment.
- [ ] A second machine on the segment generating benign traffic you can
  observe (or a feed of recorded EVE lines).

## Drill

- [ ] **Block end-to-end.** Emit telemetry for a bundle IOC (e.g.
  `203.0.113.55`) and confirm with `nft list table inet vigil_edge`
  that the drop rule exists *in the gateway's real table* and that
  traffic to the IP actually fails from a host behind the gateway.
- [ ] **TTL revert.** Wait out the bundle's `default_block_ttl_seconds`
  and confirm the rule is gone and the revert is journaled (`kind:
  revert` carrying the original action's idempotency key).
- [ ] **Model behavior.** Stop the Ollama/advisor endpoint; send one
  more IOC observation; confirm deterministic-only containment still
  fires and the decision carries no model confidence. Restart the
  endpoint.
- [ ] **The WAN pull.** Disconnect the gateway from the control plane
  for **15 minutes**. During the window: confirm state flips to
  `partitioned`, containment keeps firing inside bundle caps, and the
  journal grows on the gateway volume.
- [ ] **Overflow behavior** (if time allows): flood observations past
  the journal budget during the partition; confirm explicit loss
  counters in the health/metrics output and containment records
  surviving eviction priority — never silent discard.
- [ ] **Reconnect.** Restore the link; confirm `partitioned →
  reconciling → synced` in order, bounded batches uploading, and no
  duplicate findings for the same event ids.
- [ ] **Drift-report readback.** Open the findings surface; read the
  `offline_window` close record; verify every block that fired during
  the window appears (rule string, confidence, model version), every
  TTL-expired block shows its revert, and the executed approval rows
  carry edge provenance (`edge:<node_id>`). Anything the report claims
  must match what `nft list` showed at the time — that cross-check is
  the drill.

## Sign-off evidence to keep

The nftables command log during block and after revert, the daemon
health timeline across the partition, the imported findings and approval
rows for the window, and the drift report. Attach them to the release
notes for the deployment that ran the drill.

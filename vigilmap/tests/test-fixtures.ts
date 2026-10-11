/**
 * Shared test fixtures — small documents exercising every node kind, link
 * relation, and rejection case the contract names.
 */

import type {
  MemoryGraphDocument,
  MemoryLink,
  MemoryNode,
} from "../src/types";

/** Hand-built fixture graph: hub entity e1, leaf e2, orphan e3. */
export function fixtureDocument(): MemoryGraphDocument {
  const nodes: MemoryNode[] = [
    { id: "ip:10.0.0.1", kind: "entity", label: "10.0.0.1", entityType: "ip", entityKey: "ip:10.0.0.1" },
    { id: "domain:lan.example.com", kind: "entity", label: "lan.example.com", entityType: "domain", entityKey: "domain:lan.example.com" },
    { id: "host:orphan", kind: "entity", label: "orphan-host", entityType: "host", entityKey: "host:orphan" },
    {
      id: "s-0001", kind: "sighting", label: "beacon observed", entityKey: "ip:10.0.0.1",
      observedFrom: "2026-09-14T09:00:00Z", observedTo: "2026-09-14T09:00:00Z",
      sourceTier: "observed", investigationId: "inv-1",
    },
    {
      id: "s-0002", kind: "sighting", label: "out-of-window sighting", entityKey: "ip:10.0.0.1",
      observedFrom: "2026-09-01T09:00:00Z", observedTo: "2026-09-01T09:00:00Z",
      sourceTier: "asserted", investigationId: "inv-1",
    },
    {
      id: "s-0003", kind: "sighting", label: "untimed sighting", entityKey: "domain:lan.example.com",
      sourceTier: "observed", investigationId: "inv-1",
    },
    {
      id: "v-0001", kind: "verdict", label: "proven: beacon to control", outcome: "proven",
      statement: "Host beacons to the control IP.", rationale: "Two sources agree.",
      investigationId: "inv-1", concludedAt: "2026-09-15T17:00:00Z",
      techniques: ["T1071"],
    },
    {
      id: "v-0002", kind: "verdict", label: "false_positive: scanner", outcome: "false_positive",
      statement: "Traffic was a vulnerability scanner.", concludedAt: "2026-10-01T09:00:00Z",
    },
    { id: "g-0001", kind: "gap", label: "gap: no PCAP", disposition: "deferred", reason: "No packet capture.", investigationId: "inv-1" },
    { id: "h-0001", kind: "hunt", label: "hunt h-0001", objective: "Find beaconing.", startedAt: "2026-09-14T08:00:00Z", endedAt: "2026-09-15T17:00:00Z" },
    { id: "e-0001", kind: "episode", label: "learning: beacon windows", summary: "Beacons cluster in off-hours.", occurredAt: "2026-09-15T18:00:00Z" },
  ];

  const links: MemoryLink[] = [
    { source: "s-0001", target: "ip:10.0.0.1", relation: "sighting-of" },
    { source: "s-0002", target: "ip:10.0.0.1", relation: "sighting-of" },
    { source: "s-0003", target: "domain:lan.example.com", relation: "sighting-of" },
    { source: "v-0001", target: "ip:10.0.0.1", relation: "verdict-subject" },
    { source: "v-0001", target: "domain:lan.example.com", relation: "verdict-subject" },
    { source: "v-0001", target: "s-0001", relation: "verdict-source" },
    { source: "v-0001", target: "s-0002", relation: "verdict-source" },
    { source: "v-0002", target: "ip:10.0.0.1", relation: "verdict-subject" },
    { source: "g-0001", target: "ip:10.0.0.1", relation: "gap-subject" },
    { source: "h-0001", target: "v-0001", relation: "hunt-verdict" },
    { source: "h-0001", target: "v-0002", relation: "hunt-verdict" },
    { source: "h-0001", target: "g-0001", relation: "hunt-gap" },
    { source: "e-0001", target: "ip:10.0.0.1", relation: "episode-entity" },
  ];

  return {
    schemaVersion: 1,
    generatedAt: "2026-09-15T18:00:00Z",
    source: "test-fixture",
    nodes,
    links,
  };
}

/** Node with an unknown extra payload field — the raw-section case. */
export function nodeWithExtras(): MemoryNode {
  return {
    id: "ip:10.9.9.9",
    kind: "entity",
    label: "10.9.9.9",
    entityType: "ip",
    entityKey: "ip:10.9.9.9",
    sanityExtra: { depth: 2 },
  } as MemoryNode;
}

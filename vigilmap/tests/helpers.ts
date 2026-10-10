/**
 * Fixture builders for the contract tests. Everything a test needs to build a
 * valid (or deliberately invalid) MemoryGraphDocument by hand.
 */

import type { MemoryGraphDocument } from "../src/types";

export function validDocument(): MemoryGraphDocument {
  return {
    schemaVersion: 1,
    generatedAt: "2026-10-01T00:00:00Z",
    source: "test",
    nodes: [
      {
        id: "domain:evil-lure.example",
        kind: "entity",
        label: "evil-lure.example",
        entityType: "domain",
        entityKey: "domain:evil-lure.example",
      },
      {
        id: "ip:203.0.113.7",
        kind: "entity",
        label: "203.0.113.7",
        entityType: "ip",
        entityKey: "ip:203.0.113.7",
      },
      {
        id: "s-001",
        kind: "sighting",
        label: "lure email observed",
        entityKey: "domain:evil-lure.example",
        sourceTier: "observed",
      },
      {
        id: "v-001",
        kind: "verdict",
        label: "pre-staging",
        outcome: "proven",
        statement: "Pre-staging confirmed on the lure domain and its C2.",
        techniques: ["T1566"],
        confidence: 0.9,
      },
      { id: "h-001", kind: "hunt", label: "Hunt: phishing lure" },
    ],
    links: [
      { source: "s-001", target: "domain:evil-lure.example", relation: "sighting-of" },
      { source: "v-001", target: "domain:evil-lure.example", relation: "verdict-subject" },
      { source: "v-001", target: "ip:203.0.113.7", relation: "verdict-subject" },
      { source: "v-001", target: "s-001", relation: "verdict-source" },
      { source: "h-001", target: "v-001", relation: "hunt-verdict" },
    ],
  };
}

export function emptyDocument(): MemoryGraphDocument {
  return {
    schemaVersion: 1,
    generatedAt: "2026-10-01T00:00:00Z",
    source: "test-empty",
    nodes: [],
    links: [],
  };
}

/** Deep-clone helper so tests can mutate one field without leaking to others. */
export function withMutation(
  mutate: (doc: MemoryGraphDocument) => void,
  base: MemoryGraphDocument = validDocument(),
): unknown {
  const clone = structuredClone(base);
  mutate(clone);
  return clone;
}

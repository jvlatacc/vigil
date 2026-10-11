import { describe, expect, it } from "vitest";
import { applyFilters, findMatches, matchesTimeWindow, passesFilters } from "../src/filters";
import { noFilters, resolveSelection } from "../src/store";
import { fixtureDocument } from "./test-fixtures";
import type { MemoryNode, NodeKind, VerdictOutcome } from "../src/types";

const doc = fixtureDocument();

function ids(nodes: readonly MemoryNode[]): Set<string> {
  return new Set(nodes.map((n) => n.id));
}

describe("applyFilters", () => {
  it("shows everything under default filters", () => {
    const filtered = applyFilters(doc, noFilters());
    expect(filtered.nodes).toHaveLength(doc.nodes.length);
    expect(filtered.links).toHaveLength(doc.links.length);
  });

  it("hides a kind and the links into it, leaving the document untouched (hide-not-delete)", () => {
    const filters = noFilters();
    filters.kinds.sighting = false;
    const filtered = applyFilters(doc, filters);
    for (const node of filtered.nodes) expect(node.kind).not.toBe("sighting");
    // 3 sighting-of + 2 verdict-source links drop with the sightings
    expect(filtered.links).toHaveLength(doc.links.length - 5);
    // the document is never mutated
    expect(doc.nodes).toHaveLength(11);
    expect(doc.links).toHaveLength(13);
  });

  it("un-filtering restores exactly what was hidden", () => {
    const off = noFilters();
    off.kinds.sighting = false;
    const hidden = applyFilters(doc, off);
    const restored = applyFilters(doc, noFilters());
    expect(ids(restored.nodes)).toEqual(ids(doc.nodes));
    expect(restored.links).toHaveLength(doc.links.length);
    expect(hidden.nodes.length).toBeLessThan(restored.nodes.length);
  });

  it("filters entity types (multi-select AND)", () => {
    const filters = noFilters();
    filters.entityTypes.domain = false;
    const filtered = applyFilters(doc, filters);
    const visible = ids(filtered.nodes);
    expect(visible.has("domain:lan.example.com")).toBe(false);
    expect(visible.has("ip:10.0.0.1")).toBe(true);
    expect(visible.has("host:orphan")).toBe(true);
  });

  it("filters verdict outcomes", () => {
    const filters = noFilters();
    filters.outcomes.proven = false;
    const filtered = applyFilters(doc, filters);
    const visible = ids(filtered.nodes);
    expect(visible.has("v-0001")).toBe(false);
    expect(visible.has("v-0002")).toBe(true);
  });

  it("applies the time window to timed kinds and passes the timeless", () => {
    const filters = noFilters();
    filters.timeWindow = { from: "2026-09-10", to: "2026-09-20" };
    const filtered = applyFilters(doc, filters);
    const visible = ids(filtered.nodes);
    expect(visible.has("s-0001")).toBe(true); // inside
    expect(visible.has("s-0002")).toBe(false); // 2026-09-01, outside
    expect(visible.has("s-0003")).toBe(true); // untimed sighting passes
    expect(visible.has("v-0001")).toBe(true); // concluded 09-15
    expect(visible.has("v-0002")).toBe(false); // concluded 10-01
    expect(visible.has("h-0001")).toBe(true); // hunt window overlaps
    expect(visible.has("ip:10.0.0.1")).toBe(true); // entity — timeless
    expect(visible.has("g-0001")).toBe(true); // gap — timeless
  });

  it("ANDs combined filters", () => {
    const filters = noFilters();
    filters.kinds.sighting = false;
    filters.entityTypes.domain = false;
    filters.outcomes.proven = false;
    const filtered = applyFilters(doc, filters);
    const visible = ids(filtered.nodes);
    expect(visible.has("s-0001")).toBe(false); // kind
    expect(visible.has("domain:lan.example.com")).toBe(false); // type
    expect(visible.has("v-0001")).toBe(false); // outcome
    expect(visible.has("v-0002")).toBe(true);
    expect(visible.has("ip:10.0.0.1")).toBe(true);
    expect(visible.has("host:orphan")).toBe(true);
  });

  it("reports per-kind totals and visible counts", () => {
    const filters = noFilters();
    filters.kinds.sighting = false;
    const filtered = applyFilters(doc, filters);
    expect(filtered.counts.sighting).toEqual({ total: 3, visible: 0 });
    expect(filtered.counts.verdict).toEqual({ total: 2, visible: 2 });
    expect(filtered.counts.entity).toEqual({ total: 3, visible: 3 });
  });
});

describe("resolveSelection", () => {
  it("keeps a selection whose node stays visible", () => {
    const filtered = applyFilters(doc, noFilters());
    expect(resolveSelection("v-0001", filtered.nodes)).toBe("v-0001");
  });

  it("clears a selection whose node was filtered out", () => {
    const filters = noFilters();
    filters.outcomes.proven = false;
    const filtered = applyFilters(doc, filters);
    expect(resolveSelection("v-0001", filtered.nodes)).toBeNull();
  });

  it("stays null without a selection", () => {
    expect(resolveSelection(null, doc.nodes)).toBeNull();
  });
});

describe("matchesTimeWindow", () => {
  const window = { from: "2026-09-14", to: "2026-09-15" };

  it("matches a sighting overlapping the window even if it starts before it", () => {
    const sighting: MemoryNode = {
      id: "s-x", kind: "sighting", label: "long", entityKey: "ip:1.1.1.1",
      observedFrom: "2026-09-13T00:00:00Z", observedTo: "2026-09-14T12:00:00Z",
    };
    expect(matchesTimeWindow(sighting, window)).toBe(true);
  });

  it("excludes a sighting entirely outside the window", () => {
    const sighting: MemoryNode = {
      id: "s-y", kind: "sighting", label: "old", entityKey: "ip:1.1.1.1",
      observedFrom: "2026-09-01T00:00:00Z", observedTo: "2026-09-02T00:00:00Z",
    };
    expect(matchesTimeWindow(sighting, window)).toBe(false);
  });

  it("matches a point-in-time node inside the window and excludes outside", () => {
    const verdict = (at: string): MemoryNode => ({
      id: "v-x", kind: "verdict", label: "v", outcome: "proven", statement: "s", concludedAt: at,
    });
    expect(matchesTimeWindow(verdict("2026-09-14T23:00:00Z"), window)).toBe(true);
    expect(matchesTimeWindow(verdict("2026-09-16T00:00:00Z"), window)).toBe(false);
  });

  it("always passes a node without time fields", () => {
    const gap: MemoryNode = { id: "g-x", kind: "gap", label: "g" };
    expect(matchesTimeWindow(gap, window)).toBe(true);
  });
});

describe("findMatches (search is jump-to-select, not a visibility filter)", () => {
  it("returns nothing for an empty query", () => {
    expect(findMatches(doc, "   ")).toEqual([]);
  });

  it("ranks the exact entity key first", () => {
    const matches = findMatches(doc, "ip:10.0.0.1");
    expect(matches[0]?.id).toBe("ip:10.0.0.1");
  });

  it("matches entity keys and labels case-insensitively as substrings", () => {
    const byKey = findMatches(doc, "10.0.0");
    expect(byKey.map((n) => n.id)).toContain("ip:10.0.0.1");
    const byLabel = findMatches(doc, "beacon");
    expect(byLabel.map((n) => n.id)).toContain("s-0001");
    expect(byLabel.map((n) => n.id)).toContain("v-0001");
  });
});

describe("passesFilters", () => {
  it("is the AND of kind, entity type, outcome, and time predicates", () => {
    const filters = noFilters();
    const sighting = doc.nodes.find((n) => n.id === "s-0001")!;
    expect(passesFilters(sighting, filters)).toBe(true);
    filters.kinds.sighting = false;
    expect(passesFilters(sighting, filters)).toBe(false);
    filters.kinds.sighting = true;
    filters.timeWindow = { from: "2027-01-01" };
    expect(passesFilters(sighting, filters)).toBe(false);
  });

  it("never filters on an unknown-kind node shape by throwing", () => {
    // A node whose kind record is missing from the filter maps must fail the
    // kind check, not crash (kind toggles default false only if absent).
    const filters = noFilters();
    filters.kinds = { entity: true, sighting: true, verdict: true, gap: true, hunt: true, episode: true } as Record<
      NodeKind,
      boolean
    >;
    filters.outcomes = { proven: true, disproven: true, inconclusive: true, handed_off: true, false_positive: true } as Record<
      VerdictOutcome,
      boolean
    >;
    const verdict = doc.nodes.find((n) => n.id === "v-0002")!;
    expect(passesFilters(verdict, filters)).toBe(true);
  });
});

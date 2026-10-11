import { describe, expect, it } from "vitest";
import {
  NODE_KIND_COLORS,
  buildGraph,
  capVisibleSet,
  degreeMap,
  endpointId,
  neighborhood,
  nodeSize,
} from "../src/graph";
import type { SceneLink } from "../src/graph";
import { detailViewModel } from "../src/detail";
import { fixtureDocument } from "./test-fixtures";
import type { MemoryLink, MemoryNode, NodeKind } from "../src/types";

function countByKind(nodes: readonly { kind: NodeKind }[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const n of nodes) counts[n.kind] = (counts[n.kind] ?? 0) + 1;
  return counts;
}

describe("buildGraph", () => {
  it("maps node counts by kind and prunes the orphan", () => {
    const doc = fixtureDocument();
    const built = buildGraph(doc.nodes, doc.links);
    expect(countByKind(built.nodes)).toEqual({
      entity: 2,
      sighting: 3,
      verdict: 2,
      gap: 1,
      hunt: 1,
      episode: 1,
    });
    expect(built.pruned).toBe(1); // host:orphan has no links
    expect(built.nodes.some((n) => n.id === "host:orphan")).toBe(false);
  });

  it("sizes by degree: the hub verdict out-sizes a leaf sighting", () => {
    const doc = fixtureDocument();
    const built = buildGraph(doc.nodes, doc.links);
    const byId = new Map(built.nodes.map((n) => [n.id, n]));
    // v-0001 has degree 5; s-0003 has degree 1
    expect(byId.get("v-0001")?.val).toBe(nodeSize(5));
    expect(byId.get("s-0003")?.val).toBe(nodeSize(1));
    expect(byId.get("v-0001")!.val).toBeGreaterThan(byId.get("s-0003")!.val);
  });

  it("colors nodes by kind from the static legend map", () => {
    const doc = fixtureDocument();
    const built = buildGraph(doc.nodes, doc.links);
    for (const n of built.nodes) expect(n.color).toBe(NODE_KIND_COLORS[n.kind]);
  });

  it("keeps only links whose both endpoints survived", () => {
    const doc = fixtureDocument();
    const built = buildGraph(doc.nodes, doc.links);
    const ids = new Set(built.nodes.map((n) => n.id));
    for (const l of built.links) {
      expect(ids.has(endpointId(l.source))).toBe(true);
      expect(ids.has(endpointId(l.target))).toBe(true);
    }
    expect(built.links).toHaveLength(doc.links.length); // nothing dangling existed to drop
  });

  it("counts degrees from links, both endpoints", () => {
    const links: MemoryLink[] = [
      { source: "a", target: "b", relation: "sighting-of" },
      { source: "a", target: "c", relation: "verdict-source" },
    ];
    expect(degreeMap(links).get("a")).toBe(2);
    expect(degreeMap(links).get("b")).toBe(1);
    expect(degreeMap(links).get("c")).toBe(1);
  });

  it("never hands the document's link objects to the scene (d3 aliases them)", () => {
    const doc = fixtureDocument();
    const before = JSON.stringify(doc.links);
    const built = buildGraph(doc.nodes, doc.links);
    expect(JSON.stringify(doc.links)).toBe(before); // the document keeps its strings
    // 3d-force-graph (d3-force) rewrites the endpoints of the objects it is
    // given in place; the scene's links must be copies, not the document's.
    expect(built.links.length).toBeGreaterThan(0);
    expect(built.links[0]!).not.toBe(doc.links[0]);
    expect(typeof doc.links[0]!.source).toBe("string");
  });

  it("computes a direct neighborhood across link directions", () => {
    const links: MemoryLink[] = [
      { source: "a", target: "b", relation: "sighting-of" },
      { source: "c", target: "a", relation: "hunt-verdict" },
    ];
    expect(neighborhood("a", links)).toEqual(new Set(["b", "c"]));
    expect(neighborhood("b", links)).toEqual(new Set(["a"]));
  });

  it("resolves neighborhoods after d3 rewrites endpoints to node refs", () => {
    const links: SceneLink[] = [
      { source: { id: "a" }, target: { id: "b" }, relation: "sighting-of" },
      { source: "c", target: { id: "a" }, relation: "hunt-verdict" },
    ];
    expect(neighborhood("a", links)).toEqual(new Set(["b", "c"]));
  });

  it("detail joins survive a build round-trip (regression: subjects showed none)", () => {
    const doc = fixtureDocument();
    buildGraph(doc.nodes, doc.links); // the app builds the scene from the same doc
    const verdict = doc.nodes.find(
      (n): n is Extract<MemoryNode, { kind: "verdict" }> => n.id === "v-0001" && n.kind === "verdict",
    );
    expect(verdict).toBeDefined();
    const vm = detailViewModel(verdict!, doc);
    const subjects = vm.fields.find((f) => f.label === "subjects");
    expect(subjects?.value).toBeDefined();
    expect(subjects?.value).not.toBe("none");
    expect(subjects?.value).toContain(":"); // entity keys, not labels or ids
  });
});

describe("capVisibleSet", () => {
  const nodes: MemoryNode[] = [
    { id: "a1", kind: "entity", label: "a1", entityType: "ip", entityKey: "ip:a1" },
    { id: "a2", kind: "entity", label: "a2", entityType: "ip", entityKey: "ip:a2" },
    { id: "v1", kind: "verdict", label: "v1", outcome: "proven", statement: "s" },
    { id: "g1", kind: "gap", label: "g1" },
    { id: "h1", kind: "hunt", label: "h1" },
    { id: "ep1", kind: "episode", label: "ep1" },
    { id: "s1", kind: "sighting", label: "s1", entityKey: "ip:a1" },
    { id: "s2", kind: "sighting", label: "s2", entityKey: "ip:a1" },
    { id: "s3", kind: "sighting", label: "s3", entityKey: "ip:a2" },
  ];
  const links: MemoryLink[] = [
    { source: "s1", target: "a1", relation: "sighting-of" },
    { source: "s2", target: "a1", relation: "sighting-of" },
    { source: "s3", target: "a2", relation: "sighting-of" },
    { source: "v1", target: "a1", relation: "verdict-subject" },
  ];

  it("trims sightings first and reports the count", () => {
    const capped = capVisibleSet(nodes, links, 7);
    expect(capped.trimmed).toBe(2);
    const kinds = countByKind(capped.nodes);
    expect(kinds.sighting).toBe(1); // s1 kept by id tiebreak
    expect(kinds.entity).toBe(2);
    expect(kinds.verdict).toBe(1);
    // dropped sightings' links go with them
    expect(capped.links).toEqual([
      { source: "s1", target: "a1", relation: "sighting-of" },
      { source: "v1", target: "a1", relation: "verdict-subject" },
    ]);
  });

  it("is a no-op under the cap and returns fresh arrays", () => {
    const capped = capVisibleSet(nodes, links, 100);
    expect(capped.trimmed).toBe(0);
    expect(capped.nodes).toHaveLength(nodes.length);
    expect(capped.links).toHaveLength(links.length);
    expect(capped.nodes).not.toBe(nodes);
  });
});

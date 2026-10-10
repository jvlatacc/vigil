/**
 * Document → 3d-force-graph input.
 *
 * Pure functions: no DOM, no scene. The app wires the result into
 * `3d-force-graph` (nodes need id/val/color; links need source/target).
 *
 * - Degree-based sizing: val grows with the square root of degree, so hubs
 *   stand out without drowning their neighbors.
 * - Orphan pruning: degree-0 nodes float in a force layout and carry no
 *   navigable context, so they are dropped and counted (the count surfaces in
 *   the status line, never silently).
 * - Kind colors are static — the vocabulary is closed, so the legend is
 *   generated from this map, not inferred from data.
 */

import type { LinkRelation, MemoryLink, MemoryNode, NodeKind } from "./types";

export const NODE_KIND_COLORS: Record<NodeKind, string> = {
  entity: "#4c8dff",
  sighting: "#94a3b8",
  verdict: "#f59e0b",
  gap: "#ef4444",
  hunt: "#a78bfa",
  episode: "#2dd4bf",
};

/** Datum shape `3d-force-graph` consumes, plus the original node for the detail panel. */
export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  val: number;
  color: string;
  degree: number;
  node: MemoryNode;
}

/**
 * A link as the scene holds it. d3-force rewrites `source`/`target` from id
 * strings to node-object references in place during layout, so post-layout
 * graphs may carry either form; resolve with `endpointId`.
 */
export interface SceneLink {
  source: string | { id: string };
  target: string | { id: string };
  relation: LinkRelation;
}

export interface BuiltGraph {
  nodes: GraphNode[];
  links: SceneLink[];
  /** Degree-0 nodes dropped by orphan pruning. */
  pruned: number;
}

export function degreeMap(links: readonly MemoryLink[]): Map<string, number> {
  const degrees = new Map<string, number>();
  for (const link of links) {
    degrees.set(link.source, (degrees.get(link.source) ?? 0) + 1);
    degrees.set(link.target, (degrees.get(link.target) ?? 0) + 1);
  }
  return degrees;
}

/** Monotone, sub-linear size from degree. Degree 0 → 1, 9 → 4, 25 → 6. */
export function nodeSize(degree: number): number {
  return 1 + Math.sqrt(Math.max(degree, 0));
}

export function buildGraph(nodes: readonly MemoryNode[], links: readonly MemoryLink[]): BuiltGraph {
  const degrees = degreeMap(links);
  const graphNodes: GraphNode[] = [];
  let pruned = 0;
  for (const node of nodes) {
    const degree = degrees.get(node.id) ?? 0;
    if (degree === 0) {
      pruned += 1;
      continue;
    }
    graphNodes.push({
      id: node.id,
      kind: node.kind,
      label: node.label,
      val: nodeSize(degree),
      color: NODE_KIND_COLORS[node.kind],
      degree,
      node,
    });
  }
  // A pruned node has no links by definition; the endpoint check keeps the
  // invariant explicit so refactors cannot break it quietly.
  const kept = new Set(graphNodes.map((n) => n.id));
  // Clone: 3d-force-graph (d3-force) mutates the link objects it is given,
  // rewriting endpoints into node references. Handing it the document's own
  // link objects would corrupt every later reader — detail joins, hover
  // neighborhoods, rebuilds. The scene may have its copies; the document
  // keeps its strings.
  const keptLinks: SceneLink[] = links
    .filter((l) => kept.has(l.source) && kept.has(l.target))
    .map((l) => ({ source: l.source, target: l.target, relation: l.relation }));
  return { nodes: graphNodes, links: keptLinks, pruned };
}

/**
 * Initial visible-set cap for large exports: entities/verdicts/gaps first,
 * sightings trimmed last — sightings are the first filter to toggle off and
 * the least navigational value per node. Never renders a hairball silently:
 * the caller states the trimmed count.
 */
const KEEP_PRIORITY: readonly NodeKind[] = ["entity", "verdict", "gap", "hunt", "episode", "sighting"];

export interface CappedSet {
  nodes: MemoryNode[];
  links: MemoryLink[];
  trimmed: number;
}

export function capVisibleSet(
  nodes: readonly MemoryNode[],
  links: readonly MemoryLink[],
  max: number,
): CappedSet {
  if (nodes.length <= max) return { nodes: [...nodes], links: [...links], trimmed: 0 };
  const rank = new Map<NodeKind, number>(KEEP_PRIORITY.map((k, i) => [k, i]));
  const sorted = [...nodes].sort((a, b) => {
    const ra = rank.get(a.kind) ?? KEEP_PRIORITY.length;
    const rb = rank.get(b.kind) ?? KEEP_PRIORITY.length;
    return ra - rb || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  });
  const kept = sorted.slice(0, max);
  const keptIds = new Set(kept.map((n) => n.id));
  return {
    nodes: kept,
    links: links.filter((l) => keptIds.has(l.source) && keptIds.has(l.target)),
    trimmed: nodes.length - kept.length,
  };
}

/** Endpoint as id — derefs the node references d3 writes in during layout. */
export function endpointId(end: string | { id?: unknown }): string {
  return typeof end === "string" ? end : String(end.id ?? "");
}

/** Direct neighborhood of a node — hover highlight, detail panel "connected" counts. */
export function neighborhood(id: string, links: readonly SceneLink[]): Set<string> {
  const ids = new Set<string>();
  for (const link of links) {
    const s = endpointId(link.source);
    const t = endpointId(link.target);
    if (s === id) ids.add(t);
    else if (t === id) ids.add(s);
  }
  return ids;
}

/** Relation table (source kind → target kind) — shared by validator and tests. */
export const LINK_TABLE: Readonly<Record<LinkRelation, { source: NodeKind; target: NodeKind }>> = {
  "sighting-of": { source: "sighting", target: "entity" },
  "verdict-subject": { source: "verdict", target: "entity" },
  "verdict-source": { source: "verdict", target: "sighting" },
  "gap-subject": { source: "gap", target: "entity" },
  "hunt-verdict": { source: "hunt", target: "verdict" },
  "hunt-gap": { source: "hunt", target: "gap" },
  "episode-entity": { source: "episode", target: "entity" },
};

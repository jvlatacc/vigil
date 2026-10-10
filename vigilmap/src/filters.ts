/**
 * Filter state + predicates.
 *
 * Hide-not-delete: filtering derives a visible subgraph; the document is never
 * mutated, so un-checking a toggle restores exactly what was hidden. Filters
 * AND together.
 *
 * Search is NOT a visibility filter — per the spec's interaction contract,
 * search jumps to and selects the matching entity (`findMatches`). The
 * scaffold's `Filters.search` visibility semantics are preserved inside
 * `passesFilters` (and therefore `selectVisibleNodes`) so existing callers
 * behave identically; the UI's search box drives jump-to-select instead.
 */

import type { MemoryGraphDocument, MemoryLink, MemoryNode, NodeKind } from "./types";
import { NODE_KINDS } from "./types";
import type { Filters } from "./store";

export interface TimeWindow {
  /** ISO-8601 date or timestamp; either bound optional. */
  from?: string;
  to?: string;
}

function epoch(value: string | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Time-window membership. Interval-valued kinds (sighting, hunt) pass when
 * their window overlaps the filter; point-valued kinds (verdict, episode) pass
 * when their instant falls inside it. A node with no time of its own (entities,
 * gaps) always passes — the window filters events, not the timeless.
 */
export function matchesTimeWindow(node: MemoryNode, window: TimeWindow): boolean {
  const from = epoch(window.from);
  const to = epoch(window.to);
  if (from === null && to === null) return true;

  const contains = (instant: number): boolean =>
    (from === null || instant >= from) && (to === null || instant <= to);

  const overlaps = (lo: number, hi: number): boolean =>
    (to === null || lo <= to) && (from === null || hi >= from);

  switch (node.kind) {
    case "sighting": {
      const start = epoch(node.observedFrom);
      const end = epoch(node.observedTo);
      if (start === null && end === null) return true;
      const lo = start ?? end;
      const hi = end ?? start;
      if (lo === null || hi === null) return true; // single-sided bounds
      return overlaps(lo, hi);
    }
    case "hunt": {
      const start = epoch(node.startedAt);
      const end = epoch(node.endedAt);
      if (start === null && end === null) return true;
      const lo = start ?? end;
      const hi = end ?? start;
      if (lo === null || hi === null) return true; // open-ended hunt
      return overlaps(lo, hi);
    }
    case "verdict": {
      const instant = epoch(node.concludedAt);
      return instant === null ? true : contains(instant);
    }
    case "episode": {
      const instant = epoch(node.occurredAt);
      return instant === null ? true : contains(instant);
    }
    default:
      return true; // entity, gap — timeless
  }
}

/** The one node predicate — kind, entity type, outcome, search, time window, ANDed. */
export function passesFilters(node: MemoryNode, filters: Filters): boolean {
  if (!filters.kinds[node.kind]) return false;
  const search = filters.search.trim().toLowerCase();
  switch (node.kind) {
    case "entity":
      if (!filters.entityTypes[node.entityType]) return false;
      if (search && !node.entityKey.toLowerCase().includes(search)) return false;
      break;
    case "sighting":
      if (search && !node.entityKey.toLowerCase().includes(search)) return false;
      break;
    case "verdict":
      if (!filters.outcomes[node.outcome]) return false;
      break;
    default:
      break;
  }
  if (filters.timeWindow && !matchesTimeWindow(node, filters.timeWindow)) return false;
  return true;
}

export interface KindCounts {
  total: number;
  visible: number;
}

export interface FilteredGraph {
  nodes: MemoryNode[];
  /** Links whose both endpoints are visible — the graph only ever shows these. */
  links: MemoryLink[];
  counts: Record<NodeKind, KindCounts>;
}

export function applyFilters(doc: MemoryGraphDocument, filters: Filters): FilteredGraph {
  const nodes = doc.nodes.filter((n) => passesFilters(n, filters));
  const visibleIds = new Set(nodes.map((n) => n.id));
  const links = doc.links.filter((l) => visibleIds.has(l.source) && visibleIds.has(l.target));

  const counts = Object.fromEntries(
    NODE_KINDS.map((kind) => {
      const total = doc.nodes.reduce((n, node) => n + (node.kind === kind ? 1 : 0), 0);
      const visible = nodes.reduce((n, node) => n + (node.kind === kind ? 1 : 0), 0);
      return [kind, { total, visible }];
    }),
  ) as Record<NodeKind, KindCounts>;

  return { nodes, links, counts };
}

export type SearchRank = 1 | 2 | 3; // exact key | key prefix | substring

/**
 * Search matches entity keys (the search box's stated purpose) and every
 * node's label, ranked: exact entity key, then key prefix, then substring.
 * Jump-and-select, not a visibility filter.
 */
export function findMatches(doc: MemoryGraphDocument, query: string, limit = 10): MemoryNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored: Array<{ node: MemoryNode; rank: SearchRank }> = [];
  for (const node of doc.nodes) {
    const label = node.label.toLowerCase();
    if (node.kind === "entity") {
      const key = node.entityKey.toLowerCase();
      if (key === q) scored.push({ node, rank: 1 });
      else if (key.startsWith(q)) scored.push({ node, rank: 2 });
      else if (key.includes(q) || label.includes(q)) scored.push({ node, rank: 3 });
    } else if (label.includes(q)) {
      scored.push({ node, rank: 3 });
    }
  }
  return scored
    .sort((a, b) => a.rank - b.rank)
    .slice(0, limit)
    .map((s) => s.node);
}

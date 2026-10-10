/**
 * Minimal explorer state: document, selection (0–1 nodes), filters.
 *
 * Every change is a pure derivation — filters apply a predicate, selection
 * drives the detail panel — nothing mutates the document. The observable
 * wrapper is a store of last resort: state in, listeners out, nothing else.
 *
 * The scaffold carried the filters the ready panel needs: kind, entity type
 * and outcome toggles plus entity search. The time window and the shared node
 * predicate live in `filters.ts`; `selectVisibleNodes` delegates there so both
 * entry points stay one implementation.
 */

import type { EntityType, MemoryGraphDocument, MemoryNode, NodeKind, VerdictOutcome } from "./types";
import { ENTITY_TYPES, NODE_KINDS, VERDICT_OUTCOMES } from "./types";
import type { TimeWindow } from "./filters";
import { passesFilters } from "./filters";

export interface Filters {
  /** true = visible. All-on by default. */
  kinds: Record<NodeKind, boolean>;
  /** true = visible. All-on by default. */
  entityTypes: Record<EntityType, boolean>;
  /** true = visible. All-on by default. */
  outcomes: Record<VerdictOutcome, boolean>;
  /** Case-insensitive substring match on entity keys. */
  search: string;
  /** ISO-8601 bounds, either optional; null = no window. */
  timeWindow: TimeWindow | null;
}

function allOn<T extends string>(values: readonly T[]): Record<T, boolean> {
  return Object.fromEntries(values.map((v) => [v, true])) as Record<T, boolean>;
}

export function noFilters(): Filters {
  return {
    kinds: allOn(NODE_KINDS),
    entityTypes: allOn(ENTITY_TYPES),
    outcomes: allOn(VERDICT_OUTCOMES),
    search: "",
    timeWindow: null,
  };
}

export interface ExplorerState {
  document: MemoryGraphDocument | null;
  selectedNodeId: string | null;
  filters: Filters;
  /** Set when a load failed — drives the error state. */
  error: string | null;
}

export function initialState(): ExplorerState {
  return {
    document: null,
    selectedNodeId: null,
    filters: noFilters(),
    error: null,
  };
}

/** The four app states, derived — never stored. */
export type AppState = "loading" | "error" | "empty" | "ready";

export function deriveAppState(state: Pick<ExplorerState, "document" | "error">): AppState {
  if (state.error !== null) return "error";
  if (state.document === null) return "loading";
  return state.document.nodes.length === 0 ? "empty" : "ready";
}

export function countByKind(document: MemoryGraphDocument): Record<NodeKind, number> {
  const counts = Object.fromEntries(NODE_KINDS.map((k) => [k, 0])) as Record<NodeKind, number>;
  for (const node of document.nodes) {
    counts[node.kind] += 1;
  }
  return counts;
}

/** Nodes that pass the filters, in document order. */
export function selectVisibleNodes(
  document: MemoryGraphDocument,
  filters: Filters,
): MemoryNode[] {
  return document.nodes.filter((node) => passesFilters(node, filters));
}

/** A selected node the user cannot see is a state lie — selection clears instead. */
export function resolveSelection(
  selectedNodeId: string | null,
  visibleNodes: readonly MemoryNode[],
): string | null {
  if (selectedNodeId === null) return null;
  return visibleNodes.some((node) => node.id === selectedNodeId) ? selectedNodeId : null;
}

// ---------------------------------------------------------------------------
// Observable store
// ---------------------------------------------------------------------------

export interface ExplorerStore {
  get: () => ExplorerState;
  set: (patch: Partial<ExplorerState>) => void;
  subscribe: (listener: (state: ExplorerState) => void) => () => void;
}

export function createStore(initial: ExplorerState = initialState()): ExplorerStore {
  let state = initial;
  const listeners = new Set<(state: ExplorerState) => void>();
  return {
    get: () => state,
    set(patch: Partial<ExplorerState>) {
      state = { ...state, ...patch };
      for (const listener of listeners) listener(state);
    },
    subscribe(listener: (state: ExplorerState) => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

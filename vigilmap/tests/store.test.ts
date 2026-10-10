/**
 * Store state and pure derivations: counts, visibility filters, selection
 * survival, and the derived app state.
 */

import { describe, expect, it, vi } from "vitest";
import {
  countByKind,
  createStore,
  deriveAppState,
  noFilters,
  resolveSelection,
  selectVisibleNodes,
} from "../src/store";
import { validDocument } from "./helpers";

describe("deriveAppState", () => {
  it("derives loading before a document exists", () => {
    expect(deriveAppState({ document: null, error: null })).toBe("loading");
  });

  it("derives error when a load failed", () => {
    expect(deriveAppState({ document: null, error: "document rejected: …" })).toBe("error");
  });

  it("derives empty for an empty-but-valid document", () => {
    const doc = validDocument();
    doc.nodes = [];
    expect(deriveAppState({ document: doc, error: null })).toBe("empty");
  });

  it("derives ready when a document with nodes is loaded", () => {
    expect(deriveAppState({ document: validDocument(), error: null })).toBe("ready");
  });
});

describe("countByKind", () => {
  it("counts every kind present and zeroes the absent ones", () => {
    const counts = countByKind(validDocument());
    expect(counts.entity).toBe(2);
    expect(counts.sighting).toBe(1);
    expect(counts.verdict).toBe(1);
    expect(counts.hunt).toBe(1);
    expect(counts.gap).toBe(0);
    expect(counts.episode).toBe(0);
  });
});

describe("selectVisibleNodes", () => {
  it("returns everything with no filters", () => {
    expect(selectVisibleNodes(validDocument(), noFilters())).toHaveLength(5);
  });

  it("hides nodes whose kind is toggled off", () => {
    const filters = noFilters();
    filters.kinds.sighting = false;
    const visible = selectVisibleNodes(validDocument(), filters);
    expect(visible).toHaveLength(4);
    expect(visible.every((n) => n.kind !== "sighting")).toBe(true);
  });

  it("filters entity types", () => {
    const filters = noFilters();
    filters.entityTypes.ip = false;
    expect(selectVisibleNodes(validDocument(), filters)).toHaveLength(4);
  });

  it("filters verdict outcomes", () => {
    const filters = noFilters();
    filters.outcomes.proven = false;
    expect(selectVisibleNodes(validDocument(), filters)).toHaveLength(4);
  });

  it("search matches entity keys case-insensitively", () => {
    // The search box is "search entity key…": it constrains nodes that carry
    // an entityKey (entities, sightings). Kinds without one — verdicts, hunts,
    // gaps, episodes — are the context around the match and stay visible.
    const filters = noFilters();
    filters.search = "203.0.113";
    const visible = selectVisibleNodes(validDocument(), filters);
    expect(visible.map((n) => n.id)).toEqual(["ip:203.0.113.7", "v-001", "h-001"]);
  });

  it("filters AND together", () => {
    const filters = noFilters();
    filters.outcomes.proven = false;
    filters.entityTypes.ip = false;
    expect(selectVisibleNodes(validDocument(), filters)).toHaveLength(3);
  });
});

describe("resolveSelection", () => {
  it("keeps the selection while the node stays visible", () => {
    expect(resolveSelection("v-001", selectVisibleNodes(validDocument(), noFilters()))).toBe("v-001");
  });

  it("clears the selection when the node is filtered out", () => {
    const filters = noFilters();
    filters.kinds.verdict = false;
    expect(resolveSelection("v-001", selectVisibleNodes(validDocument(), filters))).toBeNull();
  });
});

describe("createStore", () => {
  it("notifies subscribers on set and supports unsubscribe", () => {
    const store = createStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.set({ selectedNodeId: "v-001" });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.get().selectedNodeId).toBe("v-001");

    unsubscribe();
    store.set({ selectedNodeId: null });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

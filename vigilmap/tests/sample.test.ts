import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildGraph } from "../src/graph";
import { applyFilters } from "../src/filters";
import { noFilters } from "../src/store";
import { validate } from "../src/validate";
import { ENTITY_TYPES, VERDICT_OUTCOMES, type MemoryGraphDocument } from "../src/types";

const SAMPLE_URL = new URL("../public/data/sample-memory.json", import.meta.url);

function sampleDocument(): MemoryGraphDocument {
  const raw = readFileSync(SAMPLE_URL, "utf8");
  return JSON.parse(raw) as MemoryGraphDocument;
}

describe("bundled sample-memory.json", () => {
  it("passes the app's own validator (the bundled demo cannot rot)", () => {
    const result = validate(sampleDocument());
    expect(result.ok).toBe(true);
  });

  it("carries the v1 schema, a provenance source, and a fixed vintage", () => {
    const doc = sampleDocument();
    expect(doc.schemaVersion).toBe(1);
    expect(doc.source).toBe("sample");
    expect(doc.generatedAt).toBe("2026-09-18T15:00:00Z"); // fixed — dataset vintage, not run time
  });

  it("covers the demo story: all five outcomes", () => {
    const doc = sampleDocument();
    const outcomes = new Set(
      doc.nodes.filter((n) => n.kind === "verdict").map((n) => (n.kind === "verdict" ? n.outcome : "")),
    );
    expect([...outcomes].sort()).toEqual([...VERDICT_OUTCOMES].sort());
  });

  it("covers every entity type", () => {
    const doc = sampleDocument();
    const types = new Set(
      doc.nodes.filter((n) => n.kind === "entity").map((n) => (n.kind === "entity" ? n.entityType : "")),
    );
    expect([...types].sort()).toEqual([...ENTITY_TYPES].sort());
  });

  it("has at least one gap and one learning episode, and both hunts conclude verdicts", () => {
    const doc = sampleDocument();
    expect(doc.nodes.some((n) => n.kind === "gap")).toBe(true);
    expect(doc.nodes.some((n) => n.kind === "episode")).toBe(true);
    const huntIds = new Set(doc.nodes.filter((n) => n.kind === "hunt").map((n) => n.id));
    const huntsWithVerdicts = new Set(
      doc.links.filter((l) => l.relation === "hunt-verdict").map((l) => l.source),
    );
    for (const hunt of huntIds) expect(huntsWithVerdicts.has(hunt)).toBe(true);
  });

  it("renders without orphans and shows the full document under default filters", () => {
    const doc = sampleDocument();
    const built = buildGraph(doc.nodes, doc.links);
    expect(built.pruned).toBe(0);
    const filtered = applyFilters(doc, noFilters());
    expect(filtered.nodes).toHaveLength(doc.nodes.length);
    expect(filtered.links).toHaveLength(doc.links.length);
  });

  it("keeps the proven verdict to the 1–3 subject bound with techniques", () => {
    const doc = sampleDocument();
    const proven = doc.nodes.find((n) => n.kind === "verdict" && n.outcome === "proven")!;
    if (proven.kind !== "verdict") return; // narrowing formality
    const subjects = doc.links.filter(
      (l) => l.relation === "verdict-subject" && l.source === proven.id,
    );
    expect(subjects.length).toBeGreaterThanOrEqual(1);
    expect(subjects.length).toBeLessThanOrEqual(3);
    expect(proven.techniques?.length).toBeGreaterThan(0);
  });
});

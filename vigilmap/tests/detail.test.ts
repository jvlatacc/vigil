import { describe, expect, it } from "vitest";
import { detailViewModel } from "../src/detail";
import { fixtureDocument, nodeWithExtras } from "./test-fixtures";

const doc = fixtureDocument();

function fieldOf(vm: ReturnType<typeof detailViewModel>, label: string) {
  return vm.fields.find((f) => f.label === label);
}

describe("detailViewModel — verdict", () => {
  const verdict = doc.nodes.find((n) => n.id === "v-0001")!;

  it("badges the outcome with a tone", () => {
    const vm = detailViewModel(verdict, doc);
    expect(vm.badge).toEqual({ text: "proven", tone: "good" });
  });

  it("lists statement, rationale, subjects, techniques, sources, hunt, conclusion", () => {
    const vm = detailViewModel(verdict, doc);
    expect(fieldOf(vm, "statement")?.value).toBe("Host beacons to the control IP.");
    expect(fieldOf(vm, "rationale")?.value).toBe("Two sources agree.");
    expect(fieldOf(vm, "subjects")?.value).toBe("ip:10.0.0.1, domain:lan.example.com");
    expect(fieldOf(vm, "subjects")?.mono).toBe(true);
    expect(fieldOf(vm, "techniques")?.value).toBe("T1071");
    expect(fieldOf(vm, "sources")?.value).toBe("2 sources");
    expect(fieldOf(vm, "hunt")?.value).toBe("hunt h-0001");
    expect(fieldOf(vm, "concluded")?.value).toBe("2026-09-15T17:00:00Z");
  });

  it("surfaces producer confidence when present", () => {
    const verdict = doc.nodes.find((n) => n.id === "v-0001")!;
    const withConfidence = { ...verdict, confidence: 0.87 };
    const vm = detailViewModel(withConfidence, doc);
    expect(fieldOf(vm, "confidence")?.value).toBe("0.87");
  });

  it("degrades gracefully when optional fields are absent", () => {
    const minimal = doc.nodes.find((n) => n.id === "v-0002")!;
    const vm = detailViewModel(minimal, doc);
    expect(vm.badge).toEqual({ text: "false_positive", tone: "bad" });
    expect(fieldOf(vm, "rationale")).toBeUndefined();
    expect(fieldOf(vm, "techniques")).toBeUndefined();
    expect(fieldOf(vm, "sources")?.value).toBe("0 sources");
    expect(fieldOf(vm, "subjects")?.value).toBe("ip:10.0.0.1");
  });
});

describe("detailViewModel — entity", () => {
  it("shows type, key, sighting count, and linked verdicts", () => {
    const entity = doc.nodes.find((n) => n.id === "ip:10.0.0.1")!;
    const vm = detailViewModel(entity, doc);
    expect(vm.badge).toEqual({ text: "ip", tone: "info" });
    expect(fieldOf(vm, "entity key")?.value).toBe("ip:10.0.0.1");
    expect(fieldOf(vm, "sightings")?.value).toBe("2");
    const verdicts = fieldOf(vm, "linked verdicts")?.value ?? "";
    expect(verdicts).toContain("proven: beacon to control");
    expect(verdicts).toContain("false_positive: scanner");
  });
});

describe("detailViewModel — sighting", () => {
  it("shows its entity, window, tier, and investigation", () => {
    const sighting = doc.nodes.find((n) => n.id === "s-0001")!;
    const vm = detailViewModel(sighting, doc);
    expect(fieldOf(vm, "entity")?.value).toBe("ip:10.0.0.1");
    expect(fieldOf(vm, "window")?.value).toBe(
      "2026-09-14T09:00:00Z → 2026-09-14T09:00:00Z",
    );
    expect(fieldOf(vm, "source tier")?.value).toBe("observed");
    expect(fieldOf(vm, "investigation")?.value).toBe("inv-1");
  });

  it("renders a single-sided window without an arrow", () => {
    const sighting = doc.nodes.find((n) => n.id === "s-0003")!;
    const vm = detailViewModel(sighting, doc);
    expect(fieldOf(vm, "window")).toBeUndefined(); // no time at all
  });
});

describe("detailViewModel — gap", () => {
  it("shows disposition, reason, subjects, and hunt", () => {
    const gap = doc.nodes.find((n) => n.id === "g-0001")!;
    const vm = detailViewModel(gap, doc);
    expect(fieldOf(vm, "disposition")?.value).toBe("deferred");
    expect(fieldOf(vm, "reason")?.value).toBe("No packet capture.");
    expect(fieldOf(vm, "subjects")?.value).toBe("ip:10.0.0.1");
    expect(fieldOf(vm, "hunt")?.value).toBe("hunt h-0001");
  });
});

describe("detailViewModel — hunt", () => {
  it("shows objective, bounds, verdicts, and gaps", () => {
    const hunt = doc.nodes.find((n) => n.id === "h-0001")!;
    const vm = detailViewModel(hunt, doc);
    expect(fieldOf(vm, "objective")?.value).toBe("Find beaconing.");
    expect(fieldOf(vm, "started")?.value).toBe("2026-09-14T08:00:00Z");
    expect(fieldOf(vm, "ended")?.value).toBe("2026-09-15T17:00:00Z");
    const verdicts = fieldOf(vm, "verdicts")?.value ?? "";
    expect(verdicts).toContain("proven: beacon to control");
    expect(verdicts).toContain("false_positive: scanner");
    expect(fieldOf(vm, "gaps")?.value).toBe("gap: no PCAP");
  });
});

describe("detailViewModel — episode", () => {
  it("shows summary, occurrence, and entities", () => {
    const episode = doc.nodes.find((n) => n.id === "e-0001")!;
    const vm = detailViewModel(episode, doc);
    expect(fieldOf(vm, "summary")?.value).toBe("Beacons cluster in off-hours.");
    expect(fieldOf(vm, "occurred")?.value).toBe("2026-09-15T18:00:00Z");
    expect(fieldOf(vm, "entities")?.value).toBe("ip:10.0.0.1");
  });
});

describe("rawExtras", () => {
  it("exposes unknown payload fields as a raw JSON section", () => {
    const vm = detailViewModel(nodeWithExtras(), doc);
    expect(vm.raw).toBeDefined();
    expect(vm.raw).toContain("sanityExtra");
  });

  it("omits the raw section for contract-clean nodes", () => {
    const entity = doc.nodes.find((n) => n.id === "ip:10.0.0.1")!;
    expect(detailViewModel(entity, doc).raw).toBeUndefined();
  });
});

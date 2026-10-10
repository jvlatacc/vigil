/**
 * Contract validation: every rejection case the spec names must fail with a
 * named error that identifies the offending element, and a valid document
 * must pass.
 */

import { describe, expect, it } from "vitest";
import { validate } from "../src/validate";
import type { MemoryGraphDocument } from "../src/types";
import { emptyDocument, validDocument, withMutation } from "./helpers";

function errorsOf(candidate: unknown): string[] {
  const result = validate(candidate);
  expect(result.ok, "expected the document to be rejected").toBe(false);
  return result.ok === false ? result.errors : [];
}

/** Indexed access under noUncheckedIndexedAccess — a missing slot is a test bug. */
function nodeAsRecord(doc: MemoryGraphDocument, index: number): Record<string, unknown> {
  const node = doc.nodes[index];
  if (node === undefined) throw new Error(`no node at index ${index}`);
  return node as unknown as Record<string, unknown>;
}

function linkAsRecord(doc: MemoryGraphDocument, index: number): Record<string, unknown> {
  const link = doc.links[index];
  if (link === undefined) throw new Error(`no link at index ${index}`);
  return link as unknown as Record<string, unknown>;
}

describe("validate — accepts", () => {
  it("accepts a valid document", () => {
    const result = validate(validDocument());
    expect(result.ok).toBe(true);
  });

  it("accepts an empty-but-valid document", () => {
    const result = validate(emptyDocument());
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.document.nodes).toHaveLength(0);
  });
});

describe("validate — rejection cases", () => {
  it("rejects schemaVersion !== 1 and names the found version", () => {
    const errors = errorsOf(withMutation((doc) => { doc.schemaVersion = 2 as never; }));
    expect(errors.some((e) => e.includes("schemaVersion") && e.includes("2") && e.includes("1"))).toBe(true);
  });

  it("rejects a missing schemaVersion", () => {
    const errors = errorsOf(
      withMutation((doc) => { delete (doc as unknown as Record<string, unknown>).schemaVersion; }),
    );
    expect(errors.some((e) => e.includes("schemaVersion"))).toBe(true);
  });

  it("rejects an unknown node kind, naming the kind and node", () => {
    const errors = errorsOf(withMutation((doc) => { nodeAsRecord(doc, 0).kind = "beacon"; }));
    expect(
      errors.some((e) => e.includes("unknown kind") && e.includes("beacon") && e.includes("domain:evil-lure.example")),
    ).toBe(true);
  });

  it("rejects an unknown entityType, naming the type", () => {
    const errors = errorsOf(withMutation((doc) => { nodeAsRecord(doc, 0).entityType = "mutex"; }));
    expect(errors.some((e) => e.includes("unknown entityType") && e.includes("mutex"))).toBe(true);
  });

  it("rejects an unknown verdict outcome, naming the value", () => {
    const errors = errorsOf(withMutation((doc) => { nodeAsRecord(doc, 3).outcome = "maybe"; }));
    expect(errors.some((e) => e.includes("unknown outcome") && e.includes("maybe"))).toBe(true);
  });

  it("rejects an unknown link relation, naming the value", () => {
    const errors = errorsOf(withMutation((doc) => { linkAsRecord(doc, 0).relation = "knows-about"; }));
    expect(errors.some((e) => e.includes("unknown relation") && e.includes("knows-about"))).toBe(true);
  });

  it("rejects a dangling link source, naming the id", () => {
    const errors = errorsOf(withMutation((doc) => { linkAsRecord(doc, 0).source = "s-999"; }));
    expect(errors.some((e) => e.includes("dangling link") && e.includes("s-999"))).toBe(true);
  });

  it("rejects a dangling link target, naming the id", () => {
    const errors = errorsOf(withMutation((doc) => { linkAsRecord(doc, 0).target = "domain:ghost.example"; }));
    expect(errors.some((e) => e.includes("dangling link") && e.includes("domain:ghost.example"))).toBe(true);
  });

  it("rejects duplicate node ids", () => {
    const errors = errorsOf(
      withMutation((doc) => {
        const first = doc.nodes[0];
        if (first === undefined) throw new Error("no node at index 0");
        doc.nodes.push(structuredClone(first));
      }),
    );
    expect(errors.some((e) => e.includes("duplicate node id") && e.includes("domain:evil-lure.example"))).toBe(true);
  });

  it("rejects an entity node whose entityKey does not start with its entityType", () => {
    const errors = errorsOf(withMutation((doc) => { nodeAsRecord(doc, 0).entityKey = "ip:203.0.113.7"; }));
    expect(
      errors.some((e) => e.includes("entityKey") && e.includes("does not start with") && e.includes("domain")),
    ).toBe(true);
  });

  it("rejects a verdict confidence outside 0..1", () => {
    const errors = errorsOf(withMutation((doc) => { nodeAsRecord(doc, 3).confidence = 1.5; }));
    expect(errors.some((e) => e.includes("confidence"))).toBe(true);
  });

  it("rejects a non-object document", () => {
    expect(errorsOf(["not", "an", "object"])).toContain("document must be a JSON object");
    expect(errorsOf("a string")).toContain("document must be a JSON object");
    expect(errorsOf(null)).toContain("document must be a JSON object");
  });

  it("rejects a missing nodes or links array", () => {
    const noNodes = withMutation((doc) => { delete (doc as unknown as Record<string, unknown>).nodes; });
    expect(errorsOf(noNodes).some((e) => e.includes("nodes must be an array"))).toBe(true);
    const noLinks = withMutation((doc) => { delete (doc as unknown as Record<string, unknown>).links; });
    expect(errorsOf(noLinks).some((e) => e.includes("links must be an array"))).toBe(true);
  });
});

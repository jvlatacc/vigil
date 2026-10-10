/**
 * Source resolution: three paths in, one funnel through the validator.
 * Fetch failure and validation failure both land in the error state; an
 * empty-but-valid document loads and the app shows the empty note.
 */

import { describe, expect, it } from "vitest";
import { dataUrlFromSearch, loadDroppedFile, resolveSource } from "../src/load";
import { deriveAppState, initialState } from "../src/store";
import { emptyDocument, validDocument } from "./helpers";
import sampleDocument from "../public/data/sample-memory.json";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fileResponse(body: string): Response {
  return new Response(body, { status: 200, headers: { "content-type": "application/json" } });
}

describe("dataUrlFromSearch", () => {
  it("returns null when the parameter is absent or empty", () => {
    expect(dataUrlFromSearch("")).toBeNull();
    expect(dataUrlFromSearch("?foo=bar")).toBeNull();
    expect(dataUrlFromSearch("?data=")).toBeNull();
  });

  it("returns the data URL when present", () => {
    expect(dataUrlFromSearch("?data=https://example.com/memory.json")).toBe(
      "https://example.com/memory.json",
    );
  });
});

describe("resolveSource — ?data= path", () => {
  it("fetches and validates a ?data= document (mocked fetch)", async () => {
    const outcome = await resolveSource({
      search: "?data=https://example.com/memory.json",
      fetchImpl: (async () => jsonResponse(validDocument())) as typeof fetch,
    });
    expect(outcome.status).toBe("loaded");
    if (outcome.status === "loaded") {
      expect(outcome.document.nodes).toHaveLength(5);
      expect(outcome.source).toContain("example.com");
    }
  });

  it("lands a fetch failure in the error state, naming the URL", async () => {
    const outcome = await resolveSource({
      search: "?data=https://example.com/memory.json",
      fetchImpl: (async () => {
        throw new Error("network down");
      }) as typeof fetch,
    });
    expect(outcome.status).toBe("error");
    if (outcome.status === "error") {
      expect(outcome.message).toContain("failed to fetch");
      expect(outcome.message).toContain("example.com/memory.json");
    }
  });

  it("lands an HTTP error in the error state", async () => {
    const outcome = await resolveSource({
      search: "?data=https://example.com/missing.json",
      fetchImpl: (async () => jsonResponse("not found", 404)) as typeof fetch,
    });
    expect(outcome.status).toBe("error");
    if (outcome.status === "error") expect(outcome.message).toContain("404");
  });

  it("lands a validation failure from ?data= in the error state, naming the violation", async () => {
    const bad = validDocument();
    (bad.nodes[0] as unknown as Record<string, unknown>).kind = "beacon";
    const outcome = await resolveSource({
      search: "?data=https://example.com/memory.json",
      fetchImpl: (async () => jsonResponse(bad)) as typeof fetch,
    });
    expect(outcome.status).toBe("error");
    if (outcome.status === "error") {
      expect(outcome.message).toContain("document rejected");
      expect(outcome.message).toContain("beacon");
    }
  });

  it("lands invalid JSON from ?data= in the error state", async () => {
    const outcome = await resolveSource({
      search: "?data=https://example.com/memory.json",
      fetchImpl: (async () => fileResponse("{not json")) as typeof fetch,
    });
    expect(outcome.status).toBe("error");
    if (outcome.status === "error") expect(outcome.message).toContain("not valid JSON");
  });
});

describe("resolveSource — dropped file path", () => {
  const readFile = (body: string) => async () => body;

  it("validates a dropped file", async () => {
    const file = new File([JSON.stringify(validDocument())], "memory.json", {
      type: "application/json",
    });
    const outcome = await loadDroppedFile(file, readFile(JSON.stringify(validDocument())));
    expect(outcome.status).toBe("loaded");
  });

  it("lands a dropped-file validation failure in the error state", async () => {
    const bad = validDocument();
    (bad.nodes[0] as unknown as Record<string, unknown>).entityKey = "ip:203.0.113.7"; // domain node, ip key
    const file = new File([JSON.stringify(bad)], "memory.json", { type: "application/json" });
    const outcome = await loadDroppedFile(file, readFile(JSON.stringify(bad)));
    expect(outcome.status).toBe("error");
    if (outcome.status === "error") {
      expect(outcome.message).toContain("document rejected");
      expect(outcome.message).toContain("does not start with");
    }
  });
});

describe("resolveSource — default bundled sample", () => {
  it("loads and validates the checked-in sample-memory.json", async () => {
    // Serve the real checked-in file through the mocked fetch — the bundled
    // demo cannot rot past the validator unnoticed.
    const outcome = await resolveSource({
      fetchImpl: (async () => fileResponse(JSON.stringify(sampleDocument))) as typeof fetch,
    });
    expect(outcome.status).toBe("loaded");
    if (outcome.status === "loaded") {
      expect(outcome.document.nodes.length).toBeGreaterThan(0);
      expect(outcome.document.source).toBe("sample");
    }
  });
});

describe("empty-but-valid document → empty state", () => {
  it("loads fine and derives the empty app state", async () => {
    const outcome = await resolveSource({
      search: "?data=https://example.com/empty.json",
      fetchImpl: (async () => jsonResponse(emptyDocument())) as typeof fetch,
    });
    expect(outcome.status).toBe("loaded");
    const state = { ...initialState() };
    if (outcome.status === "loaded") state.document = outcome.document;
    expect(deriveAppState(state)).toBe("empty");
  });
});

import * as v from "valibot";
import { describe, expect, it } from "vitest";
import type { InternalToolsBridge } from "../src/config.ts";
import { invokeInternalTool, outcomeOf } from "../src/tools/internal.ts";
import { toolInput } from "../src/tools/schema.ts";

// What the far side must see, and what the model must be told when it does not
// answer. The vocabulary is the contract with the hunt workflow -- a kind that
// arrives as `unavailable` when it was really a refusal sends the model back to
// retry something that will never work.

const FAILURE_KINDS = ["invalid_args", "refused", "timeout", "unavailable", "backend_error"] as const;

function bridgeAnswering(body: unknown, status = 200): InternalToolsBridge & { calls: Request[] } {
  const calls: Request[] = [];
  return {
    url: "http://core.internal/internal/tools/invoke",
    token: "sekrit",
    calls,
    fetch: async (input, init) => {
      calls.push(new Request(input as string, init));
      return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    },
  };
}

describe("the /internal/tools bridge", () => {
  it("presents the bearer token and the tool's bounds", async () => {
    const bridge = bridgeAnswering({ ok: true, rows: [], rowCount: 0, capped: false, sourceSystem: "postgres" });

    await invokeInternalTool({
      bridge,
      tool: "list_alerts",
      args: { severity: "high" },
      maxRows: 50,
      timeoutMs: 15_000,
    });

    const [call] = bridge.calls;
    expect(call).toBeDefined();
    expect(call?.method).toBe("POST");
    expect(call?.headers.get("authorization")).toBe("Bearer sekrit");
    // snake_case, because that is what the far side's Bounds model declares. A
    // bound the endpoint silently drops is not a bound.
    expect(await call?.json()).toEqual({
      tool: "list_alerts",
      args: { severity: "high" },
      bounds: { max_rows: 50, timeout_ms: 15_000 },
    });
  });

  it("passes a successful result through untouched", async () => {
    const rows = [{ id: "a-1", severity: "high" }];
    const bridge = bridgeAnswering({ ok: true, rows, rowCount: 1, capped: true, sourceSystem: "postgres" });

    const outcome = await invokeInternalTool({ bridge, tool: "list_alerts", args: {}, maxRows: 1, timeoutMs: 1_000 });

    expect(outcome).toEqual({ ok: true, rows, rowCount: 1, capped: true, sourceSystem: "postgres" });
  });

  for (const kind of FAILURE_KINDS) {
    it(`preserves the ${kind} failure kind rather than collapsing it`, async () => {
      const bridge = bridgeAnswering({ ok: false, failure: { kind, detail: "as reported" } });

      const outcome = await invokeInternalTool({ bridge, tool: "t", args: {}, maxRows: 1, timeoutMs: 1_000 });

      expect(outcome).toEqual({ ok: false, failure: { kind, detail: "as reported" } });
    });
  }

  it("reports a transport failure as unavailable, not as a backend defect", async () => {
    const bridge: InternalToolsBridge = {
      url: "http://core.internal/internal/tools/invoke",
      token: "sekrit",
      fetch: async () => {
        throw new TypeError("fetch failed");
      },
    };

    const outcome = await invokeInternalTool({ bridge, tool: "t", args: {}, maxRows: 1, timeoutMs: 1_000 });

    expect(outcome).toEqual({ ok: false, failure: { kind: "unavailable", detail: "fetch failed" } });
  });

  it("reports its own deadline as timeout", async () => {
    const bridge: InternalToolsBridge = {
      url: "http://core.internal/internal/tools/invoke",
      token: "sekrit",
      // Never answers. The bridge's own ceiling is what has to end this.
      fetch: (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal?.reason as Error));
        }),
    };

    const outcome = await invokeInternalTool({ bridge, tool: "t", args: {}, maxRows: 1, timeoutMs: 10 });

    expect(outcome).toEqual({ ok: false, failure: { kind: "timeout", timeoutMs: 10 } });
  });

  it("does not record an aborted turn as a tool that failed", async () => {
    const turn = new AbortController();
    const bridge: InternalToolsBridge = {
      url: "http://core.internal/internal/tools/invoke",
      token: "sekrit",
      fetch: (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal?.reason as Error));
        }),
    };

    const pending = invokeInternalTool({
      bridge,
      tool: "t",
      args: {},
      maxRows: 1,
      timeoutMs: 60_000,
      signal: turn.signal,
    });
    turn.abort();

    expect(await pending).toEqual({ ok: false, failure: { kind: "unavailable", detail: "the turn was aborted" } });
  });

  // A body the far side never promised means this hop broke, not that the tool
  // did. Inventing `backend_error` here would page someone for a network blip.
  it("refuses to invent a failure kind", () => {
    expect(outcomeOf({ ok: false, failure: { kind: "kablooey" } })).toEqual({
      ok: false,
      failure: { kind: "unavailable", detail: "the endpoint answered with neither rows nor a known failure" },
    });
    expect(outcomeOf("not json at all")).toEqual({
      ok: false,
      failure: { kind: "unavailable", detail: "the endpoint did not answer with a result" },
    });
  });

  it("reports a non-2xx answer as unavailable with its status", async () => {
    const bridge = bridgeAnswering({ detail: "nope" }, 503);

    const outcome = await invokeInternalTool({ bridge, tool: "t", args: {}, maxRows: 1, timeoutMs: 1_000 });

    expect(outcome).toEqual({ ok: false, failure: { kind: "unavailable", detail: "the endpoint answered 503" } });
  });
});

describe("the JSON Schema translation", () => {
  it("accepts a declared call and rejects one missing a required argument", () => {
    const schema = toolInput({
      type: "object",
      properties: {
        severity: { type: "string", enum: ["low", "high"] },
        limit: { type: "integer" },
        hosts: { type: "array", items: { type: "string" } },
        window: { type: "object", properties: { hours: { type: "number" } }, required: ["hours"] },
      },
      required: ["severity"],
    });

    expect(v.safeParse(schema, { severity: "high", limit: 10, hosts: ["a"], window: { hours: 24 } }).success).toBe(true);
    // An omitted optional is absence, not null: the far side reads a null as a
    // value and would filter on it.
    expect(v.safeParse(schema, { severity: "low" }).success).toBe(true);
    expect(v.safeParse(schema, { limit: 10 }).success).toBe(false);
    expect(v.safeParse(schema, { severity: "critical" }).success).toBe(false);
    expect(v.safeParse(schema, { severity: "high", limit: 1.5 }).success).toBe(false);
  });

  // The far side owns the signature and validates too. A construct this
  // translation does not model must not become a rejection of a call the tool
  // would have accepted.
  it("stays permissive where it cannot be precise", () => {
    const unmodelled = toolInput({ type: "object", properties: { query: { oneOf: [{ type: "string" }] } } });
    expect(v.safeParse(unmodelled, { query: { nested: true } }).success).toBe(true);

    const undeclared = toolInput({ type: "object" });
    expect(v.safeParse(undeclared, { anything: 1 }).success).toBe(true);
  });
});

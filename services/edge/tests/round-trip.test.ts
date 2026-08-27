import { fauxAssistantMessage, fauxProvider, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { init } from "@flue/runtime";
import { start } from "@flue/runtime/node";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../src/agents/chat.ts";
import { type ChatChunk, chatEventReader } from "../src/chat/events.ts";

// A whole turn, end to end, on the real runtime: a chat turn posted through
// Flue's dispatch queue, a tool call bridged to a stubbed /internal/tools, and
// the durable stream read back and projected into the console's frames.
//
// The runtime here is the Node host rather than workerd, so what this proves is
// the seam, not the storage: the same agent module, the same dispatch and read
// contract, the same chunk vocabulary. Durable Object SQLite itself is asserted
// by the wrangler dry-run's migration and binding, not by this file.

const LIST_ALERTS = {
  name: "list_alerts",
  description: "List recent alerts.",
  parameters: {
    type: "object",
    properties: { severity: { type: "string", enum: ["low", "high"] } },
    required: ["severity"],
  },
  maxRows: 50,
  timeoutMs: 15_000,
};

const IDENTITY = {
  userId: "analyst-1",
  scopes: ["alerts:read"],
  tenantId: "tenant-9",
  model: "faux/test",
  systemPrompt: "Answer briefly.",
  tools: [LIST_ALERTS],
};

function toolEndpoint() {
  const calls: { authorization: string | null; body: unknown }[] = [];
  // The global fetch's own parameter types: this package compiles without the DOM
  // lib, where RequestInfo does not exist and a cast would only hide that.
  const fetchStub = vi.fn(async (...args: Parameters<typeof fetch>) => {
    const request = new Request(...args);
    calls.push({ authorization: request.headers.get("authorization"), body: await request.json() });
    return Response.json({
      ok: true,
      rows: [{ id: "alert-1", severity: "high", host: "web-01" }],
      rowCount: 1,
      capped: false,
      sourceSystem: "postgres",
    });
  });
  return { calls, fetchStub };
}

describe("a chat turn, posted and read back", () => {
  let stop: (() => Promise<void>) | undefined;

  beforeEach(() => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "sekrit");
    vi.stubEnv("INTERNAL_TOOLS_URL", "http://core.internal/internal/tools/invoke");
  });

  afterEach(async () => {
    await stop?.();
    stop = undefined;
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("runs the turn, calls the bridged tool, and streams the console's frames", async () => {
    const faux = fauxProvider({ provider: "faux", models: [{ id: "test" }] });
    faux.setResponses([
      // stopReason toolUse, not stop: a turn that asks for a tool has not
      // finished, and a record that claims otherwise is rejected as malformed.
      fauxAssistantMessage([fauxToolCall("list_alerts", { severity: "high" })], { stopReason: "toolUse" }),
      fauxAssistantMessage("One high-severity alert on web-01."),
    ]);
    const { calls, fetchStub } = toolEndpoint();
    vi.stubGlobal("fetch", fetchStub);

    const flue = await start({ agents: [Chat], providers: [faux.provider] });
    stop = () => flue.stop();

    const handle = init(Chat, { id: "conv-round-trip" });
    const receipt = await handle.dispatch({ message: "Any high-severity alerts?", initialData: IDENTITY });

    // Admission is durable and immediate -- this is the 202 the dispatcher
    // returns before the model has said anything.
    expect(receipt.submissionId).toBeTypeOf("string");

    const chunks: ChatChunk[] = [];
    const reply = await handle.read(receipt, { onEvent: (chunk) => chunks.push(chunk as ChatChunk) });

    // The tool went over the bridge, with the bearer and the declaration's own
    // bounds -- the whole of requirement (4), through a real render.
    expect(calls).toHaveLength(1);
    expect(calls[0]?.authorization).toBe("Bearer sekrit");
    expect(calls[0]?.body).toEqual({
      tool: "list_alerts",
      args: { severity: "high" },
      bounds: { max_rows: 50, timeout_ms: 15_000 },
    });

    // The durable record, projected: the console sees the tool run and then the
    // answer, in that order.
    const read = chatEventReader();
    const frames = chunks.flatMap((chunk) => read(chunk));
    expect(frames).toContainEqual({ type: "tool_processing" });
    const prose = frames
      .filter((frame): frame is { type: "text"; content: string } => "type" in frame && frame.type === "text")
      .map((frame) => frame.content)
      .join("");
    expect(prose).toContain("web-01");
    expect(frames.some((frame) => "error" in frame)).toBe(false);
    expect(reply.text).toContain("web-01");
  });

  // Identity is recorded at creation. A later turn carries no initialData at
  // all, and the agent must still render with the same analyst and the same
  // tools -- which is what makes "never read identity post-admission" safe
  // rather than merely stated.
  it("keeps the recorded identity across turns without being told again", async () => {
    const faux = fauxProvider({ provider: "faux", models: [{ id: "test" }] });
    faux.setResponses([fauxAssistantMessage("First."), fauxAssistantMessage("Second.")]);
    const { fetchStub } = toolEndpoint();
    vi.stubGlobal("fetch", fetchStub);

    const flue = await start({ agents: [Chat], providers: [faux.provider] });
    stop = () => flue.stop();

    const handle = init(Chat, { id: "conv-two-turns" });
    await handle.read(await handle.dispatch({ message: "First question", initialData: IDENTITY }));

    const second = await handle.dispatch({ message: "Second question" });
    const reply = await handle.read(second);

    expect(reply.text).toContain("Second");
    // The transcript is the durable record, so the second turn saw the first.
    expect(faux.state.callCount).toBe(2);
  });

  // An instance cannot exist without an identity: the schema is validated before
  // the creating send is admitted, so a malformed dispatch fails at the door
  // rather than rendering an agent with no analyst.
  it("refuses a turn whose identity does not validate", async () => {
    const faux = fauxProvider({ provider: "faux", models: [{ id: "test" }] });
    faux.setResponses([fauxAssistantMessage("never reached")]);

    const flue = await start({ agents: [Chat], providers: [faux.provider] });
    stop = () => flue.stop();

    const handle = init(Chat, { id: "conv-bad-identity" });

    await expect(
      handle.dispatch({ message: "Any alerts?", initialData: { scopes: [], model: "faux/test" } }),
    ).rejects.toThrow();
  });
});

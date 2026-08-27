import { afterEach, describe, expect, it, vi } from "vitest";
import { admitTurn, type ChatRoutes, streamTurn } from "../src/chat/routes.ts";

// The console's half of the contract: what a turn's admission answers, and what
// reading it back looks like on the wire.

function stubAgent(responder: (request: Request) => Response | Promise<Response>) {
  const seen: Request[] = [];
  const routes: ChatRoutes = {
    agent: {
      fetch: async (request: Request) => {
        seen.push(request);
        return responder(request);
      },
    },
    streamPath: (id) => `/chat/${encodeURIComponent(id)}/events`,
  };
  return { routes, seen };
}

// Flue's durable read as it actually arrives: payload chunks batched into an
// `event: data` frame carrying an array, coordination on `event: control`, and
// `: heartbeat` comment lines between them. A fixture that emits bare objects
// tests a protocol nobody speaks.
type Frame = { data: unknown[] } | { control: unknown } | "heartbeat";

function flueFrames(...frames: Frame[]): string[] {
  return frames.map((frame) => {
    if (frame === "heartbeat") return ": heartbeat\n\n";
    if ("control" in frame) return `event: control\ndata:${JSON.stringify(frame.control)}\n\n`;
    return `event: data\ndata:${JSON.stringify(frame.data)}\n\n`;
  });
}

function sseBody(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

async function framesOf(response: Response): Promise<unknown[]> {
  const text = await response.text();
  return text
    .split("\n\n")
    .filter((frame) => frame.startsWith("data: "))
    .map((frame) => JSON.parse(frame.slice("data: ".length)));
}

describe("admitting a chat turn", () => {
  it("answers 202 with the stream to read, and Flue's own handles intact", async () => {
    const { routes, seen } = stubAgent(() =>
      Response.json({ submissionId: "sub-1", offset: "42", uid: "inc-1" }, { status: 202 }),
    );

    const response = await admitTurn(
      routes,
      new Request("https://edge.vigil.example/chat/conv%201?verbose=1", {
        method: "POST",
        body: JSON.stringify({ message: { kind: "user", body: "any alerts?" }, initialData: { userId: "u-1" } }),
      }),
      "conv 1",
    );

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({
      submissionId: "sub-1",
      offset: "42",
      uid: "inc-1",
      streamUrl: "https://edge.vigil.example/chat/conv%201/events",
    });
    // The resume offset is on the response too, so a console that streams
    // rather than parses does not have to read the body to know where to start.
    expect(response.headers.get("stream-next-offset")).toBe("42");
    expect(response.headers.get("location")).toBe("https://edge.vigil.example/chat/conv%201/events");

    // The delivery reaches the agent verbatim -- identity travels in the body as
    // initialData, which is the whole of requirement (3).
    expect(await seen[0]?.text()).toBe(
      JSON.stringify({ message: { kind: "user", body: "any alerts?" }, initialData: { userId: "u-1" } }),
    );
    expect(seen[0]?.method).toBe("POST");
  });

  it("passes a refusal through rather than dressing it as an accepted turn", async () => {
    const { routes } = stubAgent(() => Response.json({ error: "no such conversation" }, { status: 404 }));

    const response = await admitTurn(
      routes,
      new Request("https://edge.vigil.example/chat/c1", { method: "POST", body: "{}" }),
      "c1",
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "no such conversation" });
  });
});

describe("reading a chat turn back", () => {
  it("reads the durable updates view live, from the caller's offset", async () => {
    const { routes, seen } = stubAgent(() => new Response(sseBody(flueFrames()), { status: 200 }));

    await streamTurn(routes, new Request("https://edge.vigil.example/chat/c1/events?offset=42"), "c1");

    const url = new URL(seen[0]?.url ?? "");
    expect(url.pathname).toBe("/c1");
    expect(url.searchParams.get("view")).toBe("updates");
    expect(url.searchParams.get("live")).toBe("sse");
    expect(url.searchParams.get("offset")).toBe("42");
  });

  // A console that has just opened has seen nothing, and -1 is Flue's word for
  // "from the beginning". Defaulting to 0 would skip the first chunk.
  it("replays from the beginning when the caller names no offset", async () => {
    const { routes, seen } = stubAgent(() => new Response(sseBody(flueFrames()), { status: 200 }));

    await streamTurn(routes, new Request("https://edge.vigil.example/chat/c1/events"), "c1");

    expect(new URL(seen[0]?.url ?? "").searchParams.get("offset")).toBe("-1");
  });

  it("projects durable chunks into the console's frames, unbuffered", async () => {
    const { routes } = stubAgent(
      () =>
        new Response(
          sseBody(
            flueFrames(
              // Batched, as Flue batches them: one frame can carry several chunks.
              { data: [{ type: "message-delta", kind: "text", delta: "Two alerts" }] },
              "heartbeat",
              {
                data: [
                  { type: "tool-input", toolCallId: "t1", toolName: "list_alerts" },
                  { type: "message-delta", kind: "reasoning", delta: "ignored" },
                ],
              },
              // Coordination is the reader's business, not the console's.
              { control: { streamNextOffset: "0000_0007", upToDate: true } },
              { data: [{ type: "submission-settled", outcome: "failed", error: "the model refused" }] },
            ),
          ),
          { status: 200 },
        ),
    );

    const response = await streamTurn(routes, new Request("https://edge.vigil.example/chat/c1/events"), "c1");

    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    expect(await framesOf(response)).toEqual([
      { type: "text", content: "Two alerts" },
      { type: "tool_processing" },
      { error: "the model refused" },
    ]);
  });

  it("passes an upstream failure through instead of an empty stream", async () => {
    const { routes } = stubAgent(() => Response.json({ error: "gone" }, { status: 410 }));

    const response = await streamTurn(routes, new Request("https://edge.vigil.example/chat/c1/events"), "c1");

    expect(response.status).toBe(410);
  });
});

describe("the internal caller guard", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  async function fetchApp(path: string, headers: Record<string, string> = {}): Promise<Response> {
    const { default: app } = await import("../src/app.ts");
    return app.fetch(new Request(`https://edge.vigil.example${path}`, { headers }));
  }

  it("refuses a conversation request with no bearer", async () => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "sekrit");
    const response = await fetchApp("/chat/c1/events");
    expect(response.status).toBe(401);
  });

  it("refuses a wrong bearer", async () => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "sekrit");
    const response = await fetchApp("/chat/c1/events", { authorization: "Bearer wrong" });
    expect(response.status).toBe(401);
  });

  // The failure that matters: an unconfigured secret must close the door, not
  // open it. A service that loses its token on deploy and keeps serving is worse
  // than one that stops.
  it("refuses everything when no token is configured", async () => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "");
    vi.stubEnv("VIGIL_TOOLS_TOKEN", "");
    const response = await fetchApp("/chat/c1/events", { authorization: "Bearer anything" });
    expect(response.status).toBe(403);
  });

  it("answers liveness without the secret, so a probe can report the service is up", async () => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "");
    const response = await fetchApp("/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok", service: "vigil-edge" });
  });

  // Flue's own surface carries the same conversations, so it sits behind the same
  // lock. An unauthenticated /agents/* is the whole guard defeated.
  it("guards Flue's native agent surface too", async () => {
    vi.stubEnv("AGENT_INTERNAL_TOKEN", "sekrit");
    const response = await fetchApp("/agents/chat/c1");
    expect(response.status).toBe(401);
  });
});

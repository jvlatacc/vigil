import type { Fetchable } from "@flue/runtime/routing";
import { chatFrames } from "./stream.ts";

// The console-facing half of the chat contract, expressed over the Flue-native
// mount rather than beside it: one POST that admits a turn and one GET that
// reads it back. The agent router is passed in rather than imported so both
// routes are testable against a stub -- and so nothing here can quietly reach
// for a second source of truth about the conversation.

export interface ChatRoutes {
  readonly agent: Fetchable;
  // Where the console should come back to read the turn. Mount-relative, so the
  // caller owns the URL surface.
  readonly streamPath: (conversationId: string) => string;
}

// A turn, admitted. The body is Flue's DeliveredMessage shape verbatim
// (`{ message, initialData? }`), because inventing a second envelope for the
// same delivery is how two shapes for one thing start.
//
// The 202 is rewritten in exactly one field: Flue answers with its own read URL,
// and the console reads the projected stream. Everything else -- offset,
// submissionId, uid -- is passed through untouched, since those are the caller's
// handles on this specific delivery.
export async function admitTurn(routes: ChatRoutes, request: Request, conversationId: string): Promise<Response> {
  const upstream = await routes.agent.fetch(
    new Request(internalUrl(request, `/${encodeURIComponent(conversationId)}`), {
      method: "POST",
      headers: request.headers,
      body: await request.text(),
    }),
  );

  if (upstream.status !== 202) return upstream;

  const receipt = (await upstream.json()) as Record<string, unknown>;
  const streamUrl = new URL(request.url);
  streamUrl.search = "";
  streamUrl.pathname = routes.streamPath(conversationId);

  return Response.json(
    { ...receipt, streamUrl: streamUrl.toString() },
    {
      status: 202,
      headers: {
        location: streamUrl.toString(),
        // The offset the console must resume from, mirrored as Flue mirrors it.
        ...(typeof receipt["offset"] === "string" ? { "stream-next-offset": receipt["offset"] } : {}),
      },
    },
  );
}

// The turn, read back. `offset` is the caller's resume point: the offset the 202
// returned, or a later one it has already seen. -1 replays the conversation from
// the beginning, which is the honest default for a console that has just opened.
export async function streamTurn(routes: ChatRoutes, request: Request, conversationId: string): Promise<Response> {
  const offset = new URL(request.url).searchParams.get("offset") ?? "-1";
  const read = new URL(internalUrl(request, `/${encodeURIComponent(conversationId)}`));
  read.searchParams.set("view", "updates");
  read.searchParams.set("offset", offset);
  read.searchParams.set("live", "sse");

  const upstream = await routes.agent.fetch(new Request(read, { headers: request.headers }));
  if (!upstream.ok || upstream.body === null) return upstream;

  return new Response(chatFrames(upstream.body), {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      // Nginx buffers text/event-stream by default, which turns a live stream
      // into one delivery at the end.
      "x-accel-buffering": "no",
    },
  });
}

// The agent router serves paths relative to its mount, so an internal request is
// addressed by conversation id alone. The origin is carried over from the inbound
// request only to keep the URL well-formed.
function internalUrl(request: Request, path: string): string {
  return new URL(path, new URL(request.url).origin).toString();
}

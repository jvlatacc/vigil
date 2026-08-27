import { createAgentRouter } from "@flue/runtime/routing";
import { Hono } from "hono";
import { Chat } from "./agents/chat.ts";
import { admitTurn, type ChatRoutes, streamTurn } from "./chat/routes.ts";
import { internalToken } from "./config.ts";

// The route map. Nothing is mounted implicitly: if a URL exists in this service,
// it is because this file says so.

const chat = createAgentRouter(Chat);

const routes: ChatRoutes = {
  agent: chat,
  streamPath: (conversationId) => `/chat/${encodeURIComponent(conversationId)}/events`,
};

const app = new Hono();

// Liveness only, and deliberately before the guard: a probe that needs the
// service's own secret cannot report that the service is up.
app.get("/health", (c) => c.json({ status: "ok", service: "vigil-edge" }));

// Every conversation surface, behind the shared secret of ADR 0014. The caller
// is core/, not a browser and not a session: this authenticates the *service*.
// Who the *user* is arrives in initialData at dispatch and is recorded once --
// which is why nothing downstream of here reads an identity off a request.
//
// Reachability is the NetworkPolicy's job, as ADR 0014 settled; this is the
// second lock, not the only one.
app.use("/chat/*", requireInternalCaller);
app.use("/agents/*", requireInternalCaller);

// The console's contract: a turn in, the durable stream back out.
app.post("/chat/:id", (c) => admitTurn(routes, c.req.raw, c.req.param("id")));
app.get("/chat/:id/events", (c) => streamTurn(routes, c.req.raw, c.req.param("id")));

// Flue's own surface for the same conversations -- snapshots, aborts,
// attachments, and the raw chunk stream. Same agent, same storage, no projection:
// the SDK and any future first-party client talk to this one.
app.route("/agents/chat", chat);

export default app;

async function requireInternalCaller(
  c: { req: { header: (name: string) => string | undefined }; json: (body: unknown, status: 401 | 403) => Response },
  next: () => Promise<void>,
): Promise<Response | void> {
  const expected = internalToken();
  // An unconfigured token refuses everything rather than admitting everything.
  // The alternative is a service that silently loses its lock on deploy.
  if (expected === "") return c.json({ error: "internal token is not configured" }, 403);

  const presented = c.req.header("authorization") ?? "";
  const prefix = "Bearer ";
  if (!presented.startsWith(prefix) || !constantTimeEqual(presented.slice(prefix.length), expected)) {
    return c.json({ error: "unauthorized" }, 401);
  }
  await next();
}

// Every comparison walks the same number of bytes regardless of where the two
// differ: an early return on the first mismatch is an oracle for the token's
// matching prefix. A length difference is folded into the same accumulator
// rather than short-circuiting on it.
function constantTimeEqual(presented: string, expected: string): boolean {
  const encoder = new TextEncoder();
  const a = encoder.encode(presented);
  const b = encoder.encode(expected);
  let mismatch = a.length ^ b.length;
  const width = Math.max(a.length, b.length);
  for (let i = 0; i < width; i += 1) mismatch |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return mismatch === 0;
}

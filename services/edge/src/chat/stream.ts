import { type ChatChunk, chatEventReader, settles, sse } from "./events.ts";

// Flue's durable read and the console's stream are both SSE, and that is where
// the resemblance stops: Flue pushes arrays of ledger chunks and never ends,
// while the console expects one flat event per frame and a stream that closes
// when the turn does. This is the seam between them.
//
// Reading it back rather than forwarding it is the point of the exercise: the
// durable stream is the record, so the console's stream becomes a projection of
// a record that survives the connection, and a reconnect replays from an offset
// instead of losing the turn.

const FRAME_SEPARATOR = /\r?\n\r?\n/;

export function chatFrames(upstream: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const read = chatEventReader();
  const reader = upstream.getReader();
  let pending = "";

  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          // Upstream ended without settling the submission -- the Worker was
          // evicted, or the read was cut. Close rather than hang: the caller
          // resumes from its last offset.
          controller.close();
          return;
        }

        pending += decoder.decode(value, { stream: true });
        const blocks = pending.split(FRAME_SEPARATOR);
        // The last element is the incomplete tail, unless the chunk ended on a
        // separator, in which case it is empty and carries nothing over.
        pending = blocks.pop() ?? "";

        let closing = false;
        let emitted = false;
        for (const block of blocks) {
          for (const chunk of chunksOf(block)) {
            for (const event of read(chunk)) {
              controller.enqueue(encoder.encode(sse(event)));
              emitted = true;
            }
            if (settles(chunk)) closing = true;
          }
        }

        if (closing) {
          await reader.cancel();
          controller.close();
          return;
        }
        // Nothing to hand on yet (a heartbeat, a control event, a chunk this
        // vocabulary drops): keep reading rather than returning an empty pull.
        if (emitted) return;
      }
    },
    async cancel(reason) {
      // The console navigated away. The turn continues in the Durable Object,
      // which is the entire reason this stream is durable.
      await reader.cancel(reason);
    },
  });
}

// One SSE block -> the chunks it carries. Flue names its payload events `data`
// and its coordination events `control`; comment lines are heartbeats. Anything
// unparseable is a protocol break, and a swallowed parse error here would look
// exactly like a quiet model, so it is thrown.
function chunksOf(block: string): ChatChunk[] {
  let event = "message";
  const data: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data.push(line.slice("data:".length).trimStart());
  }

  if (event !== "data" || data.length === 0) return [];

  const payload: unknown = JSON.parse(data.join("\n"));
  if (!Array.isArray(payload)) {
    throw new TypeError(`durable stream data event was not an array: ${typeof payload}`);
  }
  return payload as ChatChunk[];
}

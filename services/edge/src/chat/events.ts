// The console's vocabulary, and the translation into it from Flue's durable
// conversation stream. Carried over verbatim from
// services/agent/workflows/chat/sse.ts: the console parses these five shapes and
// skips anything else, so adding one is safe and dropping one degrades to
// silence rather than to a broken reader.

export type ChatEvent =
  | { type: "text"; content: string }
  | { type: "tool_processing" }
  | { type: "context_windowed"; windowed_messages: number; remaining_messages: number }
  | { type: "approval_required"; checkpoint_id: string; tool: string | null; args: string | null }
  | { error: string };

// The subset of Flue's ConversationStreamChunk this translation reads, declared
// structurally. @flue/sdk owns the full union; a chat frame needs six of its
// shapes, and naming only those keeps the dependency at the protocol rather than
// at a package.
export type ChatChunk =
  | { type: "conversation-reset"; snapshot: { messages: readonly { id: string }[] } }
  | { type: "message-appended"; message: { id: string } }
  | { type: "message-started"; messageId: string }
  | { type: "message-delta"; kind: "text" | "reasoning"; delta: string }
  | { type: "tool-input"; toolCallId: string; toolName: string }
  | { type: "submission-settled"; outcome: "completed" | "failed" | "aborted"; error?: unknown }
  | { type: string };

export function sse(event: ChatEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

// A turn is over when its submission settles: the legacy contract ends the
// response there, and Flue's live read never ends on its own.
export function settles(chunk: ChatChunk): boolean {
  return chunk.type === "submission-settled";
}

export interface ChatEventReader {
  (chunk: ChatChunk): ChatEvent[];
}

// Stateful by necessity, and only for one thing: context_windowed reports how
// many messages a compaction folded away, and Flue announces a compaction as a
// reset carrying the surviving snapshot rather than as a count. Holding the ids
// seen so far is what turns that reset back into the pair of numbers the console
// renders. Everything else here is a pure per-chunk translation.
export function chatEventReader(): ChatEventReader {
  const seen = new Set<string>();

  return (chunk: ChatChunk): ChatEvent[] => {
    switch (chunk.type) {
      case "conversation-reset": {
        const reset = chunk as Extract<ChatChunk, { type: "conversation-reset" }>;
        const before = seen.size;
        seen.clear();
        for (const message of reset.snapshot.messages) seen.add(message.id);
        // A reset also opens a fresh read (offset=-1), which is not a compaction
        // and must not be reported as one.
        const folded = before - seen.size;
        return folded > 0
          ? [{ type: "context_windowed", windowed_messages: folded, remaining_messages: seen.size }]
          : [];
      }
      case "message-appended":
        seen.add((chunk as Extract<ChatChunk, { type: "message-appended" }>).message.id);
        return [];
      case "message-started":
        // A second start for an open id is a continuation, not a new message.
        seen.add((chunk as Extract<ChatChunk, { type: "message-started" }>).messageId);
        return [];
      case "message-delta": {
        const delta = chunk as Extract<ChatChunk, { type: "message-delta" }>;
        // Reasoning is dropped, as it is on the legacy wire: one console schema
        // carries no thinking block, and a block silently reshaped is worse than
        // one left out.
        return delta.kind === "text" ? [{ type: "text", content: delta.delta }] : [];
      }
      case "tool-input":
        // tool_result and usage have no shape over there either: the ledger
        // carries them and the reader does not.
        return [{ type: "tool_processing" }];
      case "submission-settled": {
        const settled = chunk as Extract<ChatChunk, { type: "submission-settled" }>;
        // An aborted turn is not a turn that failed, and the legacy stream said
        // nothing about one: the response simply ends.
        return settled.outcome === "failed" ? [{ error: messageOf(settled.error) }] : [];
      }
      default:
        return [];
    }
  };
}

// approval_required has no counterpart yet: checkpoints are the hunt workflow's
// mechanism and chat never emitted one. It stays in the type because the console
// parses it and the vocabulary is the contract, not this translation's coverage.

export function messageOf(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null) {
    const message = (error as Record<string, unknown>)["message"];
    if (typeof message === "string") return message;
    const detail = (error as Record<string, unknown>)["details"];
    if (typeof detail === "string") return detail;
  }
  return "the agent failed without saying why";
}

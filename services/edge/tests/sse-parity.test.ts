import { describe, expect, it } from "vitest";
// The legacy emitter itself, not a copy of its output. A parity test that
// restates the expected frames in its own words passes just as happily when
// both sides drift together; this one fails when the two disagree, which is
// the only thing worth asserting while the console reads both tiers.
import { chatEvents } from "../../agent/workflows/chat/sse.ts";
import { type ChatChunk, chatEventReader } from "../src/chat/events.ts";

type LegacyEvent = Parameters<typeof chatEvents>[0];

// Each case is the same moment of a turn, said in both vocabularies: what the
// old harness reported, and what Flue's durable stream carries for it. The
// assertion is that the console cannot tell which tier produced the frame.
const PARITY: readonly { moment: string; legacy: LegacyEvent; durable: ChatChunk[] }[] = [
  {
    moment: "the model streams prose",
    legacy: { type: "text_delta", text: "Two alerts, both low severity." },
    durable: [{ type: "message-delta", kind: "text", delta: "Two alerts, both low severity." }],
  },
  {
    moment: "the model calls a tool",
    legacy: { type: "tool_call", call: { name: "list_alerts", args: {} } } as unknown as LegacyEvent,
    durable: [{ type: "tool-input", toolCallId: "call-1", toolName: "list_alerts" }],
  },
  {
    moment: "the turn fails",
    legacy: { type: "failed", outcome: { reason: "the model refused" } } as unknown as LegacyEvent,
    durable: [{ type: "submission-settled", outcome: "failed", error: "the model refused" }],
  },
  {
    moment: "the turn completes",
    legacy: { type: "done", outcome: { reason: "the role answered" } } as unknown as LegacyEvent,
    durable: [{ type: "submission-settled", outcome: "completed" }],
  },
  {
    moment: "a tool returns",
    legacy: { type: "tool_result", call: { name: "list_alerts" }, attempt: {} } as unknown as LegacyEvent,
    durable: [{ type: "message-appended", message: { id: "m-tool-result" } }],
  },
];

describe("chat SSE shape parity with services/agent", () => {
  for (const { moment, legacy, durable } of PARITY) {
    it(`agrees when ${moment}`, () => {
      const read = chatEventReader();
      const projected = durable.flatMap((chunk) => read(chunk));
      expect(projected).toEqual(chatEvents(legacy));
    });
  }

  // Compaction is the one moment the two tiers describe differently: the old
  // harness counted the fold as it happened, and Flue announces the survivors.
  // Parity is therefore asserted on the frame, not on the input.
  it("agrees when context is compacted, from a reset rather than a count", () => {
    const read = chatEventReader();
    for (const id of ["m1", "m2", "m3", "m4"]) read({ type: "message-appended", message: { id } });

    const projected = read({
      type: "conversation-reset",
      snapshot: { messages: [{ id: "m3" }, { id: "m4" }] },
    });

    expect(projected).toEqual(chatEvents({ type: "folded", folded: 2, remaining: 2 }));
  });

  // The first read of a conversation is also a reset, and it must not be
  // reported as a compaction that folded the whole history away.
  it("says nothing on the reset that opens a fresh read", () => {
    const read = chatEventReader();
    const projected = read({
      type: "conversation-reset",
      snapshot: { messages: [{ id: "m1" }, { id: "m2" }] },
    });
    expect(projected).toEqual([]);
  });

  // Reasoning has no shape on the console's wire. The legacy tier never emitted
  // one, so neither does this.
  it("drops reasoning deltas, as the legacy stream did", () => {
    const read = chatEventReader();
    expect(read({ type: "message-delta", kind: "reasoning", delta: "hmm" })).toEqual([]);
  });

  // An aborted turn is not a failed turn: the legacy response simply ended, and
  // an `error` frame here would render as a failure the analyst never caused.
  it("reports nothing for an aborted turn", () => {
    const read = chatEventReader();
    expect(read({ type: "submission-settled", outcome: "aborted" })).toEqual([]);
  });
});

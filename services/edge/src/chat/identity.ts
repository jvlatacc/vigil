import * as v from "valibot";

// What a chat conversation *is*, as opposed to what a turn says. Recorded once,
// at the instance's first contact, and constant for its whole life.
//
// This is the whole of requirement (3): the caller's identity and the scope it
// was granted arrive here, at dispatch, resolved by the side that authenticated
// the human. Flue does not reconstruct caller headers or cookies inside a
// Durable Object, so an agent that tried to read identity after admission would
// be reading nothing at all -- and a turn three days later would read the same
// nothing. The bearer token on the route authenticates the *service*; this
// authenticates the *user*, and only the dispatcher can say it.
export const ChatIdentity = v.object({
  userId: v.pipe(v.string(), v.minLength(1)),
  // The authorization scope this conversation may act within. The dispatcher
  // resolved the tool list below against it; carried anyway because an
  // instruction the model can read is what keeps it inside the scope it has.
  scopes: v.array(v.pipe(v.string(), v.minLength(1))),
  tenantId: v.nullish(v.string(), null),
  // Resolved by the caller: this tier is handed a model, never an agent id.
  model: v.pipe(v.string(), v.minLength(1)),
  systemPrompt: v.optional(v.string(), ""),
  tools: v.optional(v.array(v.lazy(() => ToolDeclaration)), []),
});

// A tool the far side owns. This tier carries only what the model needs to
// choose it -- what it is called, what it does, what it takes -- plus the bounds
// the invocation must be held to. The implementation stays in core/.
export const ToolDeclaration = v.object({
  name: v.pipe(v.string(), v.minLength(1)),
  description: v.pipe(v.string(), v.minLength(1)),
  // JSON Schema, as the arch config already declares it.
  parameters: v.record(v.string(), v.unknown()),
  maxRows: v.optional(v.pipe(v.number(), v.integer(), v.minValue(1)), 200),
  timeoutMs: v.optional(v.pipe(v.number(), v.integer(), v.minValue(1)), 30_000),
});

export type ChatIdentityData = v.InferOutput<typeof ChatIdentity>;
export type ToolDeclarationData = v.InferOutput<typeof ToolDeclaration>;

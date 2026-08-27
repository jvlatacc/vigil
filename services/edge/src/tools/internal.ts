import type { JsonValue, ToolDefinition } from "@flue/runtime";
import type { InternalToolsBridge } from "../config.ts";
import type { ToolDeclarationData } from "../chat/identity.ts";
import { type ToolArgsSchema, toolInput } from "./schema.ts";

// The bridge to core/agents/tools_router.py, and the whole of requirement (4).
// The tools stay in Python -- they read Postgres, they call MCP servers, they
// know the tenancy rules -- and the agent reaches them over one authenticated
// POST, exactly as services/agent/core/remote.ts does today. The wire shape is
// therefore copied rather than improved: same bearer, same snake_case bounds,
// same discrimination on the way back. Two callers of one endpoint that disagree
// about its contract is the failure this file exists to avoid.

// The vocabulary, unchanged: invalid_args and refused are the model's problem to
// correct, timeout and unavailable are the platform's, backend_error is a defect
// worth an alert. Collapsing any pair of them loses the distinction the hunt
// reasons over -- so a kind that does not arrive from the far side never gets
// invented here.
const FAILURE_KINDS = new Set(["invalid_args", "refused", "timeout", "unavailable", "backend_error"]);

// Typed as JSON throughout, because that is what it is: the far side's answer,
// serialized for the model verbatim. The details beyond `kind` differ per
// failure and belong to the tool that raised them, so they are carried rather
// than enumerated.
export type ToolFailure = { readonly kind: string; readonly [detail: string]: JsonValue };

export type ToolOutcome =
  | {
      readonly ok: true;
      readonly rows: JsonValue[];
      readonly rowCount: number;
      readonly capped: boolean;
      readonly sourceSystem: string;
    }
  | { readonly ok: false; readonly failure: ToolFailure };

function unavailable(detail: string): ToolOutcome {
  return { ok: false, failure: { kind: "unavailable", detail } };
}

// The far side owns the discrimination, so a body that is neither rows nor a
// known failure means this hop failed rather than the tool -- and that is
// unavailable, not backend_error. Guessing the other way would report a Vigil
// defect every time the network hiccupped.
export function outcomeOf(body: unknown): ToolOutcome {
  if (typeof body !== "object" || body === null) {
    return unavailable("the endpoint did not answer with a result");
  }
  const value = body as Record<string, unknown>;
  if (value["ok"] === true && Array.isArray(value["rows"])) return value as unknown as ToolOutcome;

  const failure = value["failure"];
  if (typeof failure === "object" && failure !== null) {
    const kind = String((failure as Record<string, unknown>)["kind"]);
    if (FAILURE_KINDS.has(kind)) return { ok: false, failure: failure as ToolFailure };
  }
  return unavailable("the endpoint answered with neither rows nor a known failure");
}

export interface InvokeOptions {
  readonly bridge: InternalToolsBridge;
  readonly tool: string;
  readonly args: Record<string, unknown>;
  readonly maxRows: number;
  readonly timeoutMs: number;
  readonly signal?: AbortSignal;
}

// One tool call, as a function of its inputs: no hooks, no env reads, nothing
// that needs an agent around it. That is what makes the failure vocabulary
// testable without a model in the loop.
export async function invokeInternalTool(options: InvokeOptions): Promise<ToolOutcome> {
  const { bridge, tool, args, maxRows, timeoutMs, signal } = options;
  const call = bridge.fetch ?? globalThis.fetch;

  // The tool's own ceiling and the turn's abort both end this call, so whichever
  // fires first does: a cancelled turn must not wait out a 30s tool.
  const timeout = AbortSignal.timeout(timeoutMs);
  const halt = new AbortController();
  const relay = (source: AbortSignal) => () => halt.abort(source.reason);
  const onTimeout = relay(timeout);
  const onAbort = signal === undefined ? undefined : relay(signal);
  if (signal?.aborted === true) halt.abort(signal.reason);
  timeout.addEventListener("abort", onTimeout, { once: true });
  signal?.addEventListener("abort", onAbort as () => void, { once: true });

  try {
    let response: Response;
    try {
      response = await call(bridge.url, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${bridge.token}` },
        // snake_case because the far side's Bounds model declares it that way,
        // and a bound the endpoint drops is not a bound.
        body: JSON.stringify({ tool, args, bounds: { max_rows: maxRows, timeout_ms: timeoutMs } }),
        signal: halt.signal,
      });
    } catch (error) {
      const timedOut = error instanceof Error && error.name === "TimeoutError";
      if (timedOut) return { ok: false, failure: { kind: "timeout", timeoutMs } };
      // An aborted turn is not a tool that failed, so it is not recorded as one.
      if (signal?.aborted === true) return unavailable("the turn was aborted");
      return unavailable(error instanceof Error ? error.message : String(error));
    }

    if (!response.ok) return unavailable(`the endpoint answered ${response.status}`);
    try {
      return outcomeOf(await response.json());
    } catch (error) {
      return unavailable(error instanceof Error ? error.message : String(error));
    }
  } finally {
    // Unwired here rather than left attached: one long conversation would
    // otherwise pile a listener per tool call onto the turn's signal.
    timeout.removeEventListener("abort", onTimeout);
    if (onAbort !== undefined) signal?.removeEventListener("abort", onAbort);
  }
}

// A declared tool, as something the model can call. The failure is returned as
// the tool's output rather than thrown: a thrown error reaches the model as prose
// and drops the kind, and the kind is the part the model is supposed to act on
// (retry invalid_args, stop calling a refused name, note an unavailable source).
export function internalTool(
  declaration: ToolDeclarationData,
  bridge: () => InternalToolsBridge,
): ToolDefinition {
  const definition: ToolDefinition<ToolArgsSchema, undefined, undefined, undefined> = {
    name: declaration.name,
    description: declaration.description,
    input: toolInput(declaration.parameters),
    output: undefined,
    async run({ data, signal }) {
      const outcome = await invokeInternalTool({
        bridge: bridge(),
        tool: declaration.name,
        args: data,
        maxRows: declaration.maxRows,
        timeoutMs: declaration.timeoutMs,
        signal,
      });
      return { output: outcome };
    },
  };
  return definition as ToolDefinition;
}

// Everything this Worker needs from its environment, read in one place so a
// missing binding is one error message rather than an undefined threaded three
// files deep. process.env rather than the cloudflare:workers import: with
// nodejs_compat it carries vars and secrets on workerd, and the same code reads
// on Node under vitest, which is what makes the round-trip test possible.

export interface InternalToolsBridge {
  readonly url: string;
  readonly token: string;
  // Injected by tests. Production takes the platform's fetch.
  readonly fetch?: typeof globalThis.fetch;
}

// The bridge the agent's tools call: core/agents' /internal/tools/invoke, over
// the bearer contract of ADR 0014. Read lazily, per tool call, because an agent
// renders inside a Durable Object that outlives any one request.
export function internalToolsBridge(): InternalToolsBridge {
  const url = process.env["INTERNAL_TOOLS_URL"] ?? "";
  const token = internalToken();
  if (url === "") throw new Error("INTERNAL_TOOLS_URL is not configured");
  if (token === "") throw new Error("AGENT_INTERNAL_TOKEN is not configured");
  return { url, token };
}

// The same secret in both directions: the token core/ presents to this Worker is
// the token this Worker presents back to /internal/tools. VIGIL_TOOLS_TOKEN is
// the older name services/agent still accepts, kept so one deployment can run
// both tiers during the migration.
export function internalToken(): string {
  return process.env["AGENT_INTERNAL_TOKEN"] ?? process.env["VIGIL_TOOLS_TOKEN"] ?? "";
}

# MCP tool-call accountability — stdio vs. HTTP-capable connectors

The question this contract answers: **who ran tool X on system Y at time Z**
— for every MCP path Vigil has: the agent layer calling a vendor server, an
external MCP client calling Vigil's `/mcp`, in-process tools, and VStrike.
The answer differs by connector family, and the difference is the protocol's,
not a preference.

## Why the two families differ

**stdio servers** (every connector in `mcp-config.json` today) run as one
**persistent child process per server** (`PersistentServerSession`,
`core/integrations/mcp/client.py`), shared by every user and every agent run.
There is no per-request identity field on the stdio transport, and identity
injected at spawn time would attribute the whole long-lived session to
whoever happened to spawn it first — wrong for the second user's call. The
MCP spec itself declines to standardize stdio authorization.

**HTTP-capable servers** (Streamable HTTP) speak OAuth 2.1: Vigil can obtain
a token **per user, per server**, and the server derives the principal from
the token it validated. The spec makes tokens audience-bound (RFC 8707) and
forbids passthrough — a token minted for server A must never be sent to
server B.

So the contract splits exactly along the protocol line:

| Surface | Who the far end sees | What Vigil records |
|---|---|---|
| Agent → stdio MCP server | the server's own static credential | `tool_call_audit` row (actor, server, tool, args digest, decision, outcome) + OTEL `trace_id` |
| Agent → HTTP-capable MCP server | a per-user, audience-bound bearer token | the same audit row |
| External client → `/mcp` | Vigil itself | audit row behind the bearer gate — sessions are bound to the `vgl_mcp_` credential's owner |
| In-process tools | — | audit row attributed from the bound caller |
| VStrike REST / MCP | the shared service account (no per-user delegation exists there today) | audit row naming the acting human via `current_caller()` |

## The stdio contract, stated plainly

For a stdio connector, **attribution is Vigil's own audit row** — actor ×
server × tool × arguments digest × decision × outcome, hash-chained in
`tool_call_audit` — correlated to the call's execution by `trace_id` (and
`run_id` for agent runs). That row is the record of record: it is written
for allow **and** deny at the enforcement points (the agent invoke path and
the `/mcp` gate), and again at execution funnels with the outcome. A failed
audit write fails the call — there is no unaudited success.

What the far-end system sees is the server's own credential (a static API
key in the connector config). Per-user identity downstream is **not
promised** for stdio, because there is no protocol channel to carry it; the
honest boundary of the guarantee is Vigil's ledger. When the MCP spec adds a
per-request identity field for stdio, this contract updates.

## The HTTP-capable contract

For Streamable HTTP connectors, Vigil behaves as a spec-conformant MCP OAuth
client (`core/integrations/mcp/identity.py`): Protected Resource Metadata
discovery (RFC 9728) → authorization-server metadata (RFC 8414) →
Authorization Code + PKCE as the user → RFC 8707 `resource` parameter
binding the token to that one server. Token passthrough is prohibited —
Vigil's own session or broker tokens are never forwarded to a connector.
The downstream server's logs name the same person Vigil's audit row does.

Status: the identity module and per-user token machinery are in place; the
HTTP dispatch path in `client.py` is the remaining integration (tracked with
the downstream-identity work, PR 04 of the plan). Until it lands, HTTP
connectors behave like stdio ones for attribution — which the audit row
covers either way.

## Why this is the right boundary

The agent layer can **drop** the `tool_principal` it was handed but cannot
**forge** one — it is minted server-side, purpose-scoped, and short-lived.
Enforcement and evidence therefore sit where the verified username, the tool
id, and the arguments coexist: `tools_router.invoke` for the agent path, the
`/mcp` bearer gate for external callers. Identity-blind dispatch is what the
plan removed; the audit row is what replaced it.

Operational halves of this contract live elsewhere: keeping and shipping the
rows → [Tool-call audit — retention and SIEM export](tool-call-audit.md);
how a person's identity gets verified in the first place →
[Identity broker setup](broker-setup.md).

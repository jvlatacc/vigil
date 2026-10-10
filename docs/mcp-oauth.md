# MCP OAuth — identity-provider tokens for MCP calls

Vigil speaks the MCP authorization profile: OAuth 2.1 with Protected Resource
Metadata (RFC 9728) discovery, RFC 8707 resource-bound tokens, PKCE, and
refresh-token rotation. There is no vendor SDK and no per-IdP code path: any
issuer that serves RFC 8414 or OIDC metadata works. Okta, Microsoft Entra ID,
Keycloak, and Auth0 are the ones documented here.

The profile runs in two directions:

| Direction | Who authenticates to whom | What it covers |
|-----------|---------------------------|----------------|
| **Outbound** | Vigil → remote MCP servers | URL-based servers reached natively over streamable-HTTP, each call carrying a token your identity provider issued for that server |
| **Inbound** | Callers → Vigil's own `/mcp` surface | IdP-issued JWTs accepted beside credentials minted from Settings |

Ground rules, enforced in code rather than convention:

- Access tokens live in memory only.
- Refresh tokens and client secrets live only in the encrypted secrets store.
- Nothing token-shaped is ever logged.
- Vigil's RBAC stays authoritative: a token proves *who*; what the caller may
  *do* reads from its Vigil roles alone.

## Outbound: connecting Vigil to a remote MCP server

### The auth block

A URL-based server entry in `mcp-config.json` declares a native transport and
an `auth` block:

```json
{
  "mcpServers": {
    "azure-sentinel-native": {
      "url": "https://sentinelmcp.microsoft.com/v1/mcp",
      "transport": "streamable-http",
      "auth": {
        "type": "oauth2",
        "grant": "client_credentials",
        "issuer_url": "https://login.microsoftonline.com/${AZURE_TENANT_ID}/v2.0",
        "client_id": "${AZURE_SENTINEL_MCP_CLIENT_ID}",
        "client_secret_key": "AZURE_SENTINEL_MCP_CLIENT_SECRET",
        "resource": "https://sentinelmcp.microsoft.com"
      }
    }
  }
}
```

An entry with `transport: "streamable-http"` never spawns a child process —
the `mcp-remote` bridge and its pin are not involved. Entries that keep the
bridge stay supported until each vendor server migrates; their version pins
are owned by the ratchet tests, not by hand.

The `auth` fields:

| Field | Meaning |
|-------|---------|
| `type` | `oauth2`. The only value supported. |
| `grant` | `client_credentials` (the default) or `authorization_code`. |
| `issuer_url` | Your issuer. Optional: without it, Vigil discovers the issuer from the server's own 401 challenge (below). |
| `client_id` | The client (app) id at your issuer. |
| `client_secret_key` | The **name** of a key in the encrypted secrets store holding the client secret — never the secret itself. Required for `client_credentials`. |
| `scopes` | Scopes to request. |
| `resource` | RFC 8707 resource indicator. Defaults to the server's own URL, which is the right answer for a single-purpose server. |
| `refresh_token_key` | Store key for the refresh token. Defaults to `MCP_OAUTH_REFRESH_<SERVER>` (upper-cased server name). |

Two kinds of value ride this block. Non-secret fields may use `${VAR}`
placeholders, resolved from the environment at load — the same mechanism a
command-style entry uses. Secret *values* never appear in config: a
`client_secret_key` or `refresh_token_key` names an entry in the encrypted
secrets store, read at acquire time. A secret that does not resolve leaves
the server dormant ("awaiting credentials") — never connected unsigned.

### Discovery: how Vigil finds your issuer

When `issuer_url` is omitted, discovery follows the server's own challenge:
the first call is answered `401` with
`WWW-Authenticate: Bearer resource_metadata=…`, Vigil fetches that RFC 9728
Protected Resource Metadata document, and reads its `authorization_servers` —
then the issuer's own RFC 8414 / OIDC metadata for the endpoints. The
`resource` parameter rides every authorization and token request, so the
tokens that come back are audience-bound to this MCP server and nothing
else. Configure `issuer_url` when the challenge points at an issuer your
tenant does not answer for, or to skip the round trips.

### Grant: `client_credentials` (machine-to-machine)

For servers that act as the integration itself — Sentinel, a SIEM, a threat
intel feed — with no human in the loop. Vigil exchanges the client secret for
a token, caches it in memory with its expiry, and re-acquires on expiry.

Setup, per issuer:

- **Microsoft Entra ID.** Create an app registration, expose an API scope (or
  use the server's well-known `api://…/.default`), create a client secret,
  and store it under the `client_secret_key` name. The issuer URL is
  `https://login.microsoftonline.com/<tenant-id>/v2.0`. The `resource` is the
  server's URL (Entra accepts it as the audience).
- **Okta.** Create an API Services (client-credentials) app in your
  authorization server. The issuer URL is
  `https://<your-org>/oauth2/<authorization-server-id>`. Grant the app the
  scope the MCP server requires.
- **Keycloak.** Create a confidential client with *Service accounts* enabled,
  assign the service-account role the server expects. The issuer URL is
  `https://<host>/realms/<realm>`.
- **Auth0.** Create a Machine-to-Machine application authorized against the
  API the MCP server fronts; the audience is the API's identifier. The issuer
  URL is `https://<tenant>.auth0.com/`.

In every case: the client id may ride config (`${VAR}` placeholder or plain),
the client secret goes into the encrypted secrets store under the
`client_secret_key` name (Settings → Integrations, or your secret-provisioning
path), then enable the server. Its entry in
`GET /api/mcp/servers/status` reports `connected` with a token expiry.

### Grant: `authorization_code` + PKCE (user-delegated)

For servers that act *for a person* — the token names a user at the IdP, and
the server enforces that user's rights. Vigil obtains the token with
authorization code + PKCE (S256) and keeps it alive with the refresh grant.

This grant needs exactly one interactive consent. The flow:

1. An integrations admin starts it: `POST /api/mcp/oauth/<server>/consent`.
   Vigil builds the authorization URL — PKCE pair minted, `state` bound,
   `resource` included — and reports `needs_consent` on the status surface.
2. The operator completes the consent at the IdP in a browser. Register this
   redirect URI on the IdP application first:
   `<vigil-base-url>/api/mcp/oauth/<server>/callback`.
3. The IdP redirects back with `code` and `state`; the UI posts them to
   `POST /api/mcp/oauth/<server>/callback`. Vigil exchanges the code (the
   PKCE verifier proves it was Vigil that started the flow), and stores the
   refresh token in the secrets store under the server's `refresh_token_key`.
   The connection reports `connected`.

From then on nothing is interactive: access tokens refresh before expiry.
Refresh is serialized per server, so two concurrent calls cannot race a
refresh. Rotation is honored — a refresh response that carries a new refresh
token replaces the old one atomically — and reuse of an already-rotated token
is treated as a security event: the connection drops to `needs_consent`
rather than retrying with a token that has been seen.

### Connection states

`GET /api/mcp/servers/status` reports, for every server with an `auth`
block, a `connection_state` plus `oauth` metadata (grant, issuer, client id,
scopes, RFC 8707 resource, expiry) and a safe `last_error` where one exists:

| State | Meaning | Way out |
|-------|---------|---------|
| `disabled` | Server toggled off (the default for every catalog server) | Enable it in Settings → Integrations |
| `dormant` | The `auth` block names a secret the store does not have | Store the secret under the named key |
| `needs_consent` | `authorization_code` grant, no refresh token yet (or a rotated token was reused) | Run the consent flow above |
| `connected` | Valid or refreshable token | — (refresh failure demotes to `error`) |
| `error` | Discovery failed, the IdP rejected a grant, or a scope deficit never resolved | Read `last_error` (sanitized — never token material); fix credentials (→ `dormant`) or re-consent (→ `needs_consent`) |

### Troubleshooting notes

- **Dormant, "awaiting credentials":** the store lacks the key named by
  `client_secret_key`. The server is not spawned and no token request is
  attempted until it resolves.
- **`error` with a grant rejection:** the IdP refused the token request and
  named why (invalid credentials, unknown scope). The message shown is the
  IdP's own error code — safe by construction; nothing token-shaped is
  logged.
- **Calls fail with a scope deficit:** the token Vigil holds lacks a scope
  the server demands. Fix the scopes on the IdP application, then reconnect.
  Vigil retries a `401`/`insufficient_scope` answer exactly once after a
  serialized refresh — a second failure is surfaced, never retried blind.
- **IdP outage:** outbound calls fail closed — an unresolvable token marks
  the connection `error`, and no call ships unsigned. Disable the server
  entry if you need the rest of the catalog unaffected.

## Inbound: IdP tokens on Vigil's own `/mcp`

Vigil's MCP surface authenticates callers with credentials minted from
Settings (`vgl_mcp_` tokens). A deployment whose staff identity lives in an
IdP can accept that issuer's JWTs beside them.

### The three settings — and the veto

In `env.example` (the "MCP surface" block):

```
VIGIL_MCP_OIDC_ISSUER=""
VIGIL_MCP_OIDC_AUDIENCE=""
VIGIL_MCP_OIDC_JWKS_URL=""
VIGIL_MCP_OIDC_ENABLED=""
```

The first three are the issuer tokens must come from, the audience they must
carry, and the key set signatures are checked against — **all three or
none**, because a verifier with any one missing cannot answer and must not
pretend to. None of them is a secret; they are the issuer's public facts.

`VIGIL_MCP_OIDC_ENABLED` is a tri-state veto. Blank (the default) means
"configured is on": filling in the three settings is the whole ceremony.
An explicit `false` keeps the verifier off even when the settings are
present — for an issuer outage, a migration, or a rollback.

What a token must satisfy (pinned in `core/auth/idp_jwt.py`):

- Signed with **RS256**. Anything else a token claims — HS256 with a key from
  this key set, `none` — is not a token this deployment issued. The algorithm
  list is pinned so a library default cannot widen it silently.
- Carries `exp`, `iss`, `aud`, `sub` — and `iss`/`aud` must match the
  configured issuer and audience exactly.
- Signature checked against the configured JWKS URL. PyJWT caches the key set
  and refetches when a token presents a `kid` it has not seen.

### Mapping a token to an account

A verified token still names nobody Vigil knows. The mapping is the account
whose **External subject** (set by an administrator through the users API/UI,
`users.external_subject`) equals the token's `sub` claim. An account nobody
mapped — or a mapped but deactivated one — is refused: identity provisioning
is an administrator's act, and a token cannot create an account by naming a
subject nothing holds. If the store cannot answer, the caller is refused
rather than handed an error that invites a retry.

Two things the token does **not** do:

- **It carries no permissions.** What the caller may do reads from its Vigil
  roles, exactly as for any other principal. IdP group or role claims are
  never auto-converted into Vigil permissions — role administration stays
  inside Vigil, where the escalation guard and audit trail live.
- **It is not a session.** No session fingerprint (`sfp`) rides an IdP token,
  and none is required; the fingerprint check applies to browser sessions
  only.

Minted `vgl_mcp_` credentials keep working either way. Leave the three
settings unset and nothing about the surface changes.

### Finding the values at your issuer

Every issuer publishes these in its discovery document at
`<issuer>/.well-known/openid-configuration` — the `issuer` claim there is the
value for `VIGIL_MCP_OIDC_ISSUER`, and `jwks_uri` is
`VIGIL_MCP_OIDC_JWKS_URL`. The audience is the identity of the API
registration you created for Vigil:

- **Entra ID:** an app registration (or `api://` application ID URI) the
  tokens name in `aud`; issuer `https://login.microsoftonline.com/<tenant-id>/v2.0`.
- **Okta:** your authorization server's issuer
  (`https://<org>/oauth2/<auth-server-id>`); audience as configured on the
  access-policy's target.
- **Keycloak:** `https://<host>/realms/<realm>`; audience via a mapper on the
  client.
- **Auth0:** `https://<tenant>.auth0.com/`; audience is the API identifier.

Register the subject → account mapping in Vigil's users screen, and the
token is accepted the next time it is presented.

## What this replaces — and what it does not

- A `streamable-http` entry with an `auth` block never spawns the
  `mcp-remote` bridge: token acquisition, refresh, and rotation are tested
  Vigil code, not a child process's browser flow. Bridged entries stay
  supported until each vendor server migrates.
- stdio servers keep their vendor credentials. A vendor's local server
  authenticates against the vendor's issuer, not yours — replacing those
  static credentials with IdP tokens is a non-goal, not a gap this feature
  papers over.

## Related

- [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) — the profile Vigil implements
- [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) — Protected Resource Metadata
- [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html) — Resource Indicators (audience-bound tokens)
- [`env.example`](../env.example) — the "MCP surface" block for the inbound settings
- [`mcp-config.json`](../mcp-config.json) — `_comment_native_transport` and the `azure-sentinel-native` worked example
- [`SECURITY.md`](../SECURITY.md) — vulnerability reporting

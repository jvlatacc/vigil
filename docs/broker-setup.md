# Identity broker setup — Keycloak federating FreeIPA

How to sign in to Vigil through the upstream directory instead of (or next to)
local passwords. FreeIPA stays the authoritative identity source; an OIDC
broker — Keycloak in this runbook — fronts it, because FreeIPA is not an OIDC
issuer. Federation is **off by default**: with `OIDC_ISSUER_URL` or
`OIDC_CLIENT_ID` empty, the `/api/auth/oidc/*` routes answer 404 and local
login behaves exactly as it did before this existed.

The one flow, end to end:

```
browser                Vigil backend                 Keycloak                FreeIPA
   │  GET /api/auth/oidc/login   │                        │                    │
   │────────────────────────────▶│  discovery (cached)    │                    │
   │                             │───────────────────────▶│                    │
   │◀── 302 authorize ───────────│  state+nonce+PKCE in Redis                  │
   │  (Authorization Code + PKCE S256)                    │                    │
   │─────────────────────────────────────────────────────▶│  LDAP/SSSD bind    │
   │        sign in at the broker                         │───────────────────▶│
   │◀─────────────────────────────────────────────────────│                    │
   │  GET /api/auth/oidc/callback?code&state   ◀── 302 ───│                    │
   │────────────────────────────▶│ code+verifier → tokens │                    │
   │                             │ verify id_token:       │                    │
   │                             │  sig via JWKS, iss,    │                    │
   │                             │  aud, exp, nonce       │                    │
   │                             │ JIT-link user,         │                    │
   │                             │ role = f(groups)       │                    │
   │◀── 302 + session cookies ───│  (the existing local-session JWTs)          │
```

After the callback, nothing downstream changes: the session is the same JWT
the local login mints, with the same cookies, revocation, and fingerprint
checks. Every federated login re-decides the role from the directory groups —
a locally-granted role does not survive a directory that stops vouching for
the person.

## 1 · Boot the broker (docker-compose)

The compose file ships an opt-in Keycloak profile (`infra/docker/`):

```bash
cd infra/docker
# pick a real password first — the committed default is loud on purpose
echo "KEYCLOAK_ADMIN_PASSWORD=…" >> .env
docker compose --profile federation up -d keycloak
```

Without `--profile federation` nothing here starts, and existing deployments
change nothing. On first boot the profile imports the realm from
`infra/docker/keycloak/vigil-realm.json`:

- realm **vigil** (`--import-realm` skips a realm that already exists, so a
  later edit to the JSON does not clobber operator changes);
- client **vigil-console** — public, Authorization Code only (no direct
  grants), PKCE S256 enforced via the `pkce.code.challenge.method` attribute;
- a group-membership mapper putting the user's groups into the **`groups`**
  claim of the ID, access, and userinfo responses — full group path off, so
  the claim carries bare names (`vigil-admins`, not `/vigil-admins`).

The broker binds to `127.0.0.1:8080` and its healthcheck (`/health/ready` on
the management port) goes green in about a minute. Console:
<http://localhost:8080> — sign in with `KEYCLOAK_ADMIN_USERNAME` /
`KEYCLOAK_ADMIN_PASSWORD` (the bootstrap admin lives in the *master* realm).

`start-dev` is the loopback/no-TLS mode. See *Going to production* below
before exposing this to anything but your own machine.

### Where the issuer URL must point (compose)

The backend fetches discovery from `OIDC_ISSUER_URL` itself, and checks that
both the discovery document's `issuer` and the token's `iss` equal that exact
string. With `start-dev` the broker builds those from the request Host — so
the same hostname must work from the browser **and** from inside the backend
container. `host.docker.internal` does both (the backend service already maps
it to the host gateway for Ollama):

```
# infra/docker/.env
KEYCLOAK_ADMIN_PASSWORD=…
KEYCLOAK_ADMIN_USERNAME=admin
OIDC_ISSUER_URL=http://host.docker.internal:8080/realms/vigil
OIDC_CLIENT_ID=vigil-console
OIDC_CLIENT_SECRET=            # public client — the secret stays unset
```

On Docker Desktop `host.docker.internal` resolves everywhere already. On
native Linux, add one line to the host's `/etc/hosts` so the browser can
follow the redirect the backend mints:

```
127.0.0.1  host.docker.internal
```

Restart the backend after changing its environment; then confirm the broker
answers:

```bash
curl -fsS http://localhost:8080/realms/vigil/.well-known/openid-configuration | grep '"issuer"'
```

## 2 · Federate FreeIPA into the broker

In the Keycloak console (master realm → **Manage realms** → vigil), add the
directory. Two supported shapes:

**LDAP federation** (the common path): **User federation → LDAP**

- Connection URL `ldaps://ipa.example.com`, StartTLS off (LDAPS already
  encrypts), Bind type *simple* with a **read-only service account** — a
  dedicated system account, not a person's credentials;
- Users DN / Groups DN per your directory (e.g.
  `cn=users,cn=accounts` / `cn=groups,cn=accounts,dc=example,dc=com`);
- Username LDAP attribute `uid`; **Groups and Roles** mapper: *LDAP Groups
  Path* empty (so the token claim carries bare `cn`s, matching the realm
  import's full-path-off mapper), *User Groups Retrieve Strategy* *
  Load groups by member attribute*, membership attribute `member`;
- *Import users* on demand. Cache settings per your change rate.

**SSSD federation** (hosts already enrolled in the domain): Keycloak reads
users and groups through SSSD's D-Bus on the broker host instead of speaking
LDAP directly. Prefer this only where host enrollment already exists — it
couples the broker container to host state, which the LDAP shape avoids.

### Group naming

Vigil's role mapping reads bare group names from the `groups` claim. The
convention (any names work — these are what the rest of the docs assume):

| FreeIPA group | Maps to |
|---|---|
| `vigil-admins` | the Administrator role |
| `vigil-operators` | the analyst/operator role |
| `vigil-auditors` | the read-only auditor role |

Keep one group per role, and keep membership flat. Nested group resolution is
exactly the kind of thing to test explicitly if you use it (see the smoke
test) — the claim carries whatever the broker resolved, and a group that
arrives under a different name than the mapping row expects maps to nothing,
which is the safe direction.

## 3 · Map groups to Vigil roles

Mappings are data, not code: `role_group_mappings` rows, administered at
`/api/role-group-mappings` (Settings → Roles), every route gated
`users.write` and every write re-proving the actor could hold the role.

Resolution at each federated login: the intersection of the token's `groups`
with the mapping rows wins by **highest priority** (ties break to the
earliest-created row). A user whose groups match **no** mapping signs in as
the unmapped role — an empty permission map — and the console shows
`?oidc_state=unmapped`. Deny by default, visibly labeled.

## 4 · First-login smoke test

1. **Directory side**: pick (or create) a FreeIPA user, put them in
   `vigil-admins`, note their email — linking is by email first, then by
   username. A username that belongs to a local account with a different
   email is refused, not merged.
2. **Broker side**: user federation up, the user resolvable in the Keycloak
   console (Users → View all users after their first lookup).
3. **Vigil side**: the mapping row exists (`vigil-admins` → Administrator).
4. Drive the flow in a browser — the console's SSO button lands with the
   console work; until then the API starts the flow directly:

   ```
   http://localhost:6987/api/auth/oidc/login
   ```

   Expect: 302 to the broker → sign in as the FreeIPA user → 302 back to the
   console with session cookies set.
5. Check the seams where it usually breaks:
   - **404 at `/api/auth/oidc/login`** — federation is off: `OIDC_ISSUER_URL`
     or `OIDC_CLIENT_ID` empty in the backend's environment.
   - **502 "Identity provider unavailable"** — the backend cannot reach the
     broker (from inside the container — the compose wiring above exists for
     exactly this).
   - **401 at the callback, nothing in the browser** — the token was
     verified and refused: the specific reason is in the backend log, never
     in the response. Wrong issuer/audience/expiry and replayed state all
     look identical from outside, on purpose.
   - **Signed in, `?oidc_state=unmapped`, zero permissions** — the identity
     linked but its groups matched no mapping row. Fix the mapping (or the
     group naming in §2), then sign in again — the role is re-decided fresh
     at every federated login.
6. Confirm the unmapped path too: remove the user from `vigil-admins`, sign
   in again, and see the labeled no-access session. That state is the
   deny-by-default guarantee working.

## Going to production

`start-dev` is for the operator's machine. Before the broker leaves the host:

- **TLS + hostname**: run `start` with `--hostname <public-url>` and TLS
  terminated in front (or `--https-*` flags). The issuer URL stops being
  host-dependent once a fixed hostname is set — set `OIDC_ISSUER_URL` to it.
- **Database**: point `KC_DB` at Postgres (`KC_DB=postgres`, `KC_DB_URL_*`)
  instead of the dev-file store; the compose profile's named volume is
  convenience, not a backup story.
- **Rotate `KEYCLOAK_ADMIN_PASSWORD`**; the committed default is a tripwire,
  not a password.
- **Pinning the realm**: `--import-realm` never overwrites — operator changes
  in the console win after the first boot. Keep the JSON the source of truth
  for a *fresh* environment and change the console for a live one.
- **Redirect URIs**: the realm import registers
  `http://localhost:6987/api/auth/oidc/callback` for the compose profile.
  Behind a rewriting proxy or a real hostname, register the deployed
  callback and pin `OIDC_REDIRECT_URI` so the backend does not derive it
  from a proxied `Host` header.
- **Helm**: the chart ships no broker — deploy Keycloak beside the cluster
  and wire the values per `infra/helm/vigil/README.md`.

## Failure behavior (what the code promises)

- **Broker unreachable** → federated login fails closed (502 at login, or
  502 at verification); local login and existing sessions are untouched.
- **Token anything-but-perfect** (signature, issuer, audience, expiry,
  nonce, replayed state) → 401, one generic refusal; the specific reason is
  only in the backend log.
- **Redis down** → sign-in state cannot be checked, so sign-in answers 503
  rather than proceeding unverified.
- **Unmapped user** → a session that can see the console and do nothing,
  labeled as such. Privileges arrive only through a mapping row, and a
  locally-granted role does not survive the directory disagreeing.

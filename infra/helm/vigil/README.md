# Vigil SOC Helm chart

Production chart for the Vigil API, daemon, workers, and optional in-cluster
Postgres/Redis.

Subcharts are pinned in-repo: the `charts/*.tgz` files are vendored and
checksummed (`SHA256SUMS`) so CI never fetches charts from the network — to
bump one, run `helm dependency update infra/helm/vigil`, refresh `SHA256SUMS`
from the upstream digests, and commit the new tgz files.

Full install, values, and troubleshooting:
[docs/deploy/helm-chart.md](../../../docs/deploy/helm-chart.md)

## OIDC federation (optional)

The chart ships no broker. Deploy Keycloak (or any OIDC issuer that federates
your directory) beside or outside the cluster per
[docs/broker-setup.md](../../../docs/broker-setup.md), then wire the backend:

- **Non-secret settings** through `extraConfig` (rendered into the backend's
  environment last, so they win):

  ```yaml
  extraConfig:
    OIDC_ISSUER_URL: https://keycloak.example.com/realms/vigil
    OIDC_CLIENT_ID: vigil-console
    OIDC_SCOPES: openid profile email
    OIDC_GROUPS_CLAIM: groups   # or resource_access.vigil.roles for client roles
  ```

- **Secrets** by key name: add `OIDC_CLIENT_SECRET` to the pre-created
  `secrets.existingSecret` (keys match env var names), or map it through
  `secrets.externalSecret`. A public client needs no secret at all — leave
  it unset.
- **Redirect URI**: register `<console-url>/api/auth/oidc/callback` on the
  realm's client before first sign-in.
- Unset keys leave federation off — the `/api/auth/oidc/*` routes answer 404
  and local login is unaffected.

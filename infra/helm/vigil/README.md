# Vigil SOC Helm chart

Production chart for the Vigil API, daemon, workers, and optional in-cluster
Postgres/Redis.

Subcharts are pinned in-repo: the `charts/*.tgz` files are vendored and
checksummed (`SHA256SUMS`) so CI never fetches charts from the network — to
bump one, run `helm dependency update infra/helm/vigil`, refresh `SHA256SUMS`
from the upstream digests, and commit the new tgz files.

Full install, values, and troubleshooting:
[docs/deploy/helm-chart.md](../../../docs/deploy/helm-chart.md)

Cloud profiles (EKS, AKS, GKE) and the research/decision trail: [thunking/](../../../thunking/).

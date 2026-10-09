# Enforcement API contract

The daemon's HTTP surface is a contract with Vigil's Python executor, not an
internal detail. Following the medic convention (`services/medic/contracts/`):

- **`*.schema.json`** — the normative wire formats, JSON Schema draft
  2020-12. A schema that looks wrong is a contract change: its own PR, not a
  drive-by edit.
  - `action-request.schema.json` — POST /v1/actions body
  - `action-response.schema.json` — success reply (fresh and replayed);
    the `evidence` object is what `mark_executed` stores verbatim
  - `error-response.schema.json` — every non-success reply; the `error`
    codes are a closed vocabulary
  - `healthz.schema.json` — GET /healthz payload with per-primitive
    capability fields
- **`vector.schema.json`** — the format of the executable vectors below.
- **`vectors/v*.json`** — ordered HTTP steps with expected outcomes,
  covering the behaviours the spec names: idempotent replay, TTL floor,
  loopback/multicast refusal, unauthenticated rejection, unknown kinds,
  per-primitive unavailability, action_id conflicts, releases, and
  kind/target matching.

## Enforcement

`internal/api/contract_vector_test.go` executes every vector against the
real handlers on a fresh FakeKernel and asserts status, state, error code,
`details.reason`, the `replayed` flag, and that evidence echoes the caller's
`action_id`. It also structurally validates success replies against the
response contract's required keys (the stdlib subset of the JSON Schema).

The Python integration slice (next PRs) reads these schemas as its client
spec. A vector that looks wrong is a contract change: made in its own PR.

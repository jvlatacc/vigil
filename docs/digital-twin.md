# Digital twin

A live map of what an environment looks like — devices, the processes on
them, and the connections between them — so an analyst can see an intrusion
in the shape of the network it moved through. Feeds post observations; Vigil
upserts them into a versioned inventory and derives a layered graph the
console reads.

The twin is fed by observation ingest, not by inference: a host sensor, a
seed script, or an NDR adapter posts what it saw, and every fact in the twin
is one of those observations or an upsert of one. The vocabulary — devices,
processes, connections — is the settled contract; the graph shape on top of
it is still maturing, which is why the read surface the console uses is
deliberately unversioned.

## Where it lives

| Piece | Path | What it is |
|---|---|---|
| Contract API | `core/api/v1/digital_twin_router.py` | The versioned surface at `/api/v1/digital-twin` |
| Console API | `core/twin/twin_router.py` | Unversioned `/api/twin`, mounted from `ROUTER_META` by `services/api/discovery.py` |
| Ingest logic | `core/twin/ingest.py` | Upsert and read logic — session-passing and commit-free, so every route joins the request's unit of work |
| Graph derivation | `core/twin/graph.py` | `build_graph()` layers the graph from the stored rows |
| Models | `core/storage/models/digital_twin.py` | `TwinDevice`, `TwinProcess`, `TwinConnection` |
| Schemas | `core/storage/schemas/digital_twin.py` | `TwinIngestBatch`, `TwinIngestResult`, `TwinDeviceListResponse`, `TwinGraphPayload` |
| Demo seed | `scripts/seed_digital_twin_demo.py` | A five-device demo topology with a lateral-movement story |

## The contract surface: `/api/v1/digital-twin`

Three routes, all `Auth.REQUIRED` — MACs and serials are sensitive
inventory, and nothing about the twin is public:

| Route | Does |
|---|---|
| `POST /ingest` | Upsert a batch of observations (`TwinIngestBatch`) and get back what happened (`TwinIngestResult`) |
| `GET /graph` | The whole twin in one payload: devices, processes, connections, edges (`TwinGraphPayload`) |
| `GET /devices` | The device inventory |

Routes answer at the versioned paths and at their pre-version aliases
(`legacy_prefixes`): one handler set, two addresses, the v1 contract
convention.

## The console surface: `/api/twin`

`core/twin/twin_router.py` serves `GET /api/twin/graph` — a console surface,
not a contract. The graph shape will churn as the twin matures, so the router
lives outside the frozen `/api/v1` tree (see `core/api/v1/README.md`'s
tie-breaker for unversioned surfaces). This is the graph the case view reads:
it joins findings to twin rows, so a finding can carry the device and process
context it was observed on (`_case_ids_by_finding`). The console's dedicated
twin screen reads the versioned graph instead —
`clients/web/src/screens/twin/DigitalTwinScreen.tsx` wires
`GET /api/v1/digital-twin/graph` (`useTwinGraph.ts`).

## Observations and idempotency

An ingest batch is `{source, devices[], processes[], connections[]}` —
processes reference their device and connections reference their process by
natural key. A connection the sensor could not attribute to a process carries
its `device` hostname instead: a device-level observation.

Every row carries the natural key the ingest upserts against:

- `device_key` — `host:<hostname>`, `mac:<normalized>`, or `serial:<serial>`
- `process_key` — `{device_key}:{pid}:{name}`
- `connection_key` — `{device_key}:{type}:{proto}:{lip}:{lport}:{rip}:{rport}`

Re-posting a batch therefore finds every row it wrote, updates the observed
attributes, and bumps `last_seen` — row counts never change. `first_seen` is
written once and never touched again, which is what makes the observation
bookkeeping survive re-seeding.

Connections span three `connection_type` values — listening sockets,
established streams, and long-lived sessions — so the graph can show an
nginx listening on the internet-facing interface, an established C2 stream,
and an operator's persistent SSH session as the different facts they are.

## Seeding a demo

The read API has no real feed behind it by default: until a host sensor or an
EDR/SIEM adapter posts to `/api/v1/digital-twin/ingest`, the graph has
nothing to draw. `scripts/seed_digital_twin_demo.py` loads a demo dataset —
five devices, the processes on them, and the connections they held — telling
one lateral-movement story an analyst can walk end to end:

```text
analyst-ws (SSH) ──► web-01  (nginx, internet-facing — compromised)
                          │  ssh client running as www-data
                          ▼
                        app-01  (pivot through the app tier)
                          │  ssh client running as www-data
                          ▼
                        db-01  (customer database)
```

The lobby camera and the analyst's browser add texture the story needs to be
readable: the camera's RTSP session back to the NVR, the browser session into
the DMZ box. One unattributed outbound flow from `db-01` shows a device-level
connection — a fact with no owning process.

The script is idempotent for the same reason the ingest is: every row carries
its natural key, so running it again updates `last_seen` and changes nothing
else.

## API example

Ingest a single batch, then read the graph:

```bash
curl -sS -X POST http://localhost:6987/api/v1/digital-twin/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "host-sensor",
    "devices": [{"hostname": "web-01"}],
    "processes": [],
    "connections": []
  }'

curl -sS http://localhost:6987/api/v1/digital-twin/graph \
  -H "Authorization: Bearer $TOKEN"
```

Fields beyond the natural keys shown here (roles, MACs, serials, first/last
seen) are in the schemas: `core/storage/schemas/digital_twin.py` for the
contract, `core/storage/schemas/twin.py` for the console graph shape.

# VigilMap

A standalone, zero-backend 3D explorer for [Vigil](../README.md)'s episodic
memory: the entities memory has seen, the verdicts its hunts concluded, the
gaps it recorded, and how they connect — rendered as a graph you can orbit,
filter, and inspect. No Postgres, no Vigil API: the app reads a validated
`MemoryGraphDocument` (schema version 1, defined in
[`src/types.ts`](src/types.ts)) and nothing else.

> **Status — scaffold.** This PR ships the data contract, the load-time
> validator, source resolution, and the app shell (loading / error / empty /
> ready states). The 3D graph, filters, and detail panel land in the next PR
> of the series; the Python exporter after that.

## Run

```sh
npm i
npm run dev
```

…then open the printed URL. With no `?data=` parameter the app loads the
bundled sample at `public/data/sample-memory.json` (a small hand-written
placeholder for now — the deterministic seeded generator replaces it in a
later PR of this series).

## Load your own data

Three paths in, one funnel through the validator — a document that breaks the
contract is rejected with a named error, never half-rendered:

- **Bundled sample** — the default when no `?data=` parameter is present.
- **`?data=<url>`** — fetch any URL serving a `MemoryGraphDocument`.
- **Drop a file** — drop a `.json` document anywhere on the page.

## Export (coming)

`export/export_memory.py` will read a live deployment's episodic tables
(`episodic_sightings`, `episodic_verdicts`, `episodic_verdict_sources`,
`episodic_gaps`, `episodic_distil_markers`) and emit the document the app
reads:

```sh
DATABASE_URL=postgres://… python vigilmap/export/export_memory.py --output memory.json [--since 2026-09-01]
```

It will mint entity keys with `core.memory.entity_keys` when run inside the
repo, falling back to `export/key_rule.py` — a stated copy guarded by a CI
drift test, so the two can never disagree.

## The document contract

Six node kinds (`entity | sighting | verdict | gap | hunt | episode`), seven
link relations, and closed vocabularies for entity types and verdict outcomes
— mirrored from `core/memory/recall_contract.py`. The full shape lives in
[`src/types.ts`](src/types.ts); the validator in [`src/validate.ts`](src/validate.ts)
enforces it on load. Anything that changes the link table bumps
`schemaVersion` and gets a migration note here; the app renders only its own
version and says so otherwise.

## Development

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | Production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint 9 (flat config) |
| `npm test` | vitest, one run |

Tests live in [`tests/`](tests/): contract validation (every rejection case
with the named error asserted), source resolution for all three paths, and
store derivations. CI (`.github/workflows/vigilmap.yml`) runs all of the
above on every PR touching `vigilmap/**`.

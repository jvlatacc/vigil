# VigilMap

A standalone, zero-backend 3D explorer for [Vigil](../README.md)'s episodic
memory: the entities memory has seen, the verdicts its hunts concluded, the
gaps it recorded, and how they connect — rendered as a graph you can orbit,
filter, and inspect. No Postgres, no Vigil API: the app reads a validated
`MemoryGraphDocument` (schema version 1, defined in
[`src/types.ts`](src/types.ts)) and nothing else.

## Run

```sh
npm i
npm run dev
```

…then open the printed URL. With no `?data=` parameter the app loads the
bundled sample at `public/data/sample-memory.json` — a deterministic seeded
scenario (two hunts over one phishing→C2 campaign) covering every verdict
outcome, every entity type, gaps, and a learning episode.

Regenerate it with `python3 scripts/generate_sample.py --output
public/data/sample-memory.json`; the output is byte-identical across runs,
and CI diffs a fresh regeneration against the checked-in file.

## Load your own data

Three paths in, one funnel through the validator — a document that breaks the
contract is rejected with a named error, never half-rendered:

- **Bundled sample** — the default when no `?data=` parameter is present.
- **`?data=<url>`** — fetch any URL serving a `MemoryGraphDocument`.
- **Drop a file** — drop a `.json` document anywhere on the page.

An empty-but-valid document renders an empty scene with a note, not a blank
screen. WebGL is required; browsers without it get a plain-language error.

## Export live memory

`export/export_memory.py` reads a live deployment's episodic tables
(`episodic_sightings`, `episodic_verdicts`, `episodic_verdict_sources`,
`episodic_gaps`, `episodic_distil_markers`) and emits the document the app
reads:

```sh
DATABASE_URL=postgres://… python vigilmap/export/export_memory.py --output memory.json [--since 2026-09-01]
```

Then serve it any way you like and open the app with `?data=<url>` — or drop
`memory.json` onto the page. Entity keys are minted with
`core.memory.entity_keys` when run inside the repo, falling back to
`export/key_rule.py` — a stated copy guarded by a CI drift test, so the two
can never disagree.

## The explorer

Click a node to select it and open its detail panel; click the background or
press `Esc` to clear. Hovering highlights a node's direct neighborhood and
dims the rest. `/` focuses search — Enter jumps to and selects the best
match. Filters (kinds, entity types, verdict outcomes, time window) hide
rather than delete; a selected node that gets filtered out clears. The
camera is free-orbit; `recenter` (top bar) frames the selection. Auto-rotate
defaults off and honors `prefers-reduced-motion`. Sightings show their
labels on zoom-in only; large exports cap the initial visible set (sightings
first) and say how many they trimmed.

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
with the named error asserted), graph build, filters, detail mapping, source
resolution for all three paths, sample validity, and store derivations. The
Python exporter's suite is under [`export/tests/`](export/tests/). CI
(`.github/workflows/vigilmap.yml`) runs the Node gates, the exporter suite
with the key-rule drift guard, and the sample-determinism diff on every PR
touching `vigilmap/**`.

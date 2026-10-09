import { useEffect, useMemo, useState } from 'react'
import { EmptyState, FilterButton, FilterGroup } from '../../shared/ui'
import { Hbars, Pie } from '../../shared/charts'
import { Icon } from '../../shared/icons'
import type { ConsoleScreenProps } from '../../shared/types'
import FindingPopup from '../dashboard/FindingPopup'
import TwinGraphCanvas from './TwinGraphCanvas'
import NodeFindingsPopover from './NodeFindingsPopover'
import { useTwinGraph } from './useTwinGraph'
import {
  ANY_TWIN_FILTERS,
  BUCKETS_WITH_UNRANKED,
  SEV_COLOR,
  SEV_LABEL,
  SEVERITY_BUCKETS,
  filterGraph,
  severityTotals,
  type TwinFilters,
  type TwinNodeVM,
  type TwinSevBucket,
} from './model'
import './twin.css'

const SEV_OPTIONS: { value: string; label: string }[] = [
  { value: 'any', label: 'Any severity' },
  ...SEVERITY_BUCKETS.map((b) => ({ value: b, label: SEV_LABEL[b] })),
]

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'any', label: 'Any status' },
  { value: 'open', label: 'Open' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'closed', label: 'Closed' },
]

export default function NetworkTwinScreen({ go, goSettings, openCase, setViewFull }: ConsoleScreenProps) {
  // a canvas screen: full height, nothing scrolling beneath it
  useEffect(() => {
    setViewFull(true)
    return () => setViewFull(false)
  }, [setViewFull])

  const { graph, phase, error, refreshing, reload } = useTwinGraph()
  const [filters, setFilters] = useState<TwinFilters>(ANY_TWIN_FILTERS)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [findingId, setFindingId] = useState<string | null>(null)

  const filtered = useMemo(() => (graph ? filterGraph(graph, filters) : null), [graph, filters])

  // selection survives polls: re-point at the refreshed node, clear when it's gone
  const selected = useMemo(
    () => (selectedId && filtered ? filtered.nodes.find((n) => n.id === selectedId) ?? null : null),
    [selectedId, filtered],
  )
  useEffect(() => {
    if (selectedId && !selected) setSelectedId(null)
  }, [selectedId, selected])

  const sources = useMemo(() => {
    const set = new Set<string>()
    for (const n of graph?.nodes ?? []) {
      for (const f of n.findings) {
        if (f.src && f.src !== '—') set.add(f.src)
      }
    }
    return [{ value: 'any', label: 'Any source' }, ...Array.from(set).sort().map((s) => ({ value: s, label: s }))]
  }, [graph])

  const matched = filtered?.matchedFindings.length ?? 0
  const totals = useMemo(() => severityTotals(filtered?.matchedFindings ?? []), [filtered])
  const caseCount = useMemo(
    () => new Set((filtered?.nodes ?? []).flatMap((n) => n.cases.map((c) => c.id))).size,
    [filtered],
  )
  const totalFindings = useMemo(
    () => new Set((graph?.nodes ?? []).flatMap((n) => n.findings.map((f) => f.id))).size,
    [graph],
  )
  const topNodes = useMemo(() => {
    const nodes = filtered?.nodes ?? []
    const max = Math.max(1, ...nodes.map((n) => n.findings.length))
    return [...nodes]
      .sort((a, b) => b.findings.length - a.findings.length)
      .slice(0, 5)
      .map((n) => ({
        label: n.label,
        val: n.findings.length,
        pct: Math.round((n.findings.length / max) * 100),
        cls: `sev-${worst(n)}`,
      }))
  }, [filtered])

  const activeFacets = (filters.severity !== 'any' ? 1 : 0) + (filters.status !== 'any' ? 1 : 0) + (filters.source !== 'any' ? 1 : 0)

  const clearFacets = () => setFilters((f) => ({ ...f, severity: 'any', status: 'any', source: 'any' }))

  return (
    <div className="twin-screen">
      <div className="twin-toolbar">
        <div className="twin-search">
          <Icon name="search" size={14} />
          <input
            value={filters.query}
            onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
            placeholder="Search hosts, addresses, accounts, findings…"
            aria-label="Search the map"
          />
        </div>
        <FilterButton activeCount={activeFacets} onClearAll={clearFacets}>
          <FilterGroup
            label="Severity"
            value={filters.severity}
            options={SEV_OPTIONS}
            onSelect={(v) => setFilters((f) => ({ ...f, severity: v as TwinFilters['severity'] }))}
          />
          <FilterGroup
            label="Status"
            value={filters.status}
            options={STATUS_OPTIONS}
            onSelect={(v) => setFilters((f) => ({ ...f, status: v as TwinFilters['status'] }))}
          />
          <FilterGroup
            label="Source"
            value={filters.source}
            options={sources}
            onSelect={(v) => setFilters((f) => ({ ...f, source: v }))}
          />
        </FilterButton>
        <div className="flex-1" />
        {refreshing && (
          <span className="twin-updating" role="status">
            Updating…
          </span>
        )}
        {graph && (
          <span className="twin-generated">
            Generated {graph.generatedAt}
          </span>
        )}
        <button className="btn ghost" onClick={reload} title="Refresh the map">
          <Icon name="refresh" size={14} />
        </button>
      </div>

      <div className="twin-kpis" aria-label="Map summary">
        <div className="twin-kpi">
          <span className="twin-kpi-label">Findings on map</span>
          <span className="twin-kpi-value">
            {graph ? matched : '—'} <span className="twin-kpi-of">of {graph ? totalFindings : '—'}</span>
          </span>
        </div>
        <div className="twin-kpi">
          <span className="twin-kpi-label">Nodes</span>
          <span className="twin-kpi-value">{filtered ? filtered.nodes.length : '—'}</span>
        </div>
        <div className="twin-kpi">
          <span className="twin-kpi-label">Cases</span>
          <span className="twin-kpi-value">{filtered ? caseCount : '—'}</span>
        </div>
        <div className="twin-kpi twin-kpi-chart" aria-label="Severity mix">
          {matched > 0 ? (
            <>
              <Pie
                segs={BUCKETS_WITH_UNRANKED.map((b) => ({
                  v: totals[b] / matched,
                  color: SEV_COLOR[b],
                  label: SEV_LABEL[b],
                }))}
                size={44}
              />
              <div className="twin-kpi-legend">
                {SEVERITY_BUCKETS.map((b) => (
                  <span key={b}>
                    <i style={{ background: SEV_COLOR[b] }} /> {totals[b]} {SEV_LABEL[b].toLowerCase()}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <span className="twin-kpi-empty">No findings match</span>
          )}
        </div>
        <div className="twin-kpi twin-kpi-top">
          <span className="twin-kpi-label">Most affected</span>
          {topNodes.length > 0 ? <Hbars items={topNodes} /> : <span className="twin-kpi-empty">—</span>}
        </div>
      </div>

      <div className="twin-stage">
        {phase === 'loading' && (
          <div className="twin-loading" role="status" aria-live="polite">
            <span className="spin" aria-hidden="true" />
            <span>Drawing the map…</span>
          </div>
        )}

        {phase === 'error' && (
          <EmptyState
            error
            icon="alert"
            title="Couldn't load the map"
            body={error || 'The twin graph request failed.'}
            primary={{ label: 'Retry', onClick: reload, icon: 'refresh' }}
          />
        )}

        {phase === 'ready' && graph !== null && graph.nodes.length === 0 && (
          <EmptyState
            icon="graph"
            title="No findings to map yet"
            body="The twin is derived from what findings name — hosts, addresses, accounts. Connect a data source or check what the dashboard already holds."
            primary={{ label: 'Open Dashboard', onClick: () => go('dashboard'), icon: 'grid' }}
            secondary={{ label: 'Configure sources', onClick: () => goSettings('integrations'), icon: 'gear' }}
          />
        )}

        {phase === 'ready' && graph !== null && graph.nodes.length > 0 && filtered && (
          <div className="twin-stage-inner">
            {error && (
              <div className="twin-banner" role="alert">
                <Icon name="alert" size={14} />
                <span>Live refresh failed — showing the map as last generated.</span>
                <button className="btn ghost" onClick={reload}>
                  Retry
                </button>
              </div>
            )}
            <TwinGraphCanvas
              nodes={filtered.nodes}
              edges={filtered.edges}
              selectedId={selectedId}
              onNodeSelect={(n: TwinNodeVM) => setSelectedId(n.id)}
              onPaneSelect={() => setSelectedId(null)}
            />
            {filtered.nodes.length === 0 && (
              <div className="twin-no-match" role="status">
                <span>No nodes match the current filters.</span>
                <button
                  className="btn ghost"
                  onClick={() => setFilters({ ...ANY_TWIN_FILTERS, query: filters.query })}
                >
                  Clear severity, status and source
                </button>
              </div>
            )}
            {selected && (
              <NodeFindingsPopover
                node={selected}
                onClose={() => setSelectedId(null)}
                onOpenFinding={(id) => {
                  setSelectedId(null)
                  setFindingId(id)
                }}
                onOpenCase={openCase}
              />
            )}
          </div>
        )}
      </div>

      <FindingPopup id={findingId} onClose={() => setFindingId(null)} onChanged={reload} />
    </div>
  )
}

/** a node's ring bucket, for the bar tint in the Most affected list */
function worst(node: TwinNodeVM): TwinSevBucket | 'unranked' {
  for (const b of SEVERITY_BUCKETS) {
    if (node.severityCounts[b] > 0) return b
  }
  return 'unranked'
}

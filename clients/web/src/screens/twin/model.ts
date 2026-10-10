/* View model for the Twin screen: a pure mapping from the served graph plus
 * the console's own findings/cases rows to what the map renders. All graph
 * logic the screen needs lives here so it stays testable without React
 * Flow — the components are renderers over these types. */
import { format } from 'date-fns'
import type { IconName } from '../../shared/icons'
import type { CaseRow, Finding } from '../../data/data'
import type { Schema } from '../../services/apiTypes'

export type TwinSevBucket = 'crit' | 'high' | 'med' | 'low'
export type TwinNodeKind = 'host' | 'ip' | 'user' | 'unattributed'
export type TwinEdgeKind = 'flow' | 'link'

/** The four buckets the console's severity tokens know, plus the bucket a
 *  finding with no usable severity lands in — mirrors the backend's
 *  SEVERITY_BUCKETS + unranked (core/twin/graph.py). */
export type SeverityCounts = Record<TwinSevBucket | 'unranked', number>

export const SEVERITY_BUCKETS: readonly TwinSevBucket[] = ['crit', 'high', 'med', 'low']

/** bucket iteration including the unranked tail, for donut/legend sweeps */
export const BUCKETS_WITH_UNRANKED: (TwinSevBucket | 'unranked')[] = [...SEVERITY_BUCKETS, 'unranked']

export const SEV_COLOR: Record<TwinSevBucket | 'unranked', string> = {
  crit: 'var(--crit)',
  high: 'var(--high)',
  med: 'var(--med)',
  low: 'var(--ok)',
  unranked: 'var(--tx-3)',
}

export const SEV_LABEL: Record<TwinSevBucket | 'unranked', string> = {
  crit: 'Critical',
  high: 'High',
  med: 'Medium',
  low: 'Low',
  unranked: 'Unrated',
}

export const NODE_GLYPH: Record<TwinNodeKind, IconName> = {
  host: 'grid',
  ip: 'link',
  user: 'user',
  unattributed: 'more',
}

export const NODE_KIND_LABEL: Record<TwinNodeKind, string> = {
  host: 'Host',
  ip: 'Address',
  user: 'Account',
  unattributed: 'Unpinned',
}

export interface TwinCaseRef {
  id: string
  title: string
  status: string
  prio: CaseRow['prio']
}

export interface TwinNodeVM {
  id: string
  kind: TwinNodeKind
  label: string
  /** the node's findings in view-model shape — every row here is openable */
  findings: Finding[]
  cases: TwinCaseRef[]
  severityCounts: SeverityCounts
  position?: { x: number; y: number }
}

export interface TwinEdgeVM {
  id: string
  source: string
  target: string
  kind: TwinEdgeKind
  weight: number
  findingIds: string[]
}

export interface TwinGraphVM {
  generatedAt: string
  nodes: TwinNodeVM[]
  edges: TwinEdgeVM[]
}

export interface TwinFilters {
  severity: 'any' | TwinSevBucket
  status: 'any' | Finding['status']
  /** 'any' or a data_source */
  source: string
  query: string
}

export const ANY_TWIN_FILTERS: TwinFilters = { severity: 'any', status: 'any', source: 'any', query: '' }

/** the mapper's missing-value dash (mappers.ts keeps its own private one) */
const DASH = '—'

type ApiTwinGraph = Schema<'TwinGraphSchema'>
type ApiTwinNode = NonNullable<ApiTwinGraph['nodes']>[number]

const emptyCounts = (): SeverityCounts => ({ crit: 0, high: 0, med: 0, low: 0, unranked: 0 })

/** view-model severity -> the backend's bucket spelling */
export function bucketOf(sev: Finding['sev']): TwinSevBucket | 'unranked' {
  switch (sev) {
    case 'Critical':
      return 'crit'
    case 'High':
      return 'high'
    case 'Medium':
      return 'med'
    case 'Low':
      return 'low'
    default:
      return 'unranked'
  }
}

/** Total findings a node carries — exact from the server's counts, so the
 *  badge stays right even where the findings join was capped. */
export function countFindings(counts: SeverityCounts): number {
  return counts.crit + counts.high + counts.med + counts.low + counts.unranked
}

/** The worst severity a node carries, in the console's own ranking — the
 *  ring's colour. Zeros never win, so a clean node reads as clean. */
export function worstBucket(counts: SeverityCounts): TwinSevBucket | 'unranked' {
  for (const bucket of ['crit', 'high', 'med', 'low'] as const) {
    if (counts[bucket] > 0) return bucket
  }
  return 'unranked'
}

function countsFromApi(api: ApiTwinNode['severity_counts'], findings: Finding[]): SeverityCounts {
  if (!api) {
    // payload omitted the counts: derive from the joined findings
    return countsFromFindings(findings)
  }
  const counts = emptyCounts()
  for (const bucket of ['crit', 'high', 'med', 'low', 'unranked'] as const) {
    counts[bucket] = api[bucket] ?? 0
  }
  return counts
}

function countsFromFindings(findings: Finding[]): SeverityCounts {
  const counts = emptyCounts()
  for (const f of findings) counts[bucketOf(f.sev)] += 1
  return counts
}

function caseRef(c: CaseRow): TwinCaseRef {
  return { id: c.id, title: c.title, status: c.status, prio: c.prio }
}

/** Joins the served graph with the console's own rows: nodes get their
 *  findings (openable, so the popover can jump) and their cases. */
export function mapApiGraph(graph: ApiTwinGraph, findings: Finding[], cases: CaseRow[]): TwinGraphVM {
  const byFinding = new Map(findings.map((f) => [f.id, f]))
  const byCase = new Map(cases.map((c) => [c.id, c]))
  const nodes = (graph.nodes ?? []).map((n): TwinNodeVM => {
    const nodeFindings = (n.finding_ids ?? []).flatMap((id) => {
      const f = byFinding.get(id)
      return f ? [f] : []
    })
    const nodeCases = (n.case_ids ?? []).flatMap((id) => {
      const c = byCase.get(id)
      return c ? [caseRef(c)] : []
    })
    return {
      id: n.id,
      kind: n.kind,
      label: n.label,
      findings: nodeFindings,
      cases: nodeCases,
      severityCounts: countsFromApi(n.severity_counts, nodeFindings),
      position: n.x != null && n.y != null ? { x: n.x, y: n.y } : undefined,
    }
  })
  const edges = (graph.edges ?? []).map((e): TwinEdgeVM => ({
    id: e.id,
    source: e.source,
    target: e.target,
    kind: e.kind,
    weight: e.weight,
    findingIds: e.finding_ids ?? [],
  }))
  return { generatedAt: generatedLabel(graph.generated_at), nodes, edges }
}

// The footer shows when the map was drawn. Keep formatting in the view model
// (house pattern — mappers.ts) so the screen renders the string as-is.
function generatedLabel(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : format(d, 'MMM d, HH:mm:ss')
}

function findingMatchesFacets(f: Finding, filters: TwinFilters): boolean {
  if (filters.severity !== 'any' && bucketOf(f.sev) !== filters.severity) return false
  if (filters.status !== 'any' && f.status !== filters.status) return false
  if (filters.source !== 'any' && f.src !== filters.source) return false
  return true
}

function findingMatchesQuery(f: Finding, q: string): boolean {
  return (
    f.id.toLowerCase().includes(q) ||
    f.tech.toLowerCase().includes(q) ||
    (f.host !== DASH && f.host.toLowerCase().includes(q)) ||
    (f.user !== DASH && f.user.toLowerCase().includes(q)) ||
    (f.src !== DASH && f.src.toLowerCase().includes(q))
  )
}

export interface FilteredTwinGraph {
  nodes: TwinNodeVM[]
  edges: TwinEdgeVM[]
  /** distinct findings surviving the filters, across all visible nodes */
  matchedFindings: Finding[]
}

/** Client-side filtering over the whole served graph: a node stays when at
 *  least one of its findings survives the facet filters and the search —
 *  or when the search matches the node's own label (looking for a host by
 *  name shouldn't require its findings to mention that name). */
export function filterGraph(graph: TwinGraphVM, filters: TwinFilters): FilteredTwinGraph {
  const q = filters.query.trim().toLowerCase()
  const filtersActive = q !== '' || filters.severity !== 'any' || filters.status !== 'any' || filters.source !== 'any'
  const visible: TwinNodeVM[] = []
  const matched: Finding[] = []
  const seen = new Set<string>()
  for (const node of graph.nodes) {
    const passing = node.findings.filter(
      (f) =>
        findingMatchesFacets(f, filters) &&
        (q === '' || findingMatchesQuery(f, q) || node.label.toLowerCase().includes(q)),
    )
    for (const f of passing) {
      if (!seen.has(f.id)) {
        seen.add(f.id)
        matched.push(f)
      }
    }
    if (passing.length > 0) {
      // under filters the ring describes what is shown; unfiltered, the
      // server's counts stay exact even where the findings join was capped
      visible.push({
        ...node,
        findings: passing,
        severityCounts: filtersActive ? countsFromFindings(passing) : node.severityCounts,
      })
    }
  }
  const ids = new Set(visible.map((n) => n.id))
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  return { nodes: visible, edges, matchedFindings: matched }
}

/** Severity mix over distinct findings — the KPI donut's segments. */
export function severityTotals(findings: Finding[]): SeverityCounts {
  return countsFromFindings(findings)
}

/** Positions are stable across polls: a node the map already placed keeps
 *  its place (dragged or not) — only new ids take the served position, or
 *  the deterministic fallback when the payload has none. */
export function resolvePositions(
  nodes: TwinNodeVM[],
  previous: Map<string, { x: number; y: number }>,
): TwinNodeVM[] {
  return nodes.map((node, i) => {
    const kept = previous.get(node.id)
    if (kept) return { ...node, position: kept }
    if (node.position) return node
    return { ...node, position: fallbackPosition(i) }
  })
}

/** deterministic fallback for a payload without layout: a loose spiral */
function fallbackPosition(i: number): { x: number; y: number } {
  const ring = Math.floor(i / 8)
  const step = (Math.PI * 2) / 8
  const angle = (i % 8) * step + ring * (step / 2)
  const radius = 160 + ring * 140
  return { x: Math.round(Math.cos(angle) * radius), y: Math.round(Math.sin(angle) * radius) }
}

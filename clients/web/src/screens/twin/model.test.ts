import { describe, expect, it } from 'vitest'
import type { CaseRow, Finding } from '../../data/data'
import type { Schema } from '../../services/apiTypes'
import {
  ANY_TWIN_FILTERS,
  bucketOf,
  countFindings,
  filterGraph,
  mapApiGraph,
  resolvePositions,
  severityTotals,
  worstBucket,
  type TwinNodeVM,
} from './model'

const finding = (over: Partial<Finding> & { id: string }): Finding => ({
  sev: 'High',
  tech: 'T1059',
  conf: 80,
  tactic: 'Execution',
  src: 'crowdstrike',
  host: '—',
  user: '—',
  time: 'Oct 9, 12:00',
  score: 7,
  status: 'open',
  ...over,
})

type ApiGraph = Schema<'TwinGraphSchema'>

type ApiNode = NonNullable<ApiGraph['nodes']>[number]

// Fixture builder: required identity fields get explicit defaults so the
// result is a full node without a cast, with every other field overridable.
const apiNode = (over: Partial<ApiNode>): ApiNode => ({
  ...over,
  id: over.id ?? 'host:web-01',
  kind: over.kind ?? 'host',
  label: over.label ?? 'web-01',
})

const apiGraph = (): ApiGraph => ({
  generated_at: '2026-10-09T12:00:00+00:00',
  nodes: [
    apiNode({
      id: 'host:web-01',
      kind: 'host',
      label: 'web-01',
      finding_ids: ['f-1'],
      case_ids: ['c-1'],
      severity_counts: { crit: 1, high: 0, med: 0, low: 0, unranked: 0 },
      x: 10,
      y: 20,
    }),
    apiNode({
      id: 'ip:10.0.0.5',
      kind: 'ip',
      label: '10.0.0.5',
      finding_ids: ['f-1', 'f-2'],
      severity_counts: { crit: 0, high: 1, med: 1, low: 0, unranked: 0 },
    }),
    apiNode({ id: 'user:j.vanlowe', kind: 'user', label: 'j.vanlowe', finding_ids: ['f-3'] }),
  ],
  edges: [
    {
      id: 'flow:host:web-01-ip:10.0.0.5',
      source: 'host:web-01',
      target: 'ip:10.0.0.5',
      kind: 'flow',
      weight: 1,
      finding_ids: ['f-1'],
    },
  ],
})

const findings = (): Finding[] => [
  finding({ id: 'f-1', sev: 'Critical', tech: 'T1486', src: 'crowdstrike', host: 'web-01' }),
  finding({ id: 'f-2', sev: 'Medium', status: 'closed', src: 'splunk' }),
  finding({ id: 'f-3', sev: 'Unrated', tech: '—', src: 'osquery', user: 'j.vanlowe' }),
]

const cases = (): CaseRow[] => [
  {
    id: 'c-1',
    title: 'Ransomware dry run',
    status: 'investigating',
    prio: 'high',
    owner: 'analyst-1',
    ownerName: 'Analyst One',
    findings: 1,
    tactic: 'Impact',
    age: '2h',
    sla: '4h left',
    slaState: 'ok',
    updated: 'Oct 9, 11:00',
  },
]

const mapped = (graph: ApiGraph = apiGraph(), fs: Finding[] = findings(), cs: Parameters<typeof mapApiGraph>[2] = cases()) =>
  mapApiGraph(graph, fs, cs)

describe('mapApiGraph', () => {
  it('joins findings and cases onto nodes and keeps the served counts and layout', () => {
    const vm = mapped()
    expect(vm.nodes).toHaveLength(3)

    const web = vm.nodes[0]
    expect(web.id).toBe('host:web-01')
    expect(web.findings.map((f) => f.id)).toEqual(['f-1'])
    expect(web.cases.map((c) => c.id)).toEqual(['c-1'])
    expect(web.severityCounts).toEqual({ crit: 1, high: 0, med: 0, low: 0, unranked: 0 })
    expect(web.position).toEqual({ x: 10, y: 20 })

    // the edge rides along unchanged
    expect(vm.edges).toHaveLength(1)
    expect(vm.edges[0].kind).toBe('flow')

    // the footer stamp is formatted for display in the view model
    expect(vm.generatedAt).toBe('Oct 9, 12:00:00')
  })

  it('derives counts from the joined findings when the payload omits them', () => {
    const vm = mapped(apiGraph(), findings(), [])
    const user = vm.nodes.find((n) => n.id === 'user:j.vanlowe')
    expect(user?.severityCounts).toEqual({ crit: 0, high: 0, med: 0, low: 0, unranked: 1 })
  })

  it('drops ids that did not survive the join and leaves position absent without x/y', () => {
    const graph = apiGraph()
    graph.nodes = [apiNode({ id: 'host:ghost', kind: 'host', label: 'ghost', finding_ids: ['f-gone'], x: null, y: null })]
    const vm = mapApiGraph(graph, findings(), [])
    const ghost = vm.nodes[0]
    expect(ghost.findings).toEqual([])
    expect(ghost.position).toBeUndefined()
  })
})

describe('filterGraph', () => {
  const vm = mapped()

  it('keeps only nodes with a surviving finding and prunes orphaned edges', () => {
    const out = filterGraph(vm, { ...ANY_TWIN_FILTERS, severity: 'crit' })
    expect(out.nodes.map((n) => n.id)).toEqual(['host:web-01', 'ip:10.0.0.5'])
    expect(out.edges.map((e) => e.id)).toEqual(['flow:host:web-01-ip:10.0.0.5'])
    expect(out.matchedFindings.map((f) => f.id)).toEqual(['f-1'])
  })

  it('recomputes ring counts from what is shown while filters are active', () => {
    const out = filterGraph(vm, { ...ANY_TWIN_FILTERS, severity: 'crit' })
    expect(out.nodes.find((n) => n.id === 'ip:10.0.0.5')?.severityCounts).toEqual({
      crit: 1, high: 0, med: 0, low: 0, unranked: 0,
    })
  })

  it('keeps the server counts when nothing is filtered', () => {
    const out = filterGraph(vm, ANY_TWIN_FILTERS)
    expect(out.nodes.find((n) => n.id === 'ip:10.0.0.5')?.severityCounts).toEqual({
      crit: 0, high: 1, med: 1, low: 0, unranked: 0,
    })
  })

  it('matches a node by label search even when its findings do not mention it', () => {
    const out = filterGraph(vm, { ...ANY_TWIN_FILTERS, query: 'web-01' })
    const web = out.nodes.find((n) => n.id === 'host:web-01')
    expect(web).toBeDefined()
    // label matches: the node's facet-passing findings stay pinned to it
    expect(web?.findings.map((f) => f.id)).toEqual(['f-1'])
  })

  it('filters by status and source facets', () => {
    const closed = filterGraph(vm, { ...ANY_TWIN_FILTERS, status: 'closed' })
    expect(closed.matchedFindings.map((f) => f.id)).toEqual(['f-2'])

    const splunk = filterGraph(vm, { ...ANY_TWIN_FILTERS, source: 'splunk' })
    expect(splunk.matchedFindings.map((f) => f.id)).toEqual(['f-2'])
  })

  it('counts a finding shared by two nodes once', () => {
    const out = filterGraph(vm, ANY_TWIN_FILTERS)
    // f-1 sits on both web-01 and the ip node; distinct totals keep the KPI honest
    expect(new Set(out.matchedFindings.map((f) => f.id)).size).toBe(out.matchedFindings.length)
  })
})

describe('resolvePositions', () => {
  const placed = (id: string, x: number, y: number): TwinNodeVM => ({
    id,
    kind: 'host',
    label: id,
    findings: [],
    cases: [],
    severityCounts: { crit: 0, high: 0, med: 0, low: 0, unranked: 0 },
    position: { x, y },
  })

  it('keeps the previous position of a known node over the served layout', () => {
    const previous = new Map([['host:a', { x: 1, y: 2 }]])
    const [a] = resolvePositions([placed('host:a', 99, 99)], previous)
    expect(a.position).toEqual({ x: 1, y: 2 })
  })

  it('takes the served position for a new node and falls back when it has none', () => {
    const [b, c] = resolvePositions([placed('host:b', 5, 6), { ...placed('host:c', 0, 0), position: undefined }], new Map())
    expect(b.position).toEqual({ x: 5, y: 6 })
    expect(c.position).toBeDefined()
  })
})

describe('severity helpers', () => {
  it('buckets severities into the console ranking', () => {
    expect(bucketOf('Critical')).toBe('crit')
    expect(bucketOf('Unrated')).toBe('unranked')
  })

  it('sums counts and picks the worst bucket without letting zeros win', () => {
    const counts = { crit: 0, high: 2, med: 0, low: 0, unranked: 1 }
    expect(countFindings(counts)).toBe(3)
    expect(worstBucket(counts)).toBe('high')
    expect(worstBucket({ crit: 0, high: 0, med: 0, low: 0, unranked: 4 })).toBe('unranked')
  })

  it('totals severity across distinct findings', () => {
    const totals = severityTotals(findings())
    expect(totals).toEqual({ crit: 1, high: 0, med: 1, low: 0, unranked: 1 })
  })
})

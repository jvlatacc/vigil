import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { casesApi, findingsApi, twinApi } from '../../services/api'
import type { Schema } from '../../services/apiTypes'
import { useTwinGraph } from './useTwinGraph'

vi.mock('../../services/api', () => ({
  twinApi: { getGraph: vi.fn() },
  findingsApi: { getAll: vi.fn() },
  casesApi: { getAll: vi.fn() },
}))

const apiGraph = (): Schema<'TwinGraphSchema'> => ({
  generated_at: '2026-10-09T12:00:00+00:00',
  nodes: [
    { id: 'host:web-01', kind: 'host', label: 'web-01', finding_ids: ['f-1'], case_ids: ['c-1'] },
  ],
  edges: [],
})

const apiFinding = {
  finding_id: 'f-1',
  title: 'Beaconing observed',
  severity: 'critical',
  status: 'open',
  data_source: 'crowdstrike',
  entity_context: { hostnames: ['web-01'] },
  timestamp: '2026-10-09T11:00:00+00:00',
}

const apiCase = {
  case_id: 'c-1',
  title: 'Ransomware dry run',
  status: 'investigating',
  priority: 'high',
  age_seconds: 7200,
  comment_count: 0,
}

function mockOk() {
  vi.mocked(twinApi.getGraph).mockResolvedValue({ data: apiGraph() } as never)
  vi.mocked(findingsApi.getAll).mockResolvedValue({ data: { findings: [apiFinding] } } as never)
  vi.mocked(casesApi.getAll).mockResolvedValue({ data: { cases: [apiCase] } } as never)
}

const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0) })

describe('useTwinGraph', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => vi.useRealTimers())

  it('loads the graph with its findings and cases joined, and lands ready', async () => {
    mockOk()
    const { result } = renderHook(() => useTwinGraph())

    await flush()

    expect(result.current.phase).toBe('ready')
    expect(result.current.graph?.nodes[0].label).toBe('web-01')
    expect(result.current.graph?.nodes[0].findings[0].id).toBe('f-1')
    expect(result.current.graph?.nodes[0].cases[0].id).toBe('c-1')
    // the graph already honours exclusions server-side, so the join asks
    // for every finding a surviving node can name
    expect(vi.mocked(findingsApi.getAll)).toHaveBeenCalledWith({ limit: 1000, exclusions: 'include' })
  })

  it('lands in the error phase when the first load fails', async () => {
    vi.mocked(twinApi.getGraph).mockRejectedValue(new Error('down'))
    const { result } = renderHook(() => useTwinGraph())

    await flush()

    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('down')
    expect(result.current.graph).toBeNull()
  })

  it('keeps the last valid map when a background refresh fails', async () => {
    mockOk()
    const { result } = renderHook(() => useTwinGraph())
    await flush()
    const held = result.current.graph

    vi.mocked(twinApi.getGraph).mockRejectedValue(new Error('flaky'))
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })

    expect(result.current.phase).toBe('ready')
    expect(result.current.error).toBe('flaky')
    // the canvas never blanks: the previous map is still on offer
    expect(result.current.graph).toBe(held)
  })

  it('polls every ten seconds', async () => {
    mockOk()
    renderHook(() => useTwinGraph())
    await flush()
    expect(vi.mocked(twinApi.getGraph)).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(vi.mocked(twinApi.getGraph)).toHaveBeenCalledTimes(2)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(vi.mocked(twinApi.getGraph)).toHaveBeenCalledTimes(3)
  })

  it('recovers through reload after a failed first load', async () => {
    vi.mocked(twinApi.getGraph).mockRejectedValueOnce(new Error('down'))
    mockOk()
    const { result } = renderHook(() => useTwinGraph())
    await flush()
    expect(result.current.phase).toBe('error')

    act(() => result.current.reload())
    await flush()

    expect(result.current.phase).toBe('ready')
    expect(result.current.error).toBeNull()
  })
})

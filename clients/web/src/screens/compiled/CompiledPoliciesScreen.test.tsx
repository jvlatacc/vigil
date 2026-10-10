// Component tests for the Compiled Policies screen: the lifecycle round-trips
// (promote, hash-guard refusal), the agreement counters and KPI, state
// filtering, and the export download.
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import CompiledPoliciesScreen from './CompiledPoliciesScreen'
import { compiledPoliciesApi, type CompiledPolicySummary, type PolicyDecisionsPage } from '../../services/api'

vi.mock('../../services/api', () => ({
  compiledPoliciesApi: {
    list: vi.fn(),
    get: vi.fn(),
    decisions: vi.fn(),
    transition: vi.fn(),
    export: vi.fn(),
  },
}))

const listMock = vi.mocked(compiledPoliciesApi.list)
const decisionsMock = vi.mocked(compiledPoliciesApi.decisions)
const transitionMock = vi.mocked(compiledPoliciesApi.transition)
const exportMock = vi.mocked(compiledPoliciesApi.export)

/** a minimal AxiosResponse so mockResolvedValue satisfies the client types */
const axiosOf = <T,>(data: T) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as never,
})

const HASH = 'sha256:9f2c1a4b7d6e5c3a2b1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b'

function policy(over: Partial<CompiledPolicySummary>): CompiledPolicySummary {
  return {
    policy_id: 'pol_cred_01',
    version: 3,
    state: 'shadow',
    content_hash: HASH,
    compiled_at: '2026-10-09T20:00:00Z',
    compiled_by: 'maturity-job',
    match: {
      workflow_id: 'wf_hunt_cred_stuffing',
      data_source: ['okta.system_log'],
      techniques: { any_of: ['T1110.003'] },
    },
    decision: {
      severity: 'high',
      confidence: 0.93,
      recommended_action: 'investigate',
      category: 'credential_stuffing',
      reasoning: 'Compiled from 15 completed runs.',
      actions_human_only: true,
    },
    maturity: {
      workflow_id: 'wf_hunt_cred_stuffing',
      window_days: 30,
      outcomes: { resolved: 14, false_positive: 1 },
      consistency: 0.93,
      analyst_overrides: 0,
    },
    renders: {},
    lifecycle: {
      promoted_by: null,
      promoted_at: null,
      suspended_by: null,
      suspended_at: null,
      rearmed_by: null,
      rearmed_at: null,
      retired_by: null,
      retired_at: null,
    },
    ...over,
  }
}

function decisionsPage(over: Partial<PolicyDecisionsPage> = {}): PolicyDecisionsPage {
  return {
    policy_id: 'pol_cred_01',
    version: null,
    total: 3,
    agreement: {
      by_mode: { shadow: 2, active: 1 },
      llm: { agrees: 1, disagrees: 1 },
      analyst: { agrees: 1, disagrees: 0 },
      pending: 0,
    },
    decisions: [
      {
        id: 7,
        finding_id: 'f_007',
        policy_id: 'pol_cred_01',
        policy_version: 3,
        content_hash: HASH,
        mode: 'active',
        outcome: 'applied',
        decision: { severity: 'high' },
        actual_decision: null,
        agreement_source: null,
        agrees: null,
        evaluation_us: 180,
        evaluated_at: '2026-10-09T21:00:00Z',
      },
      {
        id: 6,
        finding_id: 'f_006',
        policy_id: 'pol_cred_01',
        policy_version: 3,
        content_hash: HASH,
        mode: 'shadow',
        outcome: 'shadow_observed',
        decision: { severity: 'high' },
        actual_decision: { severity: 'low' },
        agreement_source: 'llm',
        agrees: false,
        evaluation_us: 150,
        evaluated_at: '2026-10-09T20:30:00Z',
      },
      {
        id: 5,
        finding_id: 'f_005',
        policy_id: 'pol_cred_01',
        policy_version: 2,
        content_hash: 'sha256:older',
        mode: 'active',
        outcome: 'applied',
        decision: { severity: 'high' },
        actual_decision: { severity: 'high' },
        agreement_source: 'analyst',
        agrees: true,
        evaluation_us: 120,
        evaluated_at: '2026-10-09T20:15:00Z',
      },
    ],
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  listMock.mockResolvedValue(axiosOf({ policies: [policy({})], total: 1 }))
  decisionsMock.mockResolvedValue(axiosOf(decisionsPage()))
})

async function openScreen() {
  const { container } = render(<CompiledPoliciesScreen />)
  await waitFor(() =>
    expect(container.querySelector('[data-policy-id="pol_cred_01"]')).toBeInTheDocument()
  )
  return container.querySelector('[data-policy-id="pol_cred_01"]') as HTMLElement
}

describe('CompiledPoliciesScreen', () => {
  it('renders the empty state when no policies exist yet', async () => {
    listMock.mockResolvedValue(axiosOf({ policies: [], total: 0 }))
    render(<CompiledPoliciesScreen />)
    expect(await screen.findByText('No compiled policies yet')).toBeInTheDocument()
    expect(listMock).toHaveBeenCalledWith(undefined)
  })

  it('shows provenance — state, version, content hash, maturity — for each policy', async () => {
    const card = await openScreen()
    expect(screen.getByText('v3')).toBeInTheDocument()
    expect(screen.getByTitle(HASH)).toHaveTextContent('9f2c1a4b7d6e…')
    expect(screen.getByText(/15 runs in 30d/)).toBeInTheDocument()
    expect(screen.getByText(/93% measured agreement/)).toBeInTheDocument()
    // a shadow policy offers promote, suspend and retire, never re-arm
    expect(within(card).getByRole('button', { name: 'Promote to active' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Suspend' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Retire' })).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Re-arm to shadow' })).not.toBeInTheDocument()
  })

  it('filters by state through the API, not the client', async () => {
    await openScreen()
    fireEvent.click(screen.getByRole('tab', { name: 'active' }))
    await waitFor(() => expect(listMock).toHaveBeenLastCalledWith('active'))
  })

  it('promotes from shadow only after a dialog confirms the version and hash', async () => {
    transitionMock.mockResolvedValue(
      axiosOf({
        transition: { action: 'promote', actor: 'ops', from_state: 'shadow', to_state: 'active', content_hash: HASH },
        policy: policy({ state: 'active' }),
      })
    )
    const card = await openScreen()

    fireEvent.click(within(card).getByRole('button', { name: 'Promote to active' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent(HASH)
    expect(dialog).toHaveTextContent('shadow → active')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Promote to active' }))
    await waitFor(() =>
      expect(transitionMock).toHaveBeenCalledWith('pol_cred_01', 'promote', { version: 3, content_hash: HASH })
    )
    // and the list reloads to show the new state
    await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('surfaces the hash-guard 409 and reloads the row that actually won', async () => {
    transitionMock.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail:
            'expected content hash sha256:9f2c… does not match the current row (recompiled as version 4)',
        },
      },
    })
    const card = await openScreen()

    fireEvent.click(within(card).getByRole('button', { name: 'Promote to active' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Promote to active' }))

    const banner = await screen.findByRole('alert')
    expect(banner).toHaveTextContent('does not match the current row')
    await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('renders the decision log with agreement counters and the avoided-calls KPI', async () => {
    await openScreen()
    fireEvent.click(screen.getByRole('button', { name: /Show decision log/ }))

    // the counters render figures inside <strong>; assert each span's full text
    const avoided = await screen.findByText(/LLM triage calls avoided/)
    expect(avoided.textContent).toBe('2 LLM triage calls avoided')
    expect(screen.getByText(/evaluations logged/).textContent).toBe('3 evaluations logged')
    // the avg-evaluation KPI is 150 µs (mean of 180 and 120 over the applied
    // hits); the same figure also appears in table cells, so scope by the label
    expect(screen.getByText(/avg evaluation/).textContent).toContain('150 µs')
    expect(screen.getByText(/pending agreement/).textContent).toContain('0 pending agreement')
    expect(screen.getByText(/LLM:/).textContent).toBe('LLM: 1 agree / 1 disagree')
    expect(screen.getByText(/Analyst:/).textContent).toBe('Analyst: 1 agree / 0 disagree')
    expect(screen.getByText('f_006')).toBeInTheDocument()
  })

  it('downloads a rendered export and reports the call', async () => {
    exportMock.mockResolvedValue({
      blob: new Blob(['package vigil'], { type: 'text/plain' }),
      filename: 'pol_cred_01-v3.rego',
      sha256: 'sha256:feed',
    })
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', { value: vi.fn(), configurable: true })

    const card = await openScreen()
    fireEvent.click(within(card).getByRole('button', { name: 'Export' }))
    fireEvent.click(await screen.findByRole('button', { name: /OPA Rego/ }))

    await waitFor(() => expect(exportMock).toHaveBeenCalledWith('pol_cred_01', 'rego', 3))
    expect(createObjectURL).toHaveBeenCalled()
  })

  it('offers no lifecycle buttons on a retired policy', async () => {
    listMock.mockResolvedValue(axiosOf({ policies: [policy({ state: 'retired' })], total: 1 }))
    render(<CompiledPoliciesScreen />)
    const card = await waitFor(() => {
      const el = document.querySelector('[data-policy-id="pol_cred_01"]') as HTMLElement | null
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    expect(within(card).queryByRole('button', { name: 'Promote to active' })).not.toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Export' })).toBeInTheDocument()
  })
})

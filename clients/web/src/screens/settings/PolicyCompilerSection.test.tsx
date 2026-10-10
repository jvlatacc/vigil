// Tests for the Policy Compiler settings section: the fast-path flag renders
// from the intent report (read-only), and the maturity tunables round-trip
// through the AI operations settings endpoint.
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import PolicyCompilerSection from './PolicyCompilerSection'
import { configApi } from '../../services/api'

const notify = vi.fn()

vi.mock('../../services/api', () => ({
  configApi: {
    getIntent: vi.fn(),
    getAIOperations: vi.fn(),
    setAIOperations: vi.fn(),
  },
}))

const intentMock = vi.mocked(configApi.getIntent)
const getOpsMock = vi.mocked(configApi.getAIOperations)
const setOpsMock = vi.mocked(configApi.setAIOperations)

/** a minimal AxiosResponse so mockResolvedValue satisfies the client types */
const axiosOf = <T,>(data: T) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as never,
})

beforeEach(() => {
  vi.clearAllMocks()
  intentMock.mockResolvedValue(axiosOf({
    rows: [{ key: 'triage.jit_fast_path_enabled', declared: true, effective: false, source: 'env' }],
  }))
  getOpsMock.mockResolvedValue(axiosOf({
    policy_compiler_min_runs: 10,
    policy_compiler_min_consistency: 0.9,
    policy_compiler_window_days: 30,
    policy_compiler_drift_limit: 3,
  }))
  setOpsMock.mockResolvedValue(axiosOf({}))
})

describe('PolicyCompilerSection', () => {
  it('shows the fast-path flag from the intent report as a disabled switch with its source', async () => {
    render(<PolicyCompilerSection notify={notify} />)
    // the intent report says declared=true, effective=false — the console shows
    // the effective state, disabled, because INTENT.md plus a daemon restart
    // governs the flag
    const flag = await screen.findByRole('switch', { name: 'Fast path enabled' })
    expect(flag).toBeDisabled()
    expect(flag).toHaveAttribute('aria-checked', 'false')
    const note = await screen.findByText(/Effective value: disabled \(env\)/)
    expect(note).toHaveTextContent('declared in INTENT.md')
  })

  it('loads the four maturity tunables with their defaults', async () => {
    render(<PolicyCompilerSection notify={notify} />)
    const minRuns = (await screen.findByLabelText(/Minimum resolved runs/)) as HTMLInputElement
    expect(minRuns.value).toBe('10')
    expect((screen.getByLabelText(/Minimum consistency/) as HTMLInputElement).value).toBe('0.9')
    expect((screen.getByLabelText(/Evidence window \(days\)/) as HTMLInputElement).value).toBe('30')
    expect((screen.getByLabelText(/Drift limit/) as HTMLInputElement).value).toBe('3')
  })

  it('saves an edited tunable through the settings endpoint', async () => {
    render(<PolicyCompilerSection notify={notify} />)
    const minRuns = (await screen.findByLabelText(/Minimum resolved runs/)) as HTMLInputElement
    fireEvent.change(minRuns, { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save thresholds' }))
    await waitFor(() =>
      expect(setOpsMock).toHaveBeenCalledWith(expect.objectContaining({ policy_compiler_min_runs: 25 }))
    )
  })

  it('disables save and flags out-of-range input', async () => {
    render(<PolicyCompilerSection notify={notify} />)
    const minRuns = (await screen.findByLabelText(/Minimum resolved runs/)) as HTMLInputElement
    fireEvent.change(minRuns, { target: { value: '9999' } })
    expect(screen.getByRole('button', { name: 'Save thresholds' })).toBeDisabled()
    expect(screen.getByText(/outside the allowed range/)).toBeInTheDocument()
    expect(setOpsMock).not.toHaveBeenCalled()
  })
})

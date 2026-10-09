import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import DeceptionSection from './DeceptionSection'

const api = vi.hoisted(() => ({
  getStatus: vi.fn(),
  getLeases: vi.fn(),
  releaseLease: vi.fn(),
  setKillSwitch: vi.fn(),
  updateSettings: vi.fn(),
  getProbes: vi.fn(),
}))
vi.mock('../../services/api', () => ({ deceptionApi: api }))

const STATUS = {
  enabled: false,
  backend: 'dry_run',
  backend_error: null,
  honey_route_floor: 0.8,
  ttl_seconds: 3600,
  max_duration_seconds: 86400,
  min_observations: 3,
  window_seconds: 3600,
  kill_switch_active: false,
  allowlist: '',
  lease_counts: {},
}

const notify = vi.fn()
const renderSection = () => render(<DeceptionSection notify={notify} />)

beforeEach(() => {
  vi.clearAllMocks()
  // fresh object per call: the section re-seeds its form when the status
  // reference changes, so a stable mock instance would freeze the form dirty
  api.getStatus.mockImplementation(() => Promise.resolve({ data: { ...STATUS } }))
  api.updateSettings.mockResolvedValue({})
  api.setKillSwitch.mockResolvedValue({})
})

describe('DeceptionSection', () => {
  it('loading', () => {
    api.getStatus.mockReturnValue(new Promise(() => {}))
    renderSection()
    expect(screen.getByText('Loading the deception posture…')).toBeInTheDocument()
  })

  it('error offers Retry, which reloads', async () => {
    api.getStatus.mockRejectedValueOnce(new Error('boom'))
    renderSection()
    expect(await screen.findByText(/Couldn’t load the deception posture: boom/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Decision and lease bounds')).toBeInTheDocument()
  })

  it('ready: dry-run banner, resolved bounds, kill switch off, nothing dirty', async () => {
    renderSection()
    expect(await screen.findByText(/Dry run — every steer is recorded as intent only/)).toBeInTheDocument()
    expect(screen.getByText(/Honey-route confidence floor \(0\.8\)/)).toBeInTheDocument()
    expect(screen.getByText(/Lease TTL \(1h\)/)).toBeInTheDocument()
    expect(screen.getByText(/Kill switch is off/)).toBeInTheDocument()
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('enabling the posture marks the form dirty and saves the whole resolved set', async () => {
    renderSection()
    fireEvent.click(await screen.findByRole('switch', { name: 'Enable the deception posture' }))
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1))
    expect(api.updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true, backend: 'dry_run', honey_route_floor: 0.8 }),
    )
    // the re-read after save renders what the daemon will read
    expect(notify).toHaveBeenCalledWith('ok', expect.stringContaining('saved'))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('a validation refusal surfaces the API detail', async () => {
    api.updateSettings.mockRejectedValueOnce({
      response: { data: { detail: 'Unparseable allowlist entries: scannerbox' } },
    })
    renderSection()
    fireEvent.click(await screen.findByRole('switch', { name: 'Enable the deception posture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/Unparseable allowlist entries/)).toBeInTheDocument()
    expect(notify).toHaveBeenCalledWith('err', expect.stringContaining('Unparseable'))
  })

  it('engages the kill switch through the confirm dialog', async () => {
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: 'Engage kill switch' }))
    expect(screen.getByText('Engage the kill switch?')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Reason (recorded in the audit trail)'), {
      target: { value: 'drill' },
    })
    const buttons = screen.getAllByRole('button', { name: 'Engage' })
    fireEvent.click(buttons[buttons.length - 1]) // the dialog's confirm, rendered last
    await waitFor(() => expect(api.setKillSwitch).toHaveBeenCalledWith(true, 'drill'))
    expect(notify).toHaveBeenCalledWith('ok', 'Kill switch engaged.')
  })
})

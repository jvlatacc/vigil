import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import DeceptionScreen from './DeceptionScreen'
import { fmtCountdown } from './fmt'

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
  lease_counts: { active: 1, released: 0, failed: 0, expired: 0 },
}

const ACTIVE_LEASE = {
  lease_id: 'lease-1',
  attacker_ip: '203.0.113.7',
  action_id: 'action-1',
  destination_ips: ['10.0.4.25'],
  ports: [445, 3389],
  status: 'active',
  backend: 'dry_run',
  backend_ref: 'dry:lease-1',
  ttl_seconds: 3600,
  started_at: '2026-10-09T10:00:00+00:00',
  expires_at: new Date(Date.now() + 3600_000).toISOString(),
  renewal_count: 0,
  released_at: null,
  release_reason: null,
  rollback_result: null,
  created_at: '2026-10-09T10:00:00+00:00',
}

const RELEASED_LEASE = {
  ...ACTIVE_LEASE,
  lease_id: 'lease-2',
  attacker_ip: '198.51.100.9',
  status: 'released',
  released_at: '2026-10-09T11:00:00+00:00',
  release_reason: 'ttl expired',
  rollback_result: { success: true },
  expires_at: '2026-10-09T11:00:00+00:00',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getStatus.mockResolvedValue({ data: { ...STATUS, lease_counts: { active: 1 } } })
  api.getLeases.mockResolvedValue({ data: { leases: [ACTIVE_LEASE] } })
  api.getProbes.mockResolvedValue({ data: { probes: [] } })
  api.releaseLease.mockResolvedValue({})
  api.setKillSwitch.mockResolvedValue({})
})

const renderScreen = () => render(<DeceptionScreen />)

describe('DeceptionScreen', () => {
  it('loading', () => {
    api.getStatus.mockReturnValue(new Promise(() => {}))
    renderScreen()
    expect(screen.getByText('Loading the deception posture…')).toBeInTheDocument()
  })

  it('error offers Retry, which reloads', async () => {
    api.getStatus.mockRejectedValueOnce(new Error('boom'))
    renderScreen()
    expect(await screen.findByText(/Couldn't load the deception posture/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('203.0.113.7')).toBeInTheDocument()
  })

  it('empty: nothing steered, dry-run indicator shown, kill switch off', async () => {
    api.getLeases.mockResolvedValue({ data: { leases: [] } })
    renderScreen()
    expect(await screen.findByText('No leases — nothing is steered.')).toBeInTheDocument()
    expect(screen.getByText('Dry run — records intent only')).toBeInTheDocument()
    expect(screen.getByText('Kill switch off')).toBeInTheDocument()
    expect(screen.getByText('0 active leases')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Engage kill switch/ })).toBeInTheDocument()
  })

  it('active lease row: decoys, ports, live countdown, and the dry-run backend ref', async () => {
    renderScreen()
    const row = (await screen.findByText('203.0.113.7')).closest('tr')!
    expect(row).toHaveTextContent('10.0.4.25')
    expect(row).toHaveTextContent('445, 3389')
    expect(row).toHaveTextContent(/left/)
    expect(row).toHaveTextContent('dry:lease-1')
    expect(row).toHaveTextContent('active')
  })

  it('releases a lease through the confirm dialog', async () => {
    renderScreen()
    const row = (await screen.findByText('203.0.113.7')).closest('tr')!
    fireEvent.click(within(row).getByRole('button', { name: 'Release the lease for 203.0.113.7' }))
    expect(await screen.findByText('Release the lease for 203.0.113.7?')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Reason (recorded in the audit trail)'), {
      target: { value: 'false positive' },
    })
    const buttons = screen.getAllByRole('button', { name: 'Release' })
    fireEvent.click(buttons[buttons.length - 1]) // the dialog's confirm, rendered last
    await waitFor(() =>
      expect(api.releaseLease).toHaveBeenCalledWith('lease-1', 'false positive'),
    )
  })

  it('engages the kill switch through the confirm dialog', async () => {
    renderScreen()
    await screen.findByText('203.0.113.7')
    fireEvent.click(screen.getByRole('button', { name: /Engage kill switch/ }))
    expect(screen.getByText('Engage the kill switch?')).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: 'Engage' })
    fireEvent.click(buttons[buttons.length - 1])
    await waitFor(() => expect(api.setKillSwitch).toHaveBeenCalledWith(true, undefined))
  })

  it('engaged kill switch: chip and release affordance', async () => {
    api.getStatus.mockResolvedValue({
      data: { ...STATUS, kill_switch_active: true },
    })
    renderScreen()
    expect(await screen.findByText('Kill switch engaged')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Release kill switch' })).toBeInTheDocument()
  })

  it('captured intel: probes link the lease source to findings', async () => {
    api.getProbes.mockResolvedValue({
      data: {
        probes: [
          {
            probe_id: 'probe-1',
            source_ip: '203.0.113.7',
            finding_id: 'f-77',
            evidence: { tids: ['T1046'], ports: [445] },
            created_at: '2026-10-09T10:01:00+00:00',
          },
        ],
      },
    })
    renderScreen()
    // no source picked: the panel shows the most recent probes across sources
    const row = await screen.findByText('f-77').then((el) => el.closest('tr')!)
    expect(row).toHaveTextContent('203.0.113.7')
    expect(row).toHaveTextContent('T1046')
  })

  it('terminal leases show the rollback result', async () => {
    api.getLeases.mockResolvedValue({ data: { leases: [ACTIVE_LEASE, RELEASED_LEASE] } })
    renderScreen()
    expect(await screen.findByText('Recent released and failed leases')).toBeInTheDocument()
    const row = screen.getByText('198.51.100.9').closest('tr')!
    expect(row).toHaveTextContent('unsteered')
    expect(row).toHaveTextContent('ttl expired')
  })
})

describe('fmtCountdown', () => {
  it('formats hours, minutes, and expiry', () => {
    const now = Date.now()
    expect(fmtCountdown(new Date(now + 3600_000).toISOString(), now)).toBe('1h 0m left')
    expect(fmtCountdown(new Date(now + 90_000).toISOString(), now)).toBe('1m 30s left')
    expect(fmtCountdown(new Date(now - 1000).toISOString(), now)).toBe('expired')
    expect(fmtCountdown(null, now)).toBe('—')
  })
})

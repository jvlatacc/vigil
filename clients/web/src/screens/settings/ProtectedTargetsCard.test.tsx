import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ProtectedTargetsCard from './ProtectedTargetsCard'
import { configApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  configApi: {
    getProtectedTargets: vi.fn(),
    addProtectedTarget: vi.fn(),
    removeProtectedTarget: vi.fn(),
  },
}))

const notify = vi.fn()

const floorAndOperator = {
  targets: [
    {
      kind: 'ip',
      value: '10.0.0.5',
      origin: 'env',
      reason: 'the floor',
      created_by: 'environment',
      removable: false,
    },
    {
      kind: 'cidr',
      value: '10.60.0.0/16',
      origin: 'operator',
      reason: 'the SCADA ring',
      created_by: 'user-1',
      removable: true,
    },
  ],
  unparsed: [],
}

const merged = (targets: unknown[], unparsed: string[] = []) => ({
  data: { targets, unparsed },
})

describe('never-quarantine targets card', () => {
  beforeEach(() => {
    vi.mocked(configApi.getProtectedTargets).mockReset()
    vi.mocked(configApi.addProtectedTarget).mockReset()
    vi.mocked(configApi.removeProtectedTarget).mockReset()
    notify.mockReset()
  })

  it('renders the environment floor locked and operator rows removable', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(
      merged(floorAndOperator.targets) as never,
    )
    render(<ProtectedTargetsCard notify={notify} />)

    expect(await screen.findByText('10.0.0.5')).toBeInTheDocument()
    expect(screen.getByText('10.60.0.0/16')).toBeInTheDocument()
    // The floor is tagged, never offered a remove button; the operator row is.
    expect(screen.getAllByText('Environment')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1)
  })

  it('shows unparsed environment entries as containment-holding, not as silence', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(merged([], ['oops:zzz']) as never)
    render(<ProtectedTargetsCard notify={notify} />)

    expect(await screen.findByText(/did not parse/)).toBeInTheDocument()
    expect(screen.getByText('oops:zzz')).toBeInTheDocument()
  })

  it('refuses to save an entry without a value and a reason', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(merged([]) as never)
    render(<ProtectedTargetsCard notify={notify} />)
    await screen.findByText(/Nothing is protected yet/)

    fireEvent.click(screen.getByRole('button', { name: 'Protect' }))

    expect(
      await screen.findByText(/A value and a reason are both required/),
    ).toBeInTheDocument()
    expect(configApi.addProtectedTarget).not.toHaveBeenCalled()
  })

  it('saves an operator row and shows the merged view it returns', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(merged([]) as never)
    vi.mocked(configApi.addProtectedTarget).mockResolvedValue(
      merged([
        { kind: 'ip', value: '10.9.9.9', origin: 'operator', reason: 'domain controller', created_by: 'me', removable: true },
      ]) as never,
    )
    render(<ProtectedTargetsCard notify={notify} />)
    await screen.findByText(/Nothing is protected yet/)

    fireEvent.change(screen.getByPlaceholderText('10.0.0.5'), { target: { value: '10.9.9.9' } })
    fireEvent.change(screen.getByPlaceholderText('Why this target may never be contained'), {
      target: { value: 'domain controller' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Protect' }))

    await waitFor(() =>
      expect(configApi.addProtectedTarget).toHaveBeenCalledWith({
        kind: 'ip',
        value: '10.9.9.9',
        reason: 'domain controller',
      }),
    )
    expect(await screen.findByText('10.9.9.9')).toBeInTheDocument()
    expect(notify).toHaveBeenCalledWith('ok', 'Protected target saved.')
  })

  it('surfaces a refusal from the server instead of pretending it saved', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(merged([]) as never)
    vi.mocked(configApi.addProtectedTarget).mockRejectedValue({
      response: { data: { detail: 'The environment wins; the floor protects 10.0.0.5.' } },
    })
    render(<ProtectedTargetsCard notify={notify} />)
    await screen.findByText(/Nothing is protected yet/)

    fireEvent.change(screen.getByPlaceholderText('10.0.0.5'), { target: { value: '10.0.0.5' } })
    fireEvent.change(screen.getByPlaceholderText('Why this target may never be contained'), {
      target: { value: 'the floor, again' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Protect' }))

    expect(
      await screen.findByText('The environment wins; the floor protects 10.0.0.5.'),
    ).toBeInTheDocument()
    expect(notify).not.toHaveBeenCalled()
  })

  it('removes an operator row only after confirmation', async () => {
    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(
      merged(floorAndOperator.targets) as never,
    )
    vi.mocked(configApi.removeProtectedTarget).mockResolvedValue(merged([]) as never)
    render(<ProtectedTargetsCard notify={notify} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    expect(await screen.findByText('Stop protecting 10.60.0.0/16?')).toBeInTheDocument()

    // The dialog's confirm button; the row button shares the label.
    const removeButtons = screen.getAllByRole('button', { name: 'Remove' })
    fireEvent.click(removeButtons[removeButtons.length - 1])

    await waitFor(() =>
      expect(configApi.removeProtectedTarget).toHaveBeenCalledWith('cidr', '10.60.0.0/16'),
    )
    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(
        'ok',
        'The removal is recorded. The row keeps its history.',
      ),
    )
  })

  it('treats a failed read as an error with a retry, not an empty list', async () => {
    vi.mocked(configApi.getProtectedTargets).mockRejectedValue(new Error('down'))
    render(<ProtectedTargetsCard notify={notify} />)

    expect(
      await screen.findByText('Could not load the never-quarantine list. Nothing has been changed.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()

    vi.mocked(configApi.getProtectedTargets).mockResolvedValue(merged([]) as never)
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/Nothing is protected yet/)).toBeInTheDocument()
    expect(configApi.getProtectedTargets).toHaveBeenCalledTimes(2)
  })
})

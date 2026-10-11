import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import RoleMappingsSection from './RoleMappingsSection'

const api = vi.hoisted(() => ({
  get: vi.fn(),
}))
const roleMappingsApi = vi.hoisted(() => ({
  getAll: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}))
const hasPermission = vi.hoisted(() => vi.fn())

vi.mock('../../services/api', () => ({ api, roleMappingsApi, default: api }))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission }),
}))

const notify = vi.fn()

const ROLES = [
  { role_id: 'role-admin', name: 'Admin', description: 'Everything', permissions: {}, is_system_role: true },
  { role_id: 'role-analyst', name: 'Analyst', description: '', permissions: {}, is_system_role: true },
]

const ANALYSTS = {
  id: 1,
  role_id: 'role-analyst',
  role_name: 'Analyst',
  idp_group: 'vigil-analysts',
  priority: 100,
  created_at: '2026-10-09T00:00:00Z',
}
const ADMINS = { ...ANALYSTS, id: 2, role_id: 'role-admin', role_name: 'Admin', idp_group: 'vigil-admins', priority: 200 }

const renderSection = () => render(<RoleMappingsSection notify={notify} />)

beforeEach(() => {
  vi.clearAllMocks()
  roleMappingsApi.getAll.mockResolvedValue({ data: { total: 2, mappings: [ADMINS, ANALYSTS] } })
  api.get.mockResolvedValue({ data: { roles: ROLES } })
  roleMappingsApi.create.mockResolvedValue({ data: {} })
  roleMappingsApi.update.mockResolvedValue({ data: {} })
  roleMappingsApi.remove.mockResolvedValue({ data: {} })
  hasPermission.mockImplementation((p: string) => p === 'users.write')
})

describe('RoleMappingsSection states', () => {
  it('loading', () => {
    roleMappingsApi.getAll.mockReturnValue(new Promise(() => {}))
    renderSection()
    expect(screen.getByText('Loading role mappings…')).toBeInTheDocument()
  })

  it('error offers Retry, which reloads', async () => {
    roleMappingsApi.getAll.mockRejectedValueOnce({ response: { data: { detail: 'nope' } } })
    renderSection()
    expect(await screen.findByText(/Couldn’t load role mappings: nope/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('vigil-analysts')).toBeInTheDocument()
  })

  it('empty: federated sign-ins would grant nothing', async () => {
    roleMappingsApi.getAll.mockResolvedValue({ data: { total: 0, mappings: [] } })
    renderSection()
    expect(await screen.findByText('No role mappings yet.')).toBeInTheDocument()
  })

  it('populated: the table reads group, role, priority, created', async () => {
    renderSection()
    const row = (await screen.findByText('vigil-analysts')).closest('tr')!
    expect(within(row).getByText('Analyst')).toBeInTheDocument()
    expect(within(row).getByText('100')).toBeInTheDocument()
    expect(within(row).getByText(new Date(ANALYSTS.created_at).toLocaleDateString())).toBeInTheDocument()
    // highest priority first, as the API orders them
    const rows = screen.getAllByRole('row').filter((r) => within(r).queryByText(/vigil-/))
    expect(within(rows[0]).getByText('vigil-admins')).toBeInTheDocument()
  })

  it('no-permission banner replaces the section without users.write', async () => {
    hasPermission.mockImplementation(() => false)
    renderSection()
    // The hook still mounts (hooks run before the gate's early return), so
    // this asserts the render, not the absence of a fetch.
    expect(await screen.findByText(/You don’t have permission to manage role mappings/)).toBeInTheDocument()
    expect(screen.queryByText('Add mapping')).not.toBeInTheDocument()
  })
})

describe('RoleMappingsSection editor', () => {
  const openEditor = async () => {
    renderSection()
    await screen.findByText('vigil-analysts')
    fireEvent.click(screen.getByRole('button', { name: 'Add mapping' }))
    await screen.findByRole('dialog', { name: 'Add role mapping' })
  }

  it('creates with the picker defaulting to the first role', async () => {
    await openEditor()
    fireEvent.change(screen.getByLabelText(/^Directory group/), { target: { value: 'vigil-auditors' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(roleMappingsApi.create).toHaveBeenCalledWith({
      role_id: 'role-admin',
      idp_group: 'vigil-auditors',
      priority: 100,
    }))
    expect(notify).toHaveBeenCalledWith('ok', expect.stringContaining('vigil-auditors'))
  })

  it('refuses an empty group without calling the server', async () => {
    await openEditor()
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText('Directory group is required')).toBeInTheDocument()
    expect(roleMappingsApi.create).not.toHaveBeenCalled()
  })

  it('surfaces the server’s duplicate and escalation refusals in the dialog', async () => {
    await openEditor()
    fireEvent.change(screen.getByLabelText(/^Directory group/), { target: { value: 'vigil-dupes' } })
    roleMappingsApi.create.mockRejectedValueOnce({
      response: { status: 409, data: { detail: 'This group is already mapped to this role' } },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText('This group is already mapped to this role')).toBeInTheDocument()
    // the dialog stays open so the actor can correct instead of re-typing
    expect(screen.getByLabelText(/^Directory group/)).toBeInTheDocument()

    roleMappingsApi.create.mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'Cannot map a group to a role with more privileges than your own' } },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText(/more privileges than your own/)).toBeInTheDocument()
  })

  it('edits in place: priority change goes to the right mapping', async () => {
    renderSection()
    await screen.findByText('vigil-analysts')
    fireEvent.click(screen.getByRole('button', { name: 'Edit vigil-analysts' }))
    const priority = screen.getByLabelText(/^Priority/)
    fireEvent.change(priority, { target: { value: '42' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    await waitFor(() =>
      expect(roleMappingsApi.update).toHaveBeenCalledWith(1, {
        role_id: 'role-analyst',
        idp_group: 'vigil-analysts',
        priority: 42,
      }),
    )
  })

  it('deletes through the confirm dialog', async () => {
    renderSection()
    await screen.findByText('vigil-analysts')
    fireEvent.click(screen.getByRole('button', { name: 'Delete vigil-analysts' }))
    expect(roleMappingsApi.remove).not.toHaveBeenCalled()
    const buttons = await screen.findAllByRole('button', { name: 'Delete' })
    fireEvent.click(buttons[buttons.length - 1]) // the dialog's, rendered last
    await waitFor(() => expect(roleMappingsApi.remove).toHaveBeenCalledWith(1))
    expect(notify).toHaveBeenCalledWith('ok', expect.stringContaining('Deleted the mapping'))
  })

  it('controls disable while a save is in flight', async () => {
    await openEditor()
    fireEvent.change(screen.getByLabelText(/^Directory group/), { target: { value: 'slow-group' } })
    let release!: (v: unknown) => void
    roleMappingsApi.create.mockReturnValueOnce(new Promise((r) => (release = r)))
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled())
    release({})
    await waitFor(() => expect(roleMappingsApi.create).toHaveBeenCalledTimes(1))
  })
})

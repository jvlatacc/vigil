import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ColorSchemeProvider } from '../contexts/ColorSchemeContext'
import UnmappedUserState, { hasNoPermissions } from './UnmappedUserState'

const logout = vi.fn()
// Typed wide enough to stub the signed-out shape the component must survive.
type AuthStub = { user: { username?: string; permissions?: Record<string, boolean> } | null; logout: () => void }
const useAuth = vi.hoisted(() =>
  vi.fn<() => AuthStub>(() => ({ user: { username: 'jdoe', permissions: {} }, logout })),
)

vi.mock('../contexts/AuthContext', () => ({ useAuth }))

const renderState = () =>
  render(
    <ColorSchemeProvider>
      <UnmappedUserState />
    </ColorSchemeProvider>,
  )

describe('hasNoPermissions', () => {
  it('true for an empty map or an all-false map — the unmapped federated session', () => {
    expect(hasNoPermissions({ permissions: {} })).toBe(true)
    expect(hasNoPermissions({ permissions: { 'cases.read': false } })).toBe(true)
  })
  it('false for any granted permission, no user, or a user with no map read at all', () => {
    expect(hasNoPermissions({ permissions: { 'settings.read': true } })).toBe(false)
    expect(hasNoPermissions(null)).toBe(false)
    expect(hasNoPermissions(undefined)).toBe(false)
    // A missing map is shape drift, not a provably unmapped session.
    expect(hasNoPermissions({})).toBe(false)
  })
})

describe('UnmappedUserState', () => {
  it('says who is signed in and why nothing is available', () => {
    renderState()
    expect(screen.getByRole('heading', { name: 'No role mapped' })).toBeInTheDocument()
    expect(screen.getByText(/signed in as jdoe/i)).toBeInTheDocument()
    expect(screen.getByText(/directory groups maps to a Vigil role/i)).toBeInTheDocument()
  })

  it('signs out from the state', () => {
    renderState()
    fireEvent.click(screen.getByRole('button', { name: /sign out/i }))
    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('renders without a username on hand', () => {
    useAuth.mockReturnValueOnce({ user: null, logout })
    renderState()
    expect(screen.getByText(/signed in as a user/i)).toBeInTheDocument()
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ColorSchemeProvider } from '../../contexts/ColorSchemeContext'
import LoginScreen from './LoginScreen'

const login = vi.fn()
const navigate = vi.fn()
const oidcProbe = vi.hoisted(() => vi.fn())
const startOidc = vi.hoisted(() => vi.fn())
const bootstrapStatus = vi.hoisted(() => vi.fn())

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ login }),
}))

// stubbed so the hydrate effect resolves deterministically in jsdom
vi.mock('../../services/api', () => ({
  configApi: {
    getTheme: () => Promise.resolve({ data: { theme: 'dark' } }),
    setTheme: () => Promise.resolve({ data: {} }),
  },
  // unmocked, this throws inside the mount effect and fails every test here
  bootstrapApi: {
    status: bootstrapStatus,
    create: () => Promise.resolve({ data: {} }),
  },
  // federated sign-in probe; each test pins its answer in beforeEach
  oidcSignInAvailability: oidcProbe,
  startOidcSignIn: startOidc,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function renderLogin() {
  return render(
    <ColorSchemeProvider>
      <MemoryRouter initialEntries={['/login']}>
        <LoginScreen />
      </MemoryRouter>
    </ColorSchemeProvider>,
  )
}

beforeEach(() => {
  login.mockReset()
  navigate.mockReset()
  oidcProbe.mockReset()
  // federation off by default, so the credential-form tests stay about form
  oidcProbe.mockResolvedValue('off')
  startOidc.mockReset()
  bootstrapStatus.mockReset()
  bootstrapStatus.mockResolvedValue({ data: { required: false } })
})

describe('LoginScreen', () => {
  it('renders the credential form and brand panel', () => {
    renderLogin()
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Username or email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('signs in and routes into the console', async () => {
    login.mockResolvedValueOnce(undefined)
    renderLogin()
    fireEvent.change(screen.getByLabelText('Username or email'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'admin123' } })
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('admin', 'admin123', undefined))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/'))
  })

  it('reveals the MFA step when the backend requires it', async () => {
    login.mockRejectedValueOnce(new Error('MFA_REQUIRED'))
    renderLogin()
    fireEvent.change(screen.getByLabelText('Username or email'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'admin123' } })
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /two-factor/i })).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Authentication code')).toBeInTheDocument()
  })

  describe('sign-in errors', () => {
    async function submit() {
      renderLogin()
      fireEvent.change(screen.getByLabelText('Username or email'), { target: { value: 'admin' } })
      fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
      fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
      return screen.findByRole('alert')
    }

    it('blames the backend, not the credentials, on a network error', async () => {
      login.mockRejectedValueOnce(new Error('Network Error'))
      expect(await submit()).toHaveTextContent("Can't reach the Vigil API. Is the backend running?")
    })

    it('treats a 5xx without a detail as unreachable', async () => {
      login.mockRejectedValueOnce({ response: { status: 500, data: '' } })
      expect(await submit()).toHaveTextContent("Can't reach the Vigil API")
    })

    it('shows the server detail on a 5xx that has one', async () => {
      login.mockRejectedValueOnce({ response: { status: 500, data: { detail: 'DB locked' } } })
      expect(await submit()).toHaveTextContent('DB locked')
    })

    it('keeps the credentials message on a 401', async () => {
      login.mockRejectedValueOnce({ response: { status: 401, data: {} } })
      expect(await submit()).toHaveTextContent('Sign in failed. Check your credentials.')
    })
  })

  it('toggles between light and dark mode', async () => {
    const { container } = renderLogin()
    const root = container.querySelector('.auth-root') as HTMLElement
    await waitFor(() => expect(root.getAttribute('data-theme')).toBe('dark'))
    expect(root).toHaveClass('vg-dark')
    fireEvent.click(screen.getByRole('button', { name: /switch to light mode/i }))
    await waitFor(() => expect(root.getAttribute('data-theme')).toBe('light'))
    expect(root).toHaveClass('vg-light')
  })

  describe('federated sign-in', () => {
    it('offers FreeIPA sign-in above the local form when the backend reports it on, and keeps the local fallback', async () => {
      oidcProbe.mockResolvedValue('on')
      renderLogin()
      const oidcButton = await screen.findByRole('button', { name: /sign in with freeipa/i })
      expect(oidcButton).toBeInTheDocument()
      // the local form stays as the fallback below it
      expect(screen.getByLabelText('Username or email')).toBeInTheDocument()
      expect(screen.getByRole('separator')).toBeInTheDocument()
      fireEvent.click(oidcButton)
      expect(startOidc).toHaveBeenCalledTimes(1)
    })

    it('shows only the local form while federation is off', async () => {
      oidcProbe.mockResolvedValue('off')
      renderLogin()
      await waitFor(() => expect(oidcProbe).toHaveBeenCalledTimes(1))
      expect(screen.queryByRole('button', { name: /sign in with freeipa/i })).not.toBeInTheDocument()
      expect(screen.getByLabelText('Username or email')).toBeInTheDocument()
    })

    it('shows only the local form when the backend cannot be reached', async () => {
      oidcProbe.mockResolvedValue('unknown')
      renderLogin()
      await waitFor(() => expect(oidcProbe).toHaveBeenCalledTimes(1))
      expect(screen.queryByRole('button', { name: /sign in with freeipa/i })).not.toBeInTheDocument()
    })

    it('hides the federated door during first-account creation', async () => {
      oidcProbe.mockResolvedValue('on')
      bootstrapStatus.mockResolvedValue({ data: { required: true } })
      renderLogin()
      expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /sign in with freeipa/i })).not.toBeInTheDocument()
    })
  })
})

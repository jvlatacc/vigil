import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import DigitalTwinScreen from './DigitalTwinScreen'
import { DEMO_TWIN_PAYLOAD as DEMO } from './fixtures'
import type { TwinGraphPayload } from './types'
import type { TwinLayer, TwinNodeData } from './useTwinGraph'

// The screen is a consumer of the hook and the canvas, so both are mocked:
// the hook gets canned spec states (Loading / Ready / Refreshing / Empty /
// Error), the canvas stub records props and fires the selection callback.
// The real mappers, normalizer, and resolver ride along via importOriginal.

type HookState = {
  payload: TwinGraphPayload | null
  phase: 'loading' | 'ready' | 'error'
  refreshing: boolean
  error: string | null
  reload: () => void
}

const hook = vi.hoisted(() => ({
  current: {
    payload: null as TwinGraphPayload | null,
    phase: 'loading' as 'loading' | 'ready' | 'error',
    refreshing: false,
    error: null as string | null,
    reload: () => {},
  },
}))

vi.mock('./useTwinGraph', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./useTwinGraph')>()
  return { ...actual, useTwinGraph: (): HookState => hook.current }
})

vi.mock('./TwinGraph', () => ({
  default: (props: { payload?: TwinGraphPayload; layer?: TwinLayer; onNodeSelect?: (data: TwinNodeData) => void }) => {
    const { payload, layer, onNodeSelect } = props
    const web = payload?.devices.find((d) => d.id === 'dev-web-01')
    const proc = payload?.processes.find((p) => p.id === 'proc-ws-jvl-5520')
    const conn = payload?.connections.find((c) => c.id === 'conn-13')
    return (
      <div data-testid="twin-graph-stub" data-layer={layer}>
        {web && <button onClick={() => onNodeSelect?.({ kind: 'device', entity: web })}>pick device</button>}
        {proc && <button onClick={() => onNodeSelect?.({ kind: 'process', entity: proc })}>pick process</button>}
        {conn && <button onClick={() => onNodeSelect?.({ kind: 'connection', entity: conn })}>pick connection</button>}
        <button onClick={() => onNodeSelect?.({ kind: 'device', entity: { ...web!, id: 'dev-gone' } })}>pick ghost</button>
      </div>
    )
  },
}))

const setViewFull = vi.fn()
const reload = vi.fn()

// the screen only consumes setViewFull; the rest are stubbed to satisfy the
// ConsoleScreenProps contract
const screenProps = {
  openChat: vi.fn(),
  go: vi.fn(),
  goSettings: vi.fn(),
  openCase: vi.fn(),
  setViewFull,
}

const readyState = (payload: TwinGraphPayload | null, over: Partial<HookState> = {}) => ({
  payload,
  phase: 'ready' as const,
  refreshing: false,
  error: null,
  reload,
  ...over,
})

const renderScreen = () => render(<DigitalTwinScreen {...screenProps} />)

// the copy button needs a clipboard; jsdom ships none
const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
beforeEach(() => {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})
afterEach(() => {
  writeText.mockClear()
  setViewFull.mockClear()
  reload.mockClear()
})

describe('DigitalTwinScreen states', () => {
  it('shows the skeleton while loading, with the refresh action disabled', () => {
    hook.current = { payload: null, phase: 'loading', refreshing: false, error: null, reload }
    renderScreen()
    expect(screen.getByText('Loading the twin graph')).toBeInTheDocument()
    expect(screen.queryByTestId('twin-graph-stub')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled()
  })

  it('is full-bleed while mounted and hands the canvas the payload', () => {
    hook.current = readyState(DEMO)
    const { unmount } = renderScreen()
    expect(setViewFull).toHaveBeenCalledWith(true)
    expect(screen.getByTestId('twin-graph-stub')).toBeInTheDocument()
    // the stamp is a date-fns rendering of generated_at, not the raw ISO string
    expect(screen.getByRole('status')).toHaveTextContent(/^Updated /)
    unmount()
    expect(setViewFull).toHaveBeenLastCalledWith(false)
  })

  it('summarizes the entity counts in the top bar', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    const summary = `${DEMO.devices.length} devices · ${DEMO.processes.length} processes · ${DEMO.connections.length} connections`
    expect(screen.getByText(summary)).toBeInTheDocument()
  })

  it('marks the poll tick as Refreshing while the graph stays interactive', () => {
    hook.current = readyState(DEMO, { refreshing: true })
    renderScreen()
    expect(screen.getByRole('status')).toHaveTextContent('Refreshing…')
    expect(screen.getByTestId('twin-graph-stub')).toBeInTheDocument()
  })

  it('keeps the last good graph and explains a failed refresh', () => {
    hook.current = readyState(DEMO, { error: 'Network Error' })
    renderScreen()
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Refresh failed: Network Error — showing the last good graph.')
    expect(screen.getByTestId('twin-graph-stub')).toBeInTheDocument()
    // the strip's Retry runs a full reload
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(reload).toHaveBeenCalled()
  })

  it('shows the empty callout with both ways data arrives', () => {
    hook.current = readyState({ generated_at: '2026-10-10T08:00:00Z', devices: [], processes: [], connections: [] })
    renderScreen()
    expect(screen.getByText('No twin data yet')).toBeInTheDocument()
    expect(screen.getByText('scripts/seed_digital_twin_demo.py')).toBeInTheDocument()
    expect(screen.getByText('/api/v1/digital-twin/ingest')).toBeInTheDocument()
    expect(screen.queryByTestId('twin-graph-stub')).not.toBeInTheDocument()
  })

  it('copies the ingest example to the clipboard', async () => {
    hook.current = readyState({ generated_at: '2026-10-10T08:00:00Z', devices: [], processes: [], connections: [] })
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'Copy ingest example' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/api/v1/digital-twin/ingest')))
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('shows the error callout with retry when there is no graph to keep', () => {
    hook.current = { payload: null, phase: 'error', refreshing: false, error: 'Request failed with status code 500', reload }
    renderScreen()
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't load the digital twin")
    expect(screen.getByRole('alert')).toHaveTextContent('Request failed with status code 500')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(reload).toHaveBeenCalled()
  })
})

describe('DigitalTwinScreen interactions', () => {
  it('filters the canvas through the layer select', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.change(screen.getByRole('combobox', { name: 'Layer' }), { target: { value: 'physical' } })
    expect(screen.getByTestId('twin-graph-stub')).toHaveAttribute('data-layer', 'physical')
    fireEvent.change(screen.getByRole('combobox', { name: 'Layer' }), { target: { value: 'logical' } })
    expect(screen.getByTestId('twin-graph-stub')).toHaveAttribute('data-layer', 'logical')
  })

  it('opens the device detail with the physical identity', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick device' }))
    const panel = screen.getByRole('complementary', { name: 'Node details' })
    expect(panel).toHaveTextContent('0a:1b:2c:3d:4e:01')
    expect(panel).toHaveTextContent('C02X1234ABCD')
    expect(panel).toHaveTextContent('10.0.4.11')
  })

  it('opens the process detail with pid and user', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick process' }))
    const panel = screen.getByRole('complementary', { name: 'Node details' })
    expect(panel).toHaveTextContent('powershell')
    expect(panel).toHaveTextContent('5520')
  })

  it('opens the connection detail with the 5-tuple and type', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick connection' }))
    const panel = screen.getByRole('complementary', { name: 'Node details' })
    expect(panel).toHaveTextContent('socket')
    expect(panel).toHaveTextContent('tcp')
    expect(panel).toHaveTextContent('10.0.9.44')
  })

  it('closes the detail panel from its close button', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick device' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('complementary', { name: 'Node details' })).not.toBeInTheDocument()
  })

  it('keeps the panel through a refresh that still names the entity, and closes it when the entity is gone', () => {
    hook.current = readyState(DEMO)
    const { rerender } = renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick device' }))

    const fresh: TwinGraphPayload = {
      ...DEMO,
      devices: DEMO.devices.map((d) => (d.id === 'dev-web-01' ? { ...d, last_seen: '2026-10-10T09:00:00Z' } : d)),
    }
    hook.current = readyState(fresh)
    rerender(<DigitalTwinScreen {...screenProps} />)
    expect(screen.getByRole('complementary', { name: 'Node details' })).toBeInTheDocument()

    const withoutWeb: TwinGraphPayload = { ...DEMO, devices: DEMO.devices.filter((d) => d.id !== 'dev-web-01') }
    hook.current = readyState(withoutWeb)
    rerender(<DigitalTwinScreen {...screenProps} />)
    expect(screen.queryByRole('complementary', { name: 'Node details' })).not.toBeInTheDocument()
  })

  it('does not open a panel for an entity the payload never carried', () => {
    hook.current = readyState(DEMO)
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'pick ghost' }))
    expect(screen.queryByRole('complementary', { name: 'Node details' })).not.toBeInTheDocument()
  })
})

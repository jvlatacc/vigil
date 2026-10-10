import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Finding } from '../../data/data'
import type { ConsoleScreenProps } from '../../shared/types'
import type { TwinGraphVM, TwinNodeVM } from './model'
import NetworkTwinScreen from './NetworkTwinScreen'
import { useTwinGraph } from './useTwinGraph'

vi.mock('./useTwinGraph', () => ({ useTwinGraph: vi.fn() }))

/* The canvas is replaced with buttons that surface the selection contract
 * (click a node -> onNodeSelect); the canvas itself is covered by its own
 * suite. FindingPopup's real body fetches findings; the screen contract
 * only needs to show that the click-through hands over the right id. */
vi.mock('./TwinGraphCanvas', () => ({
  default: ({
    nodes,
    onNodeSelect,
  }: {
    nodes?: TwinNodeVM[]
    onNodeSelect?: (n: TwinNodeVM) => void
  }) => (
    <div data-testid="canvas">
      {(nodes ?? []).map((n) => (
        <button key={n.id} onClick={() => onNodeSelect?.(n)}>
          {n.label}
        </button>
      ))}
    </div>
  ),
}))
vi.mock('../dashboard/FindingPopup', () => ({
  default: ({ id }: { id: string | null }) => (id ? <div data-testid="finding-popup">{id}</div> : null),
}))

const finding = (over: Partial<Finding> & { id: string }): Finding => ({
  sev: 'High',
  tech: 'T1059',
  conf: 80,
  tactic: 'Execution',
  src: 'crowdstrike',
  host: '—',
  user: '—',
  time: 'Oct 9, 12:00',
  score: 7,
  status: 'open',
  ...over,
})

const node = (over: Partial<TwinNodeVM> & { id: string; label: string }): TwinNodeVM => ({
  kind: 'host',
  findings: [],
  cases: [],
  severityCounts: { crit: 1, high: 0, med: 0, low: 0, unranked: 0 },
  ...over,
})

const graph = (): TwinGraphVM => ({
  generatedAt: 'Oct 9, 12:00:00',
  nodes: [
    node({
      id: 'host:web-01',
      label: 'web-01',
      findings: [finding({ id: 'f-1', sev: 'Critical', tech: 'T1486', host: 'web-01' })],
      cases: [{ id: 'c-1', title: 'Ransomware dry run', status: 'investigating', prio: 'high' }],
    }),
    node({
      id: 'ip:10.0.0.5',
      kind: 'ip',
      label: '10.0.0.5',
      findings: [finding({ id: 'f-2', sev: 'Low', status: 'closed', src: 'splunk' })],
      severityCounts: { crit: 0, high: 0, med: 0, low: 1, unranked: 0 },
    }),
  ],
  edges: [],
})

type HookState = ReturnType<typeof useTwinGraph>

const hookState = (over: Partial<HookState> = {}): HookState =>
  ({
    graph: null,
    phase: 'ready',
    error: null,
    refreshing: false,
    reload: vi.fn(),
    ...over,
  }) as HookState

const mockHook = (state: HookState) => vi.mocked(useTwinGraph).mockReturnValue(state)

const screenProps = (): ConsoleScreenProps =>
  ({
    openChat: vi.fn(),
    go: vi.fn(),
    goSettings: vi.fn(),
    openCase: vi.fn(),
    setViewFull: vi.fn(),
  }) as ConsoleScreenProps

beforeEach(() => vi.clearAllMocks())

describe('NetworkTwinScreen', () => {
  it('offers a spinner, and no canvas, while the first load is in flight', () => {
    mockHook(hookState({ phase: 'loading' }))
    render(<NetworkTwinScreen {...screenProps()} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Drawing the map…')
    expect(screen.queryByTestId('canvas')).not.toBeInTheDocument()
  })

  it('lands in an error state with a retry that reloads, canvas absent', () => {
    const reload = vi.fn()
    mockHook(hookState({ phase: 'error', error: 'down', reload }))
    render(<NetworkTwinScreen {...screenProps()} />)

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText("Couldn't load the map")).toBeInTheDocument()
    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(reload).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('canvas')).not.toBeInTheDocument()
  })

  it('explains derivation in the empty state and offers a way back to work', () => {
    const props = screenProps()
    mockHook(hookState({ graph: { generatedAt: 'x', nodes: [], edges: [] } }))
    render(<NetworkTwinScreen {...props} />)

    expect(screen.getByText('No findings to map yet')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Open Dashboard/ }))
    expect(props.go).toHaveBeenCalledWith('dashboard')
    fireEvent.click(screen.getByRole('button', { name: /Configure sources/ }))
    expect(props.goSettings).toHaveBeenCalledWith('integrations')
  })

  it('renders the ready state: canvas, KPI strip and the generation time', () => {
    mockHook(hookState({ graph: graph() }))
    render(<NetworkTwinScreen {...screenProps()} />)

    expect(screen.getByTestId('canvas')).toBeInTheDocument()
    expect(screen.getByText('Nodes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'web-01' })).toBeInTheDocument()
    expect(screen.getByText(/Generated Oct 9, 12:00:00/)).toBeInTheDocument()
  })

  it('pins the popover to the selected node: exactly its findings and cases', () => {
    mockHook(hookState({ graph: graph() }))
    render(<NetworkTwinScreen {...screenProps()} />)

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    const dialog = screen.getByRole('dialog', { name: /Findings on web-01/ })
    expect(within(dialog).getByText('T1486')).toBeInTheDocument()
    expect(within(dialog).getByText('Ransomware dry run')).toBeInTheDocument()
    // the other node's finding must not leak into this popover
    expect(within(dialog).queryByText('T1059')).not.toBeInTheDocument()
  })

  it('hands the finding id to the popup on click-through and closes the popover', () => {
    mockHook(hookState({ graph: graph() }))
    render(<NetworkTwinScreen {...screenProps()} />)

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /T1486/ }))

    expect(screen.getByTestId('finding-popup')).toHaveTextContent('f-1')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the case drawer from the popover', () => {
    const props = screenProps()
    mockHook(hookState({ graph: graph() }))
    render(<NetworkTwinScreen {...props} />)

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Ransomware dry run/ }))
    expect(props.openCase).toHaveBeenCalledWith('c-1')
  })

  it('closes the popover on Escape and on a click away', () => {
    mockHook(hookState({ graph: graph() }))
    render(<NetworkTwinScreen {...screenProps()} />)

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    fireEvent(document.body, new MouseEvent('mousedown', { bubbles: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the canvas up under a failed refresh and surfaces the banner', () => {
    mockHook(hookState({ graph: graph(), error: 'flaky', reload: vi.fn() }))
    render(<NetworkTwinScreen {...screenProps()} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/Live refresh failed/)
    expect(screen.getByTestId('canvas')).toBeInTheDocument()
  })
})

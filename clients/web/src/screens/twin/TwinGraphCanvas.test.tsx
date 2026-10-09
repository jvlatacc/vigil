import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TwinGraphCanvas from './TwinGraphCanvas'
import type { TwinNodeVM } from './model'

/* React Flow is mocked per the WorkflowBuilder exemplar: the mock surfaces
 * the nodes as buttons (click -> onNodeClick) and prints each node's
 * position, which is what the persistence contract needs. */
type MockFlowNode = { id: string; position: { x: number; y: number }; data: { vm: TwinNodeVM } }

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({
    nodes,
    onNodeClick,
    onPaneClick,
    children,
  }: {
    nodes?: MockFlowNode[]
    onNodeClick?: (e: unknown, node: MockFlowNode) => void
    onPaneClick?: () => void
    children?: React.ReactNode
  }) => (
    <div>
      {(nodes ?? []).map((n) => (
        <button
          key={n.id}
          data-testid={n.id}
          data-x={String(n.position.x)}
          data-y={String(n.position.y)}
          onClick={() => onNodeClick?.(null, n)}
        >
          {n.data.vm.label}
        </button>
      ))}
      <button data-testid="pane" onClick={() => onPaneClick?.()} aria-label="Pane" />
      {children}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  applyNodeChanges: (_c: unknown, nds: unknown[]) => nds,
  useNodesInitialized: () => false,
  useReactFlow: () => ({ fitView: vi.fn() }),
  MarkerType: { ArrowClosed: 'arrowclosed' },
}))
vi.mock('@xyflow/react/dist/style.css', () => ({}))

const node = (id: string, label: string, x?: number, y?: number): TwinNodeVM => ({
  id,
  kind: id.startsWith('host') ? 'host' : 'ip',
  label,
  findings: [],
  cases: [],
  severityCounts: { crit: 1, high: 0, med: 0, low: 0, unranked: 0 },
  ...(x != null && y != null ? { position: { x, y } } : {}),
})

const props = (over: Record<string, unknown> = {}) => ({
  nodes: [] as TwinNodeVM[],
  edges: [],
  selectedId: null,
  onNodeSelect: vi.fn(),
  onPaneSelect: vi.fn(),
  ...over,
})

describe('TwinGraphCanvas', () => {
  it('renders one labelled node per vm, plus the edge legend', () => {
    render(
      <TwinGraphCanvas
        {...props({ nodes: [node('host:web-01', 'web-01', 10, 20), node('ip:10.0.0.5', '10.0.0.5')] })}
      />,
    )
    expect(screen.getByRole('button', { name: 'web-01' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '10.0.0.5' })).toBeInTheDocument()
    expect(screen.getByText(/flow — observed src/)).toBeInTheDocument()
    expect(screen.getByText(/link — co-named entities/)).toBeInTheDocument()
  })

  it('selects the clicked node and clears on a pane click', () => {
    const onNodeSelect = vi.fn()
    const onPaneSelect = vi.fn()
    render(<TwinGraphCanvas {...props({ nodes: [node('host:web-01', 'web-01', 0, 0)], onNodeSelect, onPaneSelect })} />)

    fireEvent.click(screen.getByRole('button', { name: 'web-01' }))
    expect(onNodeSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'host:web-01' }))

    fireEvent.click(screen.getByTestId('pane'))
    expect(onPaneSelect).toHaveBeenCalledTimes(1)
  })

  it('keeps placed positions across a poll tick; only new nodes take a layout', () => {
    const first = node('host:web-01', 'web-01', 10, 20)
    const { rerender } = render(<TwinGraphCanvas {...props({ nodes: [first] })} />)
    expect(screen.getByTestId('host:web-01')).toHaveAttribute('data-x', '10')

    // the poll lands: web-01 re-arrives with a fresh served layout while a
    // new node joins — the placed position must win for web-01
    rerender(
      <TwinGraphCanvas
        {...props({ nodes: [node('host:web-01', 'web-01', 999, 999), node('ip:10.0.0.5', '10.0.0.5', 5, 6)] })}
      />,
    )
    expect(screen.getByTestId('host:web-01')).toHaveAttribute('data-x', '10')
    expect(screen.getByTestId('ip:10.0.0.5')).toHaveAttribute('data-x', '5')
  })
})

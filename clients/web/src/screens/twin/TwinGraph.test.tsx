import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TwinGraph from './TwinGraph'
import { buildTwinGraph } from './useTwinGraph'
import { DEMO_TWIN_PAYLOAD as DEMO } from './fixtures'

const rf = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }))
const scheme = vi.hoisted(() => ({ current: 'dark' as 'light' | 'dark' }))

// The WorkflowBuilder.test.tsx pattern: stub the canvas so tests assert what
// TwinGraph passes to React Flow, not how React Flow renders it.
vi.mock('@xyflow/react', () => ({
  ReactFlow: (props: Record<string, unknown>) => {
    rf.props.push(props)
    return <div data-testid="twin-canvas">{props.children as React.ReactNode}</div>
  },
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  Handle: () => null,
  Position: { Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrow' },
}))
vi.mock('@xyflow/react/dist/style.css', () => ({}))
vi.mock('../../contexts/ColorSchemeContext', () => ({
  useColorScheme: () => ({ scheme: scheme.current, toggleScheme: () => {}, setScheme: () => {} }),
}))

const lastProps = (): Record<string, unknown> => rf.props[rf.props.length - 1]

beforeEach(() => {
  rf.props.length = 0
})

describe('TwinGraph canvas', () => {
  it('passes custom node types for all three entity classes and the mapped graph', () => {
    render(<TwinGraph payload={DEMO} />)
    expect(screen.getByTestId('twin-canvas')).toBeInTheDocument()

    const props = lastProps()
    expect(Object.keys(props.nodeTypes as Record<string, unknown>).sort()).toEqual(['connection', 'device', 'process'])

    const nodes = props.nodes as Array<{ type?: string }>
    expect(nodes).toHaveLength(DEMO.devices.length + DEMO.processes.length + DEMO.connections.length)
    const edges = props.edges as Array<{ data?: { kind?: string } }>
    expect(edges).toHaveLength(buildTwinGraph(DEMO).edges.length)
  })

  it('layer=physical prunes processes, connections, and their edges', () => {
    render(<TwinGraph payload={DEMO} layer="physical" />)
    const props = lastProps()

    const nodes = props.nodes as Array<{ type?: string }>
    expect(nodes.every((n) => n.type === 'device')).toBe(true)
    const edges = props.edges as Array<{ data?: { kind?: string } }>
    expect(edges).toHaveLength(8)
    expect(edges.every((e) => e.data?.kind === 'talks-to')).toBe(true)
  })

  it('drives colorMode from useColorScheme instead of hardcoding dark', () => {
    scheme.current = 'light'
    const { rerender } = render(<TwinGraph payload={DEMO} />)
    expect(lastProps().colorMode).toBe('light')

    scheme.current = 'dark'
    rerender(<TwinGraph payload={DEMO} />)
    expect(lastProps().colorMode).toBe('dark')
  })
})

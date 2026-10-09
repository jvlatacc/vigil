import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  applyNodeChanges,
  useNodesInitialized,
  useReactFlow,
  type Edge,
  type NodeChange,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import TwinNode, { type TwinNodeType } from './TwinNode'
import { resolvePositions, type TwinEdgeVM, type TwinNodeVM } from './model'

const NODE_TYPES = { twin: TwinNode } satisfies NodeTypes

/** flow = observed src→dst (directed, solid); link = co-named entities
 *  (undirected, dashed). The weight badge repeats the legend's meaning. */
function toFlowEdges(edges: TwinEdgeVM[]): Edge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    ...(e.kind === 'flow' ? { markerEnd: { type: MarkerType.ArrowClosed } } : {}),
    style:
      e.kind === 'flow'
        ? { stroke: 'var(--accent)', strokeWidth: 1.6 }
        : { stroke: 'var(--tx-3)', strokeWidth: 1.2, strokeDasharray: '4 3' },
    ...(e.weight > 1
      ? {
          label: `${e.weight}×`,
          labelShowBg: true,
          labelBgStyle: { fill: 'var(--panel)' },
          labelStyle: { fill: 'var(--tx-2)', fontSize: 10 },
        }
      : {}),
  }))
}

/** The served layout lands after mount, so the `fitView` prop has nothing
 *  to fit; this fits once, the first time nodes have measurable size. */
function FitOnFirstNodes({ pending }: { pending: boolean }) {
  const initialized = useNodesInitialized()
  const { fitView } = useReactFlow()
  const done = useRef(false)
  useEffect(() => {
    if (pending && initialized && !done.current) {
      done.current = true
      fitView({ padding: 0.25, maxZoom: 1 })
    }
  }, [pending, initialized, fitView])
  return null
}

export default function TwinGraphCanvas({
  nodes,
  edges,
  selectedId,
  onNodeSelect,
  onPaneSelect,
}: {
  nodes: TwinNodeVM[]
  edges: TwinEdgeVM[]
  selectedId: string | null
  onNodeSelect: (node: TwinNodeVM) => void
  onPaneSelect: () => void
}) {
  const [rfNodes, setRfNodes] = useState<TwinNodeType[]>([])
  // every placed position lives here, so poll ticks and filter passes
  // cannot rearrange what the analyst already arranged
  const positionsRef = useRef(new Map<string, { x: number; y: number }>())

  useEffect(() => {
    const resolved = resolvePositions(nodes, positionsRef.current)
    for (const n of resolved) {
      if (n.position) positionsRef.current.set(n.id, n.position)
    }
    setRfNodes(
      resolved.map((vm) => ({
        id: vm.id,
        type: 'twin' as const,
        position: { x: vm.position?.x ?? 0, y: vm.position?.y ?? 0 },
        selected: vm.id === selectedId,
        data: { vm },
      })),
    )
  }, [nodes, selectedId])

  const rfEdges = useMemo<Edge[]>(() => toFlowEdges(edges), [edges])

  const onNodesChange = useCallback((changes: NodeChange<TwinNodeType>[]) => {
    setRfNodes((nds) => applyNodeChanges(changes, nds))
  }, [])

  const onNodeDragStop = useCallback((_: unknown, node: TwinNodeType) => {
    positionsRef.current.set(node.id, node.position)
  }, [])

  const onNodeClick = useCallback(
    (_: unknown, node: TwinNodeType) => {
      onNodeSelect(node.data.vm)
    },
    [onNodeSelect],
  )

  return (
    <div className="twin-canvas" data-testid="twin-canvas">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        minZoom={0.1}
        maxZoom={1.75}
        nodesDraggable
        elementsSelectable
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onPaneClick={onPaneSelect}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <FitOnFirstNodes pending={nodes.length > 0} />
        <Background />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
      <div className="twin-legend" aria-hidden="true">
        <span>
          <i className="twin-legend-flow" /> flow — observed src → dst
        </span>
        <span>
          <i className="twin-legend-link" /> link — co-named entities
        </span>
        <span>×N — findings behind an edge</span>
      </div>
    </div>
  )
}

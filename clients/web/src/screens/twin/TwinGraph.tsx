import { useCallback, useMemo, type MouseEvent } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useColorScheme } from '../../contexts/ColorSchemeContext'
import {
  buildTwinGraph,
  connectionTupleLabel,
  filterTwinGraph,
  type TwinConnectionFlowNode,
  type TwinDeviceFlowNode,
  type TwinLayer,
  type TwinNodeData,
  type TwinProcessFlowNode,
} from './useTwinGraph'
import type { TwinConnectionType, TwinGraphPayload } from './types'

/**
 * The read-only twin canvas (presentational layer): a React Flow graph with a
 * custom node per entity class. The screen owns data fetching, the layer
 * toggle, and the detail panel — this component maps the payload and renders.
 */

function DeviceNode({ data, selected }: NodeProps<TwinDeviceFlowNode>) {
  const d = data.entity
  return (
    <div className={`w-60 rounded-lg border bg-panel px-3 py-2.5 shadow-panel ${selected ? 'border-accent' : 'border-line'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[13px] font-bold text-tx">{d.hostname || d.id}</span>
        <span className="shrink-0 rounded border border-line bg-bg-3 px-1.5 py-px text-[9.5px] font-bold uppercase tracking-[0.06em] text-tx-3">
          {d.device_type}
        </span>
      </div>
      <div className="mt-1 space-y-px font-mono text-[10.5px] leading-relaxed text-tx-2">
        {d.mac_address && <div>MAC {d.mac_address}</div>}
        {d.serial_number && <div>S/N {d.serial_number}</div>}
        {d.ip_address && <div>IP {d.ip_address}</div>}
      </div>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

function ProcessNode({ data, selected }: NodeProps<TwinProcessFlowNode>) {
  const p = data.entity
  return (
    <div className={`w-60 rounded-lg border bg-panel px-3 py-2.5 shadow-panel ${selected ? 'border-accent' : 'border-line'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[13px] font-bold text-tx">{p.name}</span>
        <span className="shrink-0 font-mono text-[10px] text-tx-3">pid {p.pid}</span>
      </div>
      <div className="mt-0.5 truncate text-[10.5px] text-tx-3">{p.user ? `user ${p.user}` : 'user unknown'}</div>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const TYPE_BADGE: Record<TwinConnectionType, string> = {
  socket: 'border-accent-line bg-accent-dim text-accent',
  stream: 'border-med bg-med-dim text-med',
  session: 'border-ok bg-ok-dim text-ok',
}

function ConnectionNode({ data, selected }: NodeProps<TwinConnectionFlowNode>) {
  const c = data.entity
  return (
    <div className={`w-72 rounded-lg border bg-panel px-3 py-2.5 shadow-panel ${selected ? 'border-accent' : 'border-line'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[11px] text-tx">{connectionTupleLabel(c)}</span>
        <span className={`shrink-0 rounded border px-1.5 py-px text-[9.5px] font-bold uppercase tracking-[0.06em] ${TYPE_BADGE[c.connection_type]}`}>
          {c.connection_type}
        </span>
      </div>
      <div className="mt-0.5 truncate text-[10.5px] text-tx-3">{[c.state, `via ${c.source}`].filter(Boolean).join(' · ')}</div>
      <Handle type="target" position={Position.Left} />
    </div>
  )
}

const nodeTypes = { device: DeviceNode, process: ProcessNode, connection: ConnectionNode }

export default function TwinGraph({
  payload,
  layer = 'all',
  onNodeSelect,
}: {
  payload: TwinGraphPayload
  layer?: TwinLayer
  /** Screen-level detail panel: carries the clicked entity's data. */
  onNodeSelect?: (data: TwinNodeData) => void
}) {
  const { scheme } = useColorScheme()
  const graph = useMemo(() => {
    const built = buildTwinGraph(payload)
    return filterTwinGraph(built.nodes, built.edges, layer)
  }, [payload, layer])

  // Resolve the click against our own typed nodes instead of casting React
  // Flow's generic node.data — an unknown node id simply selects nothing.
  const handleNodeClick = useCallback(
    (_: MouseEvent, node: Node) => {
      const hit = graph.nodes.find((n) => n.id === node.id)
      if (hit && onNodeSelect) onNodeSelect(hit.data)
    },
    [graph.nodes, onNodeSelect],
  )

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        colorMode={scheme}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        minZoom={0.1}
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  )
}

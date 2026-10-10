import { useCallback, useEffect, useState } from 'react'
import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type { TwinConnection, TwinDevice, TwinGraphPayload, TwinProcess } from './types'
import { DEMO_TWIN_PAYLOAD } from './fixtures'

/**
 * Pure mappers from the spec's graph payload to React Flow nodes and edges,
 * plus the Phase hook the screen will consume. No state, no fetching — the
 * wiring PR only swaps the loader.
 */

/** Layer toggle: physical shows devices, logical shows processes + connections. */
export type TwinLayer = 'all' | 'physical' | 'logical'

export type DeviceNodeData = { kind: 'device'; entity: TwinDevice }
export type ProcessNodeData = { kind: 'process'; entity: TwinProcess }
export type ConnectionNodeData = { kind: 'connection'; entity: TwinConnection }
export type TwinNodeData = DeviceNodeData | ProcessNodeData | ConnectionNodeData

export type TwinDeviceFlowNode = Node<DeviceNodeData, 'device'>
export type TwinProcessFlowNode = Node<ProcessNodeData, 'process'>
export type TwinConnectionFlowNode = Node<ConnectionNodeData, 'connection'>
export type TwinFlowNode = TwinDeviceFlowNode | TwinProcessFlowNode | TwinConnectionFlowNode

export type TwinEdgeKind = 'runs' | 'binds' | 'talks-to'
export type TwinEdgeData = { kind: TwinEdgeKind; heuristic?: boolean }
export type TwinFlowEdge = Edge<TwinEdgeData>

/** Columns: devices left, processes middle, connections right. */
export const DEVICE_X = 0
export const PROCESS_X = 340
export const CONNECTION_X = 680
export const ROW_Y = 130

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)

// Natural keys carry the stable y-ordering; the id is the final tiebreaker so
// the same entity set always lays out identically regardless of payload order.
const deviceKey = (d: TwinDevice) => `${(d.hostname || d.mac_address || d.id).toLowerCase()}:${d.id}`
const processKey = (p: TwinProcess) => `${p.name.toLowerCase()}:${p.pid}:${p.id}`
const connectionKey = (c: TwinConnection) =>
  `${c.protocol || ''}:${c.local_ip || ''}:${c.local_port ?? ''}:${c.remote_ip || ''}:${c.remote_port ?? ''}:${c.connection_type}:${c.id}`

function makeEdge(id: string, source: string, target: string, kind: TwinEdgeKind): TwinFlowEdge {
  const heuristic = kind === 'talks-to'
  return {
    id,
    source,
    target,
    type: 'smoothstep',
    data: heuristic ? { kind, heuristic: true } : { kind },
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: heuristic ? 'var(--accent)' : 'var(--line)' },
    // talks-to is the spec's labeled heuristic edge — dashed so it reads as inferred
    ...(heuristic
      ? {
          label: 'talks-to',
          labelStyle: { fill: 'var(--tx-3)', fontSize: 10 },
          labelBgStyle: { fill: 'var(--panel)' },
          strokeDasharray: '6 3',
        }
      : {}),
  }
}

/**
 * The heuristic edge family: a connection whose `remote_ip` matches another
 * device's last-known `ip_address` implies that device talks to it. v1 matches
 * `ip_address` only — reused or overlapping addresses can fabricate a link,
 * which is why the edge renders dashed and labeled. Self-connections
 * (remote_ip equal to the device's own IP) and remotes with no known device
 * produce no edge; repeated observations of the same pair collapse into one.
 */
export function deriveTalksToEdges(devices: TwinDevice[], connections: TwinConnection[]): TwinFlowEdge[] {
  const deviceByIp = new Map<string, TwinDevice>()
  for (const d of [...devices].sort((a, b) => cmp(deviceKey(a), deviceKey(b)))) {
    if (d.ip_address && !deviceByIp.has(d.ip_address)) deviceByIp.set(d.ip_address, d)
  }
  const seen = new Set<string>()
  const edges: TwinFlowEdge[] = []
  for (const c of [...connections].sort((a, b) => cmp(connectionKey(a), connectionKey(b)))) {
    const remote = c.remote_ip ? deviceByIp.get(c.remote_ip) : undefined
    if (!remote || remote.id === c.device_id) continue
    const key = `${c.device_id}->${remote.id}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push(makeEdge(`talks-to:${key}`, c.device_id, remote.id, 'talks-to'))
  }
  return edges
}

/**
 * Layered graph: one node per entity (devices / processes / connections in
 * their own columns), device `runs` process edges, process `binds` connection
 * edges, and the heuristic device `talks-to` device edges. Orphan references
 * (an entity pointing at a device or process the payload never named) keep
 * their node but lose the dangling edge — React Flow never sees a missing
 * endpoint.
 */
export function buildTwinGraph(payload: TwinGraphPayload): { nodes: TwinFlowNode[]; edges: TwinFlowEdge[] } {
  const devices = [...payload.devices].sort((a, b) => cmp(deviceKey(a), deviceKey(b)))
  const processes = [...payload.processes].sort((a, b) => cmp(processKey(a), processKey(b)))
  const connections = [...payload.connections].sort((a, b) => cmp(connectionKey(a), connectionKey(b)))

  const nodes: TwinFlowNode[] = [
    ...devices.map((d, i) => ({
      id: d.id,
      type: 'device' as const,
      position: { x: DEVICE_X, y: i * ROW_Y },
      data: { kind: 'device' as const, entity: d },
    })),
    ...processes.map((p, i) => ({
      id: p.id,
      type: 'process' as const,
      position: { x: PROCESS_X, y: i * ROW_Y },
      data: { kind: 'process' as const, entity: p },
    })),
    ...connections.map((c, i) => ({
      id: c.id,
      type: 'connection' as const,
      position: { x: CONNECTION_X, y: i * ROW_Y },
      data: { kind: 'connection' as const, entity: c },
    })),
  ]

  const deviceIds = new Set(devices.map((d) => d.id))
  const processIds = new Set(processes.map((p) => p.id))

  const edges: TwinFlowEdge[] = []
  for (const p of processes) {
    if (!deviceIds.has(p.device_id)) continue
    edges.push(makeEdge(`runs:${p.device_id}:${p.id}`, p.device_id, p.id, 'runs'))
  }
  for (const c of connections) {
    if (!c.process_id || !processIds.has(c.process_id) || !deviceIds.has(c.device_id)) continue
    edges.push(makeEdge(`binds:${c.process_id}:${c.id}`, c.process_id, c.id, 'binds'))
  }
  edges.push(...deriveTalksToEdges(devices, connections))

  return { nodes, edges }
}

/** Hides node classes the layer filters out, and every edge that would dangle. */
export function filterTwinGraph(
  nodes: TwinFlowNode[],
  edges: TwinFlowEdge[],
  layer: TwinLayer,
): { nodes: TwinFlowNode[]; edges: TwinFlowEdge[] } {
  if (layer === 'all') return { nodes, edges }
  const keptTypes = layer === 'physical' ? ['device'] : ['process', 'connection']
  const keptNodes = nodes.filter((n) => n.type !== undefined && keptTypes.includes(n.type))
  const ids = new Set(keptNodes.map((n) => n.id))
  return { nodes: keptNodes, edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)) }
}

/** `tcp remote → local` for inbound, `tcp local → remote` for outbound — the
 *  arrow follows the traffic, not the field order. */
export function connectionTupleLabel(c: TwinConnection): string {
  const proto = c.protocol ? `${c.protocol} ` : ''
  const local = `${c.local_ip ?? '?'}:${c.local_port ?? '?'}`
  const remote = `${c.remote_ip ?? '?'}:${c.remote_port ?? '?'}`
  return c.direction === 'outbound' ? `${proto}${local} → ${remote}` : `${proto}${remote} → ${local}`
}

export type TwinPhase = 'loading' | 'ready' | 'error'

/**
 * Stand-in data source until the twin API lands: the wiring PR swaps this one
 * function for the real `GET /graph` call without touching the mappers.
 */
export function loadTwinPayload(): Promise<TwinGraphPayload> {
  return Promise.resolve(DEMO_TWIN_PAYLOAD)
}

export function useTwinGraph(): {
  payload: TwinGraphPayload | null
  phase: TwinPhase
  error: string | null
  reload: () => void
} {
  const [payload, setPayload] = useState<TwinGraphPayload | null>(null)
  const [phase, setPhase] = useState<TwinPhase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    setError(null)
    loadTwinPayload()
      .then((next) => {
        if (cancelled) return
        setPayload(next)
        setPhase('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setError((e as { message?: string })?.message || 'Failed to load the twin graph')
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  return { payload, phase, error, reload }
}

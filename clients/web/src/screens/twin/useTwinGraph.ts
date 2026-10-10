import { useCallback, useEffect, useRef, useState } from 'react'
import { MarkerType, type Edge, type Node } from '@xyflow/react'
import { twinApi } from '../../services/api'
import type { Schema } from '../../services/apiTypes'
import type {
  TwinConnection,
  TwinDevice,
  TwinDeviceType,
  TwinDirection,
  TwinGraphPayload,
  TwinProcess,
} from './types'

/**
 * Pure mappers from the spec's graph payload to React Flow nodes and edges,
 * plus the Phase hook the screen consumes: the loader normalizes the wire
 * DTO, the mappers stay framework-pure, and the hook owns fetching, the
 * 30 s poll, and the refresh semantics.
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

/** The generated OpenAPI wire shape (optional lists, untyped uuid ids). */
type TwinGraphWire = Schema<'TwinGraphPayload'>

const DEVICE_TYPES: TwinDeviceType[] = ['server', 'workstation', 'appliance', 'iot', 'container_host']

const asDeviceType = (value: string): TwinDeviceType =>
  (DEVICE_TYPES as string[]).includes(value) ? (value as TwinDeviceType) : 'unknown'

const asDirection = (value: string | null | undefined): TwinDirection | null =>
  value === 'inbound' || value === 'outbound' ? value : null

/**
 * Wire DTO → the screen's payload: ids arrive as untyped uuids
 * (openapi-typescript can't see the format), the three lists are optional
 * server-side, and free-form enum fields fall back to `unknown`/`null`
 * instead of lying about their type.
 */
export function normalizeTwinPayload(raw: TwinGraphWire): TwinGraphPayload {
  return {
    generated_at: raw.generated_at,
    devices: (raw.devices ?? []).map((d) => ({
      id: String(d.id),
      hostname: d.hostname ?? null,
      mac_address: d.mac_address ?? null,
      serial_number: d.serial_number ?? null,
      device_type: asDeviceType(d.device_type),
      ip_address: d.ip_address ?? null,
      source: d.source,
      first_seen: d.first_seen,
      last_seen: d.last_seen,
    })),
    processes: (raw.processes ?? []).map((p) => ({
      id: String(p.id),
      device_id: String(p.device_id),
      pid: p.pid,
      name: p.name,
      user: p.user ?? null,
      command: p.command ?? null,
      source: p.source,
      first_seen: p.first_seen,
      last_seen: p.last_seen,
    })),
    connections: (raw.connections ?? []).map((c) => ({
      id: String(c.id),
      device_id: String(c.device_id),
      process_id: c.process_id == null ? null : String(c.process_id),
      connection_type: c.connection_type,
      protocol: c.protocol ?? null,
      local_ip: c.local_ip ?? null,
      local_port: c.local_port ?? null,
      remote_ip: c.remote_ip ?? null,
      remote_port: c.remote_port ?? null,
      state: c.state ?? null,
      direction: asDirection(c.direction),
      source: c.source,
      first_seen: c.first_seen,
      last_seen: c.last_seen,
    })),
  }
}

/** The detail panel's selection, re-resolved against a fresh payload: a
 *  refresh that still carries the entity keeps the panel open with the
 *  entity's fresher fields; one that no longer names it closes the panel
 *  instead of showing a row the canvas no longer has. */
export function resolveSelection(
  payload: TwinGraphPayload | null,
  selected: TwinNodeData | null,
): TwinNodeData | null {
  if (!selected || !payload) return null
  switch (selected.kind) {
    case 'device': {
      const fresh = payload.devices.find((d) => d.id === selected.entity.id)
      return fresh ? { kind: 'device', entity: fresh } : null
    }
    case 'process': {
      const fresh = payload.processes.find((p) => p.id === selected.entity.id)
      return fresh ? { kind: 'process', entity: fresh } : null
    }
    case 'connection': {
      const fresh = payload.connections.find((c) => c.id === selected.entity.id)
      return fresh ? { kind: 'connection', entity: fresh } : null
    }
  }
}

export type TwinPhase = 'loading' | 'ready' | 'error'

/** The data source: GET /api/v1/digital-twin/graph, normalized for the mappers. */
export function loadTwinPayload(): Promise<TwinGraphPayload> {
  return twinApi.getTwinGraph().then((res) => normalizeTwinPayload(res.data))
}

const POLL_MS = 30_000

/**
 * Phase hook for the twin screen. Two refresh shapes, per the spec's state
 * table: `reload` (first mount, retry, manual reload) drops back to the
 * Loading skeleton, while the 30 s poll while Ready refreshes in place —
 * the last valid graph stays up, and a failed refresh surfaces its error
 * without ever blanking the canvas.
 */
export function useTwinGraph(): {
  payload: TwinGraphPayload | null
  phase: TwinPhase
  /** a background refresh is in flight; the graph stays visible and live */
  refreshing: boolean
  error: string | null
  reload: () => void
} {
  const [payload, setPayload] = useState<TwinGraphPayload | null>(null)
  const [phase, setPhase] = useState<TwinPhase>('loading')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestRef = useRef(0)
  const liveRef = useRef(true)
  useEffect(() => {
    // StrictMode's simulated unmount disarms this guard; the second (real)
    // mount must re-arm it or every response is discarded and the screen
    // sits in Loading forever.
    liveRef.current = true
    return () => {
      liveRef.current = false
    }
  }, [])

  const run = useCallback(async (mode: 'full' | 'refresh') => {
    const req = ++requestRef.current
    if (mode === 'full') {
      setPhase('loading')
      setError(null)
    } else {
      setRefreshing(true)
    }
    try {
      const next = await loadTwinPayload()
      if (!liveRef.current || req !== requestRef.current) return
      setPayload(next)
      setPhase('ready')
      setError(null)
    } catch (e) {
      if (!liveRef.current || req !== requestRef.current) return
      setError((e as { message?: string })?.message || 'Failed to load the twin graph')
      if (mode === 'full') setPhase('error')
    } finally {
      // a request that superseded an in-flight refresh clears its flag too
      if (liveRef.current && req === requestRef.current) setRefreshing(false)
    }
  }, [])

  const reload = useCallback(() => {
    void run('full')
  }, [run])

  useEffect(() => {
    void run('full')
  }, [run])

  useEffect(() => {
    if (phase !== 'ready') return
    const id = setInterval(() => {
      void run('refresh')
    }, POLL_MS)
    return () => clearInterval(id)
  }, [phase, run])

  return { payload, phase, refreshing, error, reload }
}

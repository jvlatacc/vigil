import { describe, expect, it, vi } from 'vitest'
import {
  buildTwinGraph,
  connectionTupleLabel,
  deriveTalksToEdges,
  filterTwinGraph,
  normalizeTwinPayload,
  resolveSelection,
  DEVICE_X,
  PROCESS_X,
  CONNECTION_X,
  type TwinConnectionFlowNode,
  type TwinDeviceFlowNode,
  type TwinEdgeKind,
  type TwinFlowEdge,
  type TwinNodeData,
  type TwinProcessFlowNode,
} from './useTwinGraph'
import { DEMO_TWIN_PAYLOAD as DEMO } from './fixtures'
import type { Schema } from '../../services/apiTypes'
import type { TwinConnection, TwinDevice, TwinGraphPayload } from './types'

// The mappers only touch MarkerType; the full canvas is mocked in TwinGraph.test.tsx
vi.mock('@xyflow/react', () => ({ MarkerType: { ArrowClosed: 'arrow' } }))

const byKind = (edges: TwinFlowEdge[], kind: TwinEdgeKind) => edges.filter((e) => e.data?.kind === kind)

describe('twin graph mappers', () => {
  it('maps the payload to one node per entity, carrying its attributes', () => {
    const { nodes } = buildTwinGraph(DEMO)
    expect(nodes.filter((n) => n.type === 'device')).toHaveLength(DEMO.devices.length)
    expect(nodes.filter((n) => n.type === 'process')).toHaveLength(DEMO.processes.length)
    expect(nodes.filter((n) => n.type === 'connection')).toHaveLength(DEMO.connections.length)

    const web = nodes.find((n) => n.id === 'dev-web-01') as TwinDeviceFlowNode
    expect(web.data.entity.mac_address).toBe('0a:1b:2c:3d:4e:01')
    expect(web.data.entity.serial_number).toBe('C02X1234ABCD')
    expect(web.data.entity.device_type).toBe('server')

    const ps = nodes.find((n) => n.id === 'proc-ws-jvl-5520') as TwinProcessFlowNode
    expect(ps.data.entity.pid).toBe(5520)
    expect(ps.data.entity.name).toBe('powershell')

    const conn = nodes.find((n) => n.id === 'conn-13') as TwinConnectionFlowNode
    expect(conn.data.entity.connection_type).toBe('socket')
    expect(conn.data.entity.remote_ip).toBe('10.0.9.44')
  })

  it('derives runs, binds, and heuristic talks-to edges', () => {
    const { edges } = buildTwinGraph(DEMO)
    // every process hangs off its device
    expect(byKind(edges, 'runs')).toHaveLength(DEMO.processes.length)
    // every attributed connection hangs off its process; conn-02 is unattributed
    expect(byKind(edges, 'binds')).toHaveLength(DEMO.connections.filter((c) => c.process_id).length)

    // deduped cross-device pairs: web→ws, web→cam, web→db, db→web, db→ws, ws→web, ws→db, cam→ws
    const talks = byKind(edges, 'talks-to')
    expect(talks).toHaveLength(8)

    const wsToDb = talks.find((e) => e.source === 'dev-ws-jvl' && e.target === 'dev-db-01')
    expect(wsToDb?.data).toEqual({ kind: 'talks-to', heuristic: true })
    expect(wsToDb?.label).toBe('talks-to')

    // two db-01 connections to the workstation collapse into one edge
    expect(talks.filter((e) => e.source === 'dev-db-01' && e.target === 'dev-ws-jvl')).toHaveLength(1)
    // the camera's own-IP socket makes no self edge; the C2 remote is not a known device
    expect(edges.every((e) => e.source !== e.target)).toBe(true)
    expect(talks.some((e) => e.source === 'dev-cam-loading' && e.target === 'dev-cam-loading')).toBe(false)
  })

  it('never derives talks-to for devices without a known ip', () => {
    const devices: TwinDevice[] = [{ ...DEMO.devices[0], ip_address: null }]
    const connections: TwinConnection[] = [{ ...DEMO.connections[0], remote_ip: '10.0.4.11' }]
    expect(deriveTalksToEdges(devices, connections)).toEqual([])
  })

  it('layer filter prunes node classes and never leaves a dangling edge', () => {
    const built = buildTwinGraph(DEMO)

    const physical = filterTwinGraph(built.nodes, built.edges, 'physical')
    expect(physical.nodes.every((n) => n.type === 'device')).toBe(true)
    expect(physical.edges.every((e) => e.data?.kind === 'talks-to')).toBe(true)
    expect(physical.edges).toHaveLength(8)

    const logical = filterTwinGraph(built.nodes, built.edges, 'logical')
    expect(logical.nodes.every((n) => n.type === 'process' || n.type === 'connection')).toBe(true)
    expect(logical.nodes).toHaveLength(DEMO.processes.length + DEMO.connections.length)
    expect(logical.edges.some((e) => e.data?.kind === 'talks-to')).toBe(false)

    expect(filterTwinGraph(built.nodes, built.edges, 'all')).toEqual({ nodes: built.nodes, edges: built.edges })
  })

  it('layout is deterministic and independent of payload order', () => {
    const first = buildTwinGraph(DEMO)
    expect(buildTwinGraph(DEMO)).toEqual(first)

    const shuffled: TwinGraphPayload = {
      ...DEMO,
      devices: [...DEMO.devices].reverse(),
      processes: [...DEMO.processes].reverse(),
      connections: [...DEMO.connections].reverse(),
    }
    expect(buildTwinGraph(shuffled)).toEqual(first)

    // devices left, processes middle, connections right
    for (const n of first.nodes) {
      if (n.type === 'device') expect(n.position.x).toBe(DEVICE_X)
      if (n.type === 'process') expect(n.position.x).toBe(PROCESS_X)
      if (n.type === 'connection') expect(n.position.x).toBe(CONNECTION_X)
    }
    // stable y-ordering: rows descend by natural key within each column
    for (const kind of ['device', 'process', 'connection'] as const) {
      const ys = first.nodes.filter((n) => n.type === kind).map((n) => n.position.y)
      expect([...ys].sort((a, b) => a - b)).toEqual(ys)
    }
  })

  it('reads the tuple label in the direction of the traffic', () => {
    const base = DEMO.connections[0]
    expect(connectionTupleLabel(base)).toBe('tcp 10.0.7.31:52341 → 10.0.4.11:443')
    expect(connectionTupleLabel({ ...base, direction: 'outbound', protocol: null })).toBe('10.0.4.11:443 → 10.0.7.31:52341')
  })

  it('maps an empty payload to an empty graph', () => {
    const empty: TwinGraphPayload = { generated_at: '2026-10-09T00:00:00Z', devices: [], processes: [], connections: [] }
    expect(buildTwinGraph(empty)).toEqual({ nodes: [], edges: [] })
  })
})

describe('normalizeTwinPayload', () => {
  // the wire shape the API PR ships: optional lists, untyped uuid ids, extra
  // inventory fields the screen deliberately drops
  const wireDevice = {
    ...DEMO.devices[0],
    device_key: 'seed:0a:1b:2c:3d:4e:01',
    os_info: null,
    attributes: null,
  }
  const wirePayload = (over: Partial<Schema<'TwinGraphPayload'>> = {}): Schema<'TwinGraphPayload'> => ({
    generated_at: '2026-10-10T08:00:00Z',
    devices: [wireDevice],
    processes: [DEMO.processes[0]],
    connections: [DEMO.connections[0]],
    ...over,
  })

  it('normalizes the wire DTO into the screen payload', () => {
    const payload = normalizeTwinPayload(wirePayload())
    expect(payload.generated_at).toBe('2026-10-10T08:00:00Z')
    expect(payload.devices).toHaveLength(1)
    expect(payload.devices[0]).toEqual(DEMO.devices[0])
    expect(payload.processes).toEqual([DEMO.processes[0]])
    expect(payload.connections).toEqual([DEMO.connections[0]])
  })

  it('defaults the optional entity lists to empty arrays', () => {
    const payload = normalizeTwinPayload({ generated_at: '2026-10-10T08:00:00Z' })
    expect(payload).toEqual({ generated_at: '2026-10-10T08:00:00Z', devices: [], processes: [], connections: [] })
  })

  it('falls back to unknown for free-form enum fields instead of lying', () => {
    const payload = normalizeTwinPayload(wirePayload({ devices: [{ ...wireDevice, device_type: 'printer' }] }))
    expect(payload.devices[0]?.device_type).toBe('unknown')
  })
})

describe('resolveSelection', () => {
  const web = DEMO.devices.find((d) => d.id === 'dev-web-01')!
  const deviceSelection = (entity: TwinDevice = web): TwinNodeData => ({ kind: 'device', entity })

  it('keeps the selection and hands back the fresh entity when the payload still names it', () => {
    const bumped: TwinDevice = { ...web, last_seen: '2026-10-10T09:00:00Z' }
    const payload: TwinGraphPayload = { generated_at: '2026-10-10T09:00:00Z', devices: [bumped], processes: [], connections: [] }
    expect(resolveSelection(payload, deviceSelection(web))).toEqual({ kind: 'device', entity: bumped })
  })

  it('closes the panel when a refresh dropped the selected entity', () => {
    const payload: TwinGraphPayload = { generated_at: '2026-10-10T09:00:00Z', devices: [], processes: [], connections: [] }
    expect(resolveSelection(payload, deviceSelection())).toBeNull()
    expect(resolveSelection(null, deviceSelection())).toBeNull()
    expect(resolveSelection({ ...DEMO }, null)).toBeNull()
  })
})

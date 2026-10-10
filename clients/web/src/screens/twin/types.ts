/**
 * Wire types for the digital-twin graph, mirroring the spec's graph payload
 * ("Digital Twin Graph — VigilSOC Spec"): devices, processes, and connections
 * observed per host. The mappers in `useTwinGraph.ts` derive React Flow nodes
 * and three edge families (`runs | binds | talks-to`) from these lists.
 *
 * Datetimes serialize as ISO-8601 strings over the wire.
 */

/** Physical class of a device; `unknown` when the source could not classify it. */
export type TwinDeviceType = 'server' | 'workstation' | 'appliance' | 'iot' | 'container_host' | 'unknown'

/** What a logical connection is: a raw socket, a long-lived stream, or a session. */
export type TwinConnectionType = 'socket' | 'stream' | 'session'

export type TwinDirection = 'inbound' | 'outbound'

export interface TwinDevice {
  id: string
  hostname?: string | null
  /** Normalized `aa:bb:cc:dd:ee:ff`. */
  mac_address?: string | null
  serial_number?: string | null
  device_type: TwinDeviceType
  /** Last known IP — the only field the v1 talks-to heuristic matches on. */
  ip_address?: string | null
  /** Where the observation came from: "seed", "darktrace", "medic", … */
  source: string
  first_seen: string
  last_seen: string
}

export interface TwinProcess {
  id: string
  device_id: string
  pid: number
  name: string
  user?: string | null
  command?: string | null
  /** Where the observation came from: "seed", "darktrace", "medic", … */
  source: string
  first_seen: string
  last_seen: string
}

export interface TwinConnection {
  id: string
  device_id: string
  /** Owning process, when the source could attribute it. */
  process_id?: string | null
  connection_type: TwinConnectionType
  protocol?: string | null
  local_ip?: string | null
  local_port?: number | null
  remote_ip?: string | null
  remote_port?: number | null
  state?: string | null
  direction?: TwinDirection | null
  source: string
  first_seen: string
  last_seen: string
}

/** The whole graph in one payload; every node carries its entity attributes. */
export interface TwinGraphPayload {
  generated_at: string
  devices: TwinDevice[]
  processes: TwinProcess[]
  connections: TwinConnection[]
}

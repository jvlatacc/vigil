import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { format } from 'date-fns'
import { EmptyState } from '../../shared/ui'
import { Icon } from '../../shared/icons'
import type { ConsoleScreenProps } from '../../shared/types'
import TwinGraph from './TwinGraph'
import {
  connectionTupleLabel,
  resolveSelection,
  useTwinGraph,
  type TwinLayer,
  type TwinNodeData,
} from './useTwinGraph'
import type { TwinConnection, TwinDevice, TwinProcess } from './types'

/**
 * The twin screen (spec: "Digital Twin Graph — VigilSOC Spec", Console screen
 * + state table): a read-only graph mapping the physical layer — devices with
 * MAC and serial — to the logical layer of processes and network connections
 * running on them. Read-only in v1: analysts filter, pivot, and inspect.
 *
 * States, per the spec table: Loading (skeleton), Ready, Refreshing (30 s
 * poll — the graph never blanks), Empty (callout naming both ways data
 * arrives), Error (callout with retry; a refresh that fails over a live
 * graph keeps the graph and shows the strip instead).
 */

const LAYERS: TwinLayer[] = ['all', 'physical', 'logical']
const LAYER_LABEL: Record<TwinLayer, string> = { all: 'All', physical: 'Physical', logical: 'Logical' }

const SEED_HINT = 'scripts/seed_digital_twin_demo.py'

const INGEST_EXAMPLE = `curl -X POST "$VIGIL_URL/api/v1/digital-twin/ingest" \\
  -H "Content-Type: application/json" \\
  -d '{"source":"my-feed","devices":[{"hostname":"web-01","mac_address":"0a:1b:2c:3d:4e:01","device_type":"server","ip_address":"10.0.4.11"}]}'`

const fmtStamp = (iso: string | null | undefined): string => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : format(d, 'MMM d HH:mm:ss')
}

const plural = (noun: string): string => (noun === 'process' ? 'processes' : `${noun}s`)
const countLabel = (n: number, noun: string): string => `${n} ${n === 1 ? noun : plural(noun)}`

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-0 flex-1 items-center justify-center p-6">{children}</div>
}

/** The spec's Loading state: skeleton canvas with a faint grid; nav stays live. */
function TwinSkeleton() {
  return (
    <div className="relative flex min-h-0 flex-1 items-center justify-center">
      <div
        aria-hidden
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            'linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />
      <div className="relative">
        <EmptyState icon="graph" loading title="Loading the twin graph" body="Reading devices, processes, and connections." />
      </div>
    </div>
  )
}

function DetailRows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div>
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-3 py-1.5">
          <span className="shrink-0 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-tx-3">{label}</span>
          <span className="min-w-0 break-words text-right font-mono text-[11px] text-tx-2">
            {value === null || value === undefined || value === '' ? '—' : value}
          </span>
        </div>
      ))}
    </div>
  )
}

function DeviceDetail({ d }: { d: TwinDevice }) {
  return (
    <DetailRows
      rows={[
        ['MAC', d.mac_address],
        ['Serial', d.serial_number],
        ['Type', d.device_type],
        ['IP (last seen)', d.ip_address],
        ['Source', d.source],
        ['First seen', fmtStamp(d.first_seen)],
        ['Last seen', fmtStamp(d.last_seen)],
      ]}
    />
  )
}

function ProcessDetail({ p }: { p: TwinProcess }) {
  return (
    <DetailRows
      rows={[
        ['PID', p.pid],
        ['User', p.user],
        ['Command', p.command],
        ['First seen', fmtStamp(p.first_seen)],
        ['Last seen', fmtStamp(p.last_seen)],
      ]}
    />
  )
}

function ConnectionDetail({ c }: { c: TwinConnection }) {
  return (
    <DetailRows
      rows={[
        ['Type', c.connection_type],
        ['Protocol', c.protocol],
        ['Local', c.local_ip ? `${c.local_ip}:${c.local_port ?? '?'}` : null],
        ['Remote', c.remote_ip ? `${c.remote_ip}:${c.remote_port ?? '?'}` : null],
        ['Traffic', connectionTupleLabel(c)],
        ['State', c.state],
        ['Direction', c.direction],
        ['Source', c.source],
        ['First seen', fmtStamp(c.first_seen)],
        ['Last seen', fmtStamp(c.last_seen)],
      ]}
    />
  )
}

function DetailPanel({ data, onClose }: { data: TwinNodeData; onClose: () => void }) {
  const heading =
    data.kind === 'device'
      ? data.entity.hostname || data.entity.id
      : data.kind === 'process'
        ? `${data.entity.name} (pid ${data.entity.pid})`
        : connectionTupleLabel(data.entity)
  return (
    <aside aria-label="Node details" className="flex w-80 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="rounded border border-line bg-bg-3 px-1.5 py-px text-[9.5px] font-bold uppercase tracking-[0.06em] text-tx-3">
          {data.kind}
        </span>
        <button type="button" onClick={onClose} aria-label="Close details" className="text-tx-3 hover:text-tx">
          <Icon name="close" size={14} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        <h3 className="mb-1 truncate text-[13px] font-bold text-tx">{heading}</h3>
        {data.kind === 'device' && <DeviceDetail d={data.entity} />}
        {data.kind === 'process' && <ProcessDetail p={data.entity} />}
        {data.kind === 'connection' && <ConnectionDetail c={data.entity} />}
      </div>
    </aside>
  )
}

export default function DigitalTwinScreen({ setViewFull }: ConsoleScreenProps) {
  const { payload, phase, refreshing, error, reload } = useTwinGraph()
  const [layer, setLayer] = useState<TwinLayer>('all')
  const [selected, setSelected] = useState<TwinNodeData | null>(null)
  const [copied, setCopied] = useState(false)

  // the graph canvas is full-bleed for as long as the screen is mounted
  useEffect(() => {
    setViewFull(true)
    return () => setViewFull(false)
  }, [setViewFull])

  // a refresh must not slam the panel shut on the analyst: the selection
  // survives while the payload still names the entity, and closes the moment
  // it doesn't
  const selection = useMemo(() => resolveSelection(payload, selected), [payload, selected])

  const copyExample = () => {
    const clip = navigator.clipboard
    if (!clip) return
    clip.writeText(INGEST_EXAMPLE)
      .then(() => setCopied(true))
      .catch(() => setCopied(false))
  }

  const devices = payload?.devices.length ?? 0
  const processes = payload?.processes.length ?? 0
  const connections = payload?.connections.length ?? 0
  const isEmpty = phase === 'ready' && !!payload && devices + processes + connections === 0
  const hasGraph = !!payload && devices + processes + connections > 0

  let body: ReactNode
  if (phase === 'loading') {
    body = <TwinSkeleton />
  } else if (phase === 'error' && !payload) {
    body = (
      <Centered>
        <EmptyState
          icon="alert"
          error
          title="Couldn't load the digital twin"
          body={error ?? 'The twin graph endpoint did not answer.'}
          primary={{ label: 'Retry', onClick: reload, icon: 'refresh' }}
        />
      </Centered>
    )
  } else if (isEmpty) {
    body = (
      <Centered>
        <EmptyState
          icon="graph"
          title="No twin data yet"
          body={
            <>
              Run <code className="font-mono text-[11px] text-accent">{SEED_HINT}</code> for a demo
              topology, or POST device, process, and connection observations to{' '}
              <code className="font-mono text-[11px] text-accent">/api/v1/digital-twin/ingest</code>.
            </>
          }
          primary={{ label: 'Retry', onClick: reload, icon: 'refresh' }}
          secondary={{ label: copied ? 'Copied' : 'Copy ingest example', onClick: copyExample, icon: 'copy' }}
        />
      </Centered>
    )
  } else if (hasGraph && payload) {
    body = (
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <TwinGraph payload={payload} layer={layer} onNodeSelect={setSelected} />
        </div>
        {selection && <DetailPanel data={selection} onClose={() => setSelected(null)} />}
      </div>
    )
  } else {
    body = null
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-[22px] py-[10px]">
        <label className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-tx-3">
          Layer
          <select
            value={layer}
            onChange={(e) => setLayer(e.target.value as TwinLayer)}
            aria-label="Layer"
            className="rounded border border-line bg-panel px-2 py-1 text-[11px] normal-case tracking-normal text-tx-2"
          >
            {LAYERS.map((l) => (
              <option key={l} value={l}>
                {LAYER_LABEL[l]}
              </option>
            ))}
          </select>
        </label>
        <span className="text-[11px] text-tx-3" role="status" aria-live="polite">
          {refreshing ? 'Refreshing…' : payload ? `Updated ${fmtStamp(payload.generated_at)}` : ''}
        </span>
        {payload && (
          <span className="text-[11px] text-tx-3">
            {[countLabel(devices, 'device'), countLabel(processes, 'process'), countLabel(connections, 'connection')].join(' · ')}
          </span>
        )}
        <button type="button" className="btn ghost ml-auto" onClick={reload} disabled={phase === 'loading'}>
          <Icon name="refresh" size={13} /> Refresh
        </button>
      </div>

      {/* a failed refresh never blanks the canvas: the strip explains, the last
          good graph stays up, and Retry runs a full reload */}
      {phase !== 'loading' && error && payload && (
        <div role="alert" className="flex items-center gap-2 border-b border-line bg-crit-dim px-[22px] py-1.5 text-[11px] text-tx-2">
          <span className="min-w-0 truncate">Refresh failed: {error} — showing the last good graph.</span>
          <button type="button" className="btn ghost shrink-0" onClick={reload}>
            Retry
          </button>
        </div>
      )}

      {body}
    </div>
  )
}

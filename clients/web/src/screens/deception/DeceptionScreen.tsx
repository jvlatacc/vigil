import { useState } from 'react'
import type { DeceptionLease } from '../../services/api'
import { Icon } from '../../shared/icons'
import { ConfirmDialog, EmptyState, Field, Select, TextInput } from '../../shared/ui'
import { fmtClock, fmtCountdown } from './fmt'
import { useDeception, useProbes } from './useDeception'

const OPEN_STATUSES = new Set(['pending', 'active'])

// colour rides on top of the shared label; the word carries the meaning
const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--high)',
  active: 'var(--ok)',
  released: 'var(--tx-3)',
  failed: 'var(--crit)',
}

const errText = (e: unknown, fallback: string): string =>
  (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail?.toString?.() ||
  (e as { message?: string })?.message ||
  fallback

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color }}
    >
      <i className="sla-dot" style={{ background: color }} />
      {label}
    </span>
  )
}

/** Where suspicious sources are being steered: the posture summary, the lease
 *  table with live TTL countdowns, the probe log, and the kill switch. The
 *  v1 screen reads what the spine persists; decoy-session intel joins the
 *  probe log when the decoy farm reports through the webhook ingest. */
export default function DeceptionScreen() {
  const { status, leases, phase, error, now, reload, release, setKillSwitch } = useDeception()
  const [switchAction, setSwitchAction] = useState<'engage' | 'release' | null>(null)
  const [switchReason, setSwitchReason] = useState('')
  const [switchBusy, setSwitchBusy] = useState(false)
  const [switchError, setSwitchError] = useState('')
  const [releaseTarget, setReleaseTarget] = useState<DeceptionLease | null>(null)
  const [releaseReason, setReleaseReason] = useState('')
  const [releaseBusy, setReleaseBusy] = useState(false)
  const [releaseError, setReleaseError] = useState('')
  const [intelSource, setIntelSource] = useState<string | null>(null)

  if (phase === 'loading') {
    return <EmptyState loading title="Loading the deception posture…" />
  }
  if (phase === 'error' || !status) {
    return (
      <EmptyState
        error
        title="Couldn't load the deception posture"
        body={error}
        secondary={{ label: 'Retry', onClick: () => reload() }}
      />
    )
  }

  const openLeases = leases.filter((l) => OPEN_STATUSES.has(l.status))
  const terminalLeases = leases.filter((l) => !OPEN_STATUSES.has(l.status)).slice(0, 25)
  const dryRun = status.backend === 'dry_run'

  const handleSwitch = async () => {
    if (!switchAction) return
    setSwitchBusy(true)
    setSwitchError('')
    try {
      await setKillSwitch(switchAction === 'engage', switchReason.trim() || undefined)
      setSwitchAction(null)
      setSwitchReason('')
    } catch (e) {
      setSwitchError(errText(e, 'Failed to set the kill switch'))
    } finally {
      setSwitchBusy(false)
    }
  }

  const handleRelease = async () => {
    if (!releaseTarget) return
    setReleaseBusy(true)
    setReleaseError('')
    try {
      await release(releaseTarget.lease_id, releaseReason.trim() || undefined)
      setReleaseTarget(null)
      setReleaseReason('')
    } catch (e) {
      setReleaseError(errText(e, 'Failed to release the lease'))
    } finally {
      setReleaseBusy(false)
    }
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Posture strip */}
      <div className="card card-sq p-3 flex items-center gap-5 flex-wrap">
        <Chip label={status.enabled ? 'Posture enabled' : 'Posture disabled'} color={status.enabled ? 'var(--ok)' : 'var(--tx-3)'} />
        <Chip label={dryRun ? 'Dry run — records intent only' : `Backend: ${status.backend}`} color={dryRun ? 'var(--high)' : 'var(--accent)'} />
        <Chip
          label={status.kill_switch_active ? 'Kill switch engaged' : 'Kill switch off'}
          color={status.kill_switch_active ? 'var(--crit)' : 'var(--tx-3)'}
        />
        <span className="text-xs text-tx-3">{openLeases.length} active lease{openLeases.length === 1 ? '' : 's'}</span>
        <div className="flex-1" />
        <button className="btn ghost icon" title="Refresh" aria-label="Refresh" onClick={() => reload()}>
          <Icon name="refresh" />
        </button>
      </div>

      {status.backend_error && (
        <div className="settings-banner err">
          <Icon name="alert" size={14} /> Steering backend unavailable: {status.backend_error}
        </div>
      )}

      {/* Kill switch */}
      {status.kill_switch_active ? (
        <div className="settings-banner err justify-between flex items-center gap-3">
          <span className="flex items-center gap-2">
            <Icon name="alert" size={14} /> Kill switch engaged — new steering is stopped and
            leases are not renewed. Releases still work. If an environment override set this,
            releasing here will not stick.
          </span>
          <button className="btn ghost" onClick={() => setSwitchAction('release')} disabled={switchBusy}>
            Release kill switch
          </button>
        </div>
      ) : (
        <div className="flex justify-end">
          <button className="btn danger" onClick={() => setSwitchAction('engage')} disabled={switchBusy}>
            <Icon name="alert" size={14} /> Engage kill switch
          </button>
        </div>
      )}

      {/* Active leases */}
      <section className="card card-sq">
        <div className="card-h">
          <div className="settings-card-head">
            <h3>Active leases</h3>
          </div>
        </div>
        <div className="card-b">
          {openLeases.length === 0 ? (
            <EmptyState
              compact
              table
              icon="shield"
              title="No leases — nothing is steered."
              body="The posture is off by default. Corroborated recon sources are steered into decoys only while the posture is enabled in Settings › Deception."
            />
          ) : (
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Attacker</th>
                    <th>Steered to decoys</th>
                    <th>Ports</th>
                    <th>TTL</th>
                    <th>Renewals</th>
                    <th>Backend ref</th>
                    <th>Status</th>
                    <th aria-label="Release" />
                  </tr>
                </thead>
                <tbody>
                  {openLeases.map((l) => (
                    <tr key={l.lease_id}>
                      <td className="font-mono text-xs">{l.attacker_ip}</td>
                      <td className="font-mono text-xs">{l.destination_ips.join(', ') || '—'}</td>
                      <td className="font-mono text-xs">{l.ports.join(', ') || '—'}</td>
                      <td>{fmtCountdown(l.expires_at, now)}</td>
                      <td>{l.renewal_count}</td>
                      <td className="font-mono text-xs" title={l.backend_ref || undefined}>{l.backend_ref || '—'}</td>
                      <td><Chip label={l.status} color={STATUS_COLOR[l.status] || 'var(--tx-3)'} /></td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn ghost"
                          aria-label={`Release the lease for ${l.attacker_ip}`}
                          onClick={() => {
                            setReleaseTarget(l)
                            setReleaseReason('')
                            setReleaseError('')
                          }}
                        >
                          Release
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Captured intel */}
      <section className="card card-sq">
        <div className="card-h">
          <div className="settings-card-head">
            <h3>Captured intel</h3>
          </div>
        </div>
        <div className="card-b flex flex-col gap-3">
          <Field label="Source">
            <Select
              value={intelSource ?? ''}
              options={[
                { value: '', label: 'All recent sources' },
                ...openLeases.map((l) => ({ value: l.attacker_ip, label: l.attacker_ip })),
              ]}
              onSelect={(v) => setIntelSource(v || null)}
            />
          </Field>
          <IntelTable source={intelSource} />
          <p className="text-xs text-tx-3">
            Probes are the recon observations corroboration counts. Decoy-session telemetry —
            commands captured inside the decoys — joins this panel through the same probe log
            once the decoy farm reports sessions to the webhook ingest.
          </p>
        </div>
      </section>

      {/* Recent terminal leases — the audit tail */}
      {terminalLeases.length > 0 && (
        <section className="card card-sq">
          <div className="card-h">
            <div className="settings-card-head">
              <h3>Recent released and failed leases</h3>
            </div>
          </div>
          <div className="card-b">
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Attacker</th>
                    <th>Status</th>
                    <th>Released at</th>
                    <th>Reason</th>
                    <th>Rollback</th>
                  </tr>
                </thead>
                <tbody>
                  {terminalLeases.map((l) => {
                    const rollback = l.rollback_result as { success?: boolean } | null
                    return (
                      <tr key={l.lease_id}>
                        <td className="font-mono text-xs">{l.attacker_ip}</td>
                        <td><Chip label={l.status} color={STATUS_COLOR[l.status] || 'var(--tx-3)'} /></td>
                        <td>{fmtClock(l.released_at)}</td>
                        <td>{l.release_reason || '—'}</td>
                        <td>
                          {rollback ? (
                            rollback.success ? (
                              <Chip label="unsteered" color="var(--ok)" />
                            ) : (
                              <Chip label="rollback failed" color="var(--crit)" />
                            )
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* Kill-switch confirm */}
      <ConfirmDialog
        open={switchAction !== null}
        title={switchAction === 'engage' ? 'Engage the kill switch?' : 'Release the kill switch?'}
        body={
          <div className="flex flex-col gap-3">
            <span>
              {switchAction === 'engage'
                ? 'New steering stops immediately and leases are not renewed. Active redirects stay until released or expired. The switch works even with the daemon down (controller drain).'
                : 'Steering resumes: corroborated recon sources are routed into decoys again.'}
            </span>
            <Field label="Reason (recorded in the audit trail)">
              <TextInput value={switchReason} onChange={(e) => setSwitchReason(e.target.value)} />
            </Field>
            {switchError && <span className="text-sm" style={{ color: 'var(--crit)' }}>{switchError}</span>}
          </div>
        }
        confirmLabel={switchAction === 'engage' ? 'Engage' : 'Release'}
        busy={switchBusy}
        onConfirm={handleSwitch}
        onClose={() => setSwitchAction(null)}
      />

      {/* Lease release confirm */}
      <ConfirmDialog
        open={releaseTarget !== null}
        title={`Release the lease for ${releaseTarget?.attacker_ip ?? ''}?`}
        body={
          <div className="flex flex-col gap-3">
            <span>The source is unsteered now and its traffic returns to normal paths. The rollback is recorded on the lease.</span>
            <Field label="Reason (recorded in the audit trail)">
              <TextInput value={releaseReason} onChange={(e) => setReleaseReason(e.target.value)} />
            </Field>
            {releaseError && <span className="text-sm" style={{ color: 'var(--crit)' }}>{releaseError}</span>}
          </div>
        }
        confirmLabel="Release"
        busy={releaseBusy}
        onConfirm={handleRelease}
        onClose={() => setReleaseTarget(null)}
      />
    </div>
  )
}

/** The probe log for the selected source — the lease-to-finding linkage. */
function IntelTable({ source }: { source: string | null }) {
  const { probes, phase } = useProbes(source)

  if (phase === 'loading') return <div className="text-sm text-tx-3 py-6 text-center">Loading probes…</div>
  if (phase === 'error') {
    return <div className="text-sm text-tx-3 py-6 text-center">Couldn't read the probe log.</div>
  }
  if (probes.length === 0) {
    return (
      <EmptyState
        compact
        table
        icon="search"
        title="No probes for this source yet."
        body="Recon observations appear as the posture sees them — one per distinct finding, counted toward corroboration."
      />
    )
  }
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>Seen at</th>
            <th>Source</th>
            <th>Finding</th>
            <th>Techniques</th>
            <th>Ports</th>
          </tr>
        </thead>
        <tbody>
          {probes.map((p) => {
            const evidence = (p.evidence || {}) as { tids?: string[]; ports?: number[] }
            return (
              <tr key={p.probe_id}>
                <td>{fmtClock(p.created_at)}</td>
                <td className="font-mono text-xs">{p.source_ip}</td>
                <td className="font-mono text-xs" title={p.finding_id || undefined}>{p.finding_id || '—'}</td>
                <td className="font-mono text-xs">{(evidence.tids || []).join(', ') || '—'}</td>
                <td className="font-mono text-xs">{(evidence.ports || []).join(', ') || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

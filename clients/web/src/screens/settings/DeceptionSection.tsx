import { useEffect, useMemo, useState } from 'react'
import type { DeceptionStatus } from '../../services/api'
import { Icon } from '../../shared/icons'
import { ConfirmDialog, Field, NumberInput, Select, SettingsCard, TextInput, ToggleRow } from '../../shared/ui'
import { useDeceptionSettings } from './useDeceptionSettings'
import type { SectionProps } from './types'

const BACKENDS = [
  { value: 'dry_run', label: 'Dry run — record intent only (default)' },
  { value: 'controller', label: 'Reference decoy controller (programs nftables / Cilium)' },
]

interface FormState {
  enabled: boolean
  backend: string
  honey_route_floor: number
  ttl_seconds: number
  max_duration_seconds: number
  min_observations: number
  window_seconds: number
  allowlist: string
}

const secondsLabel = (s: number) =>
  s % 3600 === 0 ? `${s / 3600}h` : s % 60 === 0 ? `${s / 60}m` : `${s}s`

const seedForm = (s: DeceptionStatus): FormState => ({
  enabled: s.enabled,
  backend: s.backend,
  honey_route_floor: s.honey_route_floor,
  ttl_seconds: s.ttl_seconds,
  max_duration_seconds: s.max_duration_seconds,
  min_observations: s.min_observations,
  window_seconds: s.window_seconds,
  allowlist: s.allowlist,
})

function errText(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string })?.msg || JSON.stringify(d)).join(', ')
  if (detail && typeof detail === 'object') return (detail as { msg?: string }).msg || JSON.stringify(detail)
  return (e as { message?: string })?.message || fallback
}

/** Settings › Deception: the honey-routing posture — enablement, steering
 *  backend, the decision floor and lease bounds, and the allowlist of sources
 *  that must never be steered. Writes land in the stored `deception.settings`
 *  row, which overrides the environment defaults; what the daemon reads is
 *  re-fetched after every save and shown as the resolved posture. */
export default function DeceptionSection({ notify }: SectionProps) {
  const { status, phase, error, reload, save, setKillSwitch } = useDeceptionSettings()
  const [form, setForm] = useState<FormState | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [switchAction, setSwitchAction] = useState<'engage' | 'release' | null>(null)
  const [switchReason, setSwitchReason] = useState('')
  const [switchBusy, setSwitchBusy] = useState(false)
  const [switchError, setSwitchError] = useState('')

  // seed (and re-seed after save) from the resolved posture, never from a
  // half-written form state
  useEffect(() => {
    if (status) setForm(seedForm(status))
  }, [status])

  const dirty = useMemo(
    () => !!status && !!form && JSON.stringify(seedForm(status)) !== JSON.stringify(form),
    [status, form],
  )

  if (phase === 'loading') {
    return <div className="text-sm text-tx-3 py-16 text-center">Loading the deception posture…</div>
  }
  if (phase === 'error' || !status) {
    return (
      <div className="py-16 text-center flex flex-col items-center gap-2.5">
        <span className="text-sm text-tx-3">Couldn’t load the deception posture: {error}</span>
        <button className="btn ghost" onClick={reload}>Retry</button>
      </div>
    )
  }

  const set = (patch: Partial<FormState>) => setForm((f) => (f ? { ...f, ...patch } : f))

  const handleSave = async () => {
    if (!form) return
    setSaving(true)
    setFormError('')
    try {
      await save({
        enabled: form.enabled,
        backend: form.backend,
        honey_route_floor: form.honey_route_floor,
        ttl_seconds: form.ttl_seconds,
        max_duration_seconds: form.max_duration_seconds,
        min_observations: form.min_observations,
        window_seconds: form.window_seconds,
        allowlist: form.allowlist,
      })
      notify('ok', 'Deception settings saved — the daemon picks them up within a minute.')
    } catch (e) {
      const message = errText(e, 'Failed to save the deception settings')
      setFormError(message)
      notify('err', message)
    } finally {
      setSaving(false)
    }
  }

  const handleSwitch = async () => {
    if (!switchAction) return
    setSwitchBusy(true)
    setSwitchError('')
    try {
      await setKillSwitch(switchAction === 'engage', switchReason.trim() || undefined)
      setSwitchAction(null)
      setSwitchReason('')
      notify('ok', switchAction === 'engage' ? 'Kill switch engaged.' : 'Kill switch released.')
    } catch (e) {
      const message = errText(e, 'Failed to set the kill switch')
      setSwitchError(message)
      notify('err', message)
    } finally {
      setSwitchBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {status.backend === 'dry_run' && (
        <div className="settings-banner info">
          <Icon name="info" size={14} /> Dry run — every steer is recorded as intent only.
          Nothing touches the network until the decoy controller backend is selected and configured.
        </div>
      )}
      {status.kill_switch_active && (
        <div className="settings-banner err">
          <Icon name="alert" size={14} /> Kill switch engaged — new steering is stopped and leases
          are not renewed. Releases still work. If an environment override set this, releasing
          here will not stick.
        </div>
      )}

      <SettingsCard
        title="Posture"
        desc="Honey-routing steers corroborated recon and lateral-probe sources into isolated decoys instead of denying them. Off by default."
      >
        <ToggleRow
          label="Enable the deception posture"
          hint="Corroborated recon sources are routed into decoys on a short TTL lease. Disable to fall back to the normal response behaviour."
          checked={form?.enabled ?? false}
          onChange={(v) => set({ enabled: v })}
          disabled={!form}
        />
        <Field label="Steering backend" hint="The controller backend requires the decoy-controller service, its base URL, and the steering token.">
          <Select
            value={form?.backend ?? 'dry_run'}
            options={BACKENDS}
            onSelect={(v) => set({ backend: v })}
            disabled={!form}
          />
        </Field>
        {form?.backend === 'controller' && (
          <div className="settings-banner info">
            <Icon name="alert" size={14} /> Live steering: redirects are programmed on the network
            path. The controller is never in the production path — a backend outage leaves
            routing untouched — but it does change where attacker traffic lands.
          </div>
        )}
        <p className="text-xs text-tx-3">
          These are the resolved values — what you store here overrides the environment defaults
          (the <code>DAEMON_*</code> variables). The daemon re-reads them within a minute.
        </p>
      </SettingsCard>

      <SettingsCard title="Decision and lease bounds" desc="When the posture acts, and for how long a steer lasts.">
        <Field label={`Honey-route confidence floor (${form?.honey_route_floor ?? '—'})`} hint="Findings at or above this confidence with a corroborated recon signal are steered. The isolate/block bands are untouched.">
          <NumberInput
            value={form?.honey_route_floor ?? 0.8}
            min={0}
            max={1}
            step={0.01}
            onChange={(e) => set({ honey_route_floor: Number(e.target.value) })}
            disabled={!form}
          />
        </Field>
        <Field label={`Lease TTL (${form ? secondsLabel(form.ttl_seconds) : '—'})`} hint="How long one redirect lasts before the daemon releases it.">
          <NumberInput
            value={form?.ttl_seconds ?? 3600}
            min={60}
            step={60}
            onChange={(e) => set({ ttl_seconds: Number(e.target.value) })}
            disabled={!form}
          />
        </Field>
        <Field label={`Max lease duration (${form ? secondsLabel(form.max_duration_seconds) : '—'})`} hint="Renewals cannot extend a lease past this cap.">
          <NumberInput
            value={form?.max_duration_seconds ?? 86400}
            min={3600}
            step={3600}
            onChange={(e) => set({ max_duration_seconds: Number(e.target.value) })}
            disabled={!form}
          />
        </Field>
        <Field label={`Corroboration (${form?.min_observations ?? '—'} probes / ${form ? secondsLabel(form.window_seconds) : '—'})`} hint="Distinct probes from one source inside this window before the posture steers.">
          <NumberInput
            value={form?.min_observations ?? 3}
            min={1}
            onChange={(e) => set({ min_observations: Number(e.target.value) })}
            disabled={!form}
          />
          <NumberInput
            value={form?.window_seconds ?? 3600}
            min={60}
            step={60}
            onChange={(e) => set({ window_seconds: Number(e.target.value) })}
            disabled={!form}
          />
        </Field>
      </SettingsCard>

      <SettingsCard
        title="Allowlist"
        desc="Sources that are never steered — sanctioned scanners, shared NAT ranges. Comma-separated IPs or CIDRs."
      >
        <Field hint="Vigil validates these; unparseable entries are refused on save.">
          <TextInput
            value={form?.allowlist ?? ''}
            onChange={(e) => set({ allowlist: e.target.value })}
            placeholder="10.0.0.0/8, 198.51.100.4"
            disabled={!form}
          />
        </Field>
      </SettingsCard>

      <div className="flex items-center gap-3 justify-end">
        {formError && <span className="text-sm" style={{ color: 'var(--crit)' }}>{formError}</span>}
        <span className="text-xs text-tx-3">{dirty ? 'Unsaved changes' : 'Saved'}</span>
        <button className="btn primary" onClick={handleSave} disabled={!dirty || saving || !form}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      <SettingsCard
        title="Kill switch"
        desc="Stops new steering and lease renewals immediately, without the decision engine. Active redirects are released or left to expire."
        actions={
          status.kill_switch_active ? (
            <button className="btn ghost" onClick={() => { setSwitchAction('release'); setSwitchError('') }} disabled={switchBusy}>
              Release kill switch
            </button>
          ) : (
            <button className="btn danger" onClick={() => { setSwitchAction('engage'); setSwitchError('') }} disabled={switchBusy}>
              Engage kill switch
            </button>
          )
        }
      >
        <p className="text-sm">
          Kill switch is {status.kill_switch_active ? 'engaged' : 'off'}. The controller's drain
          endpoint removes every redirect it created even with Vigil down.
        </p>
      </SettingsCard>

      <ConfirmDialog
        open={switchAction !== null}
        title={switchAction === 'engage' ? 'Engage the kill switch?' : 'Release the kill switch?'}
        body={
          <div className="flex flex-col gap-3">
            <span>
              {switchAction === 'engage'
                ? 'New steering stops immediately and leases are not renewed. Active redirects stay until released or expired.'
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
    </div>
  )
}

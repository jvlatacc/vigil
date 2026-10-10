// Policy compiler settings: the fast-path autonomy flag is read from the
// intent report (declared in INTENT.md, applied at daemon start — not editable
// here); the maturity tunables are DB-backed runtime config edited live.
import { useEffect, useState } from 'react'
import { Field, NumberInput, SettingsCard, ToggleRow } from '../../shared/ui'
import { SectionProps } from './types'
import { useAiOperations, type AIOperationsSettings } from './useSettings'
import { useIntentFlag } from './usePolicyCompilerSettings'

function errorText(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err && 'response' in err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean)
      if (msgs.length) return msgs.join('; ')
    }
  }
  return fallback
}

interface TunableRow {
  field: keyof AIOperationsSettings
  label: string
  hint: string
  min: number
  max: number
  step: number
}

// bounds mirror the server-side Field constraints on the ai-operations model
const TUNABLES: TunableRow[] = [
  { field: 'policy_compiler_min_runs', label: 'Minimum resolved runs', hint: 'Completed runs of the workflow in the window before a pattern may compile', min: 1, max: 1000, step: 1 },
  { field: 'policy_compiler_min_consistency', label: 'Minimum consistency', hint: 'Share of closures that agree (0–1), e.g. 0.9 = 90%', min: 0, max: 1, step: 0.05 },
  { field: 'policy_compiler_window_days', label: 'Evidence window (days)', hint: 'How far back the maturity job looks for evidence', min: 1, max: 365, step: 1 },
  { field: 'policy_compiler_drift_limit', label: 'Drift limit', hint: 'Shadow disagreements or analyst overrides before a policy auto-suspends', min: 1, max: 100, step: 1 },
]

export default function PolicyCompilerSection({ notify }: SectionProps) {
  const { settings, save } = useAiOperations()
  const intentFlag = useIntentFlag('triage.jit_fast_path_enabled')
  const [draft, setDraft] = useState<AIOperationsSettings | null>(settings)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDraft(settings)
  }, [settings])

  const dirty = TUNABLES.some(({ field }) => draft && draft[field] !== settings?.[field])
  const outOfRange = draft
    ? TUNABLES.filter(({ field, min, max }) => {
        const v = draft[field]
        return typeof v === 'number' && (v < min || v > max)
      })
    : []

  const onSave = async () => {
    if (!draft) return
    setBusy(true)
    try {
      await save(draft)
      notify('ok', 'Policy compiler thresholds saved.')
    } catch (e) {
      notify('err', errorText(e, "Couldn't save the policy compiler thresholds."))
    } finally {
      setBusy(false)
    }
  }

  if (intentFlag.phase === 'loading') {
    return <div className="text-sm text-tx-3 py-16 text-center">Loading policy compiler settings…</div>
  }

  return (
    <div className="flex flex-col gap-4 max-w-[720px]">
      <SettingsCard title="JIT fast path" desc="Skips model triage for findings an active compiled policy already decides. Every action it routes toward still waits for a person.">
        <ToggleRow
          label="Fast path enabled"
          hint={
            intentFlag.effective
              ? 'The daemon currently evaluates compiled policies before model triage.'
              : 'Off — every finding pays model triage. Enabled in INTENT.md and applied when the daemon starts.'
          }
          checked={intentFlag.effective === true}
          disabled
          onChange={() => undefined}
        />
        <p className="m-0 text-[12.5px] text-tx-2" role="note">
          {intentFlag.effective === null
            ? 'The daemon has not reported its effective autonomy yet.'
            : `Effective value: ${intentFlag.effective ? 'enabled' : 'disabled'}${
                intentFlag.source ? ` (${intentFlag.source})` : ''
              }. This flag is declared in INTENT.md, not a setting — changing it is a commit to that file plus a daemon restart.`}
        </p>
      </SettingsCard>

      <SettingsCard
        title="Maturity thresholds"
        desc="When the evidence must be strong enough to compile a candidate, and when drift suspends one. Applies live — no restart."
      >
        {TUNABLES.map(({ field, label, hint, min, max, step }) => (
          <Field key={field} label={label} hint={hint}>
            <NumberInput
              min={min}
              max={max}
              step={step}
              value={draft ? String(draft[field]) : ''}
              onChange={(e) =>
                setDraft((cur) => (cur ? { ...cur, [field]: Number(e.target.value) } : cur))
              }
            />
          </Field>
        ))}
        {outOfRange.length > 0 && (
          <p className="m-0 text-[12.5px]" role="alert" style={{ color: 'var(--crit)' }}>
            {outOfRange.map((t) => t.label).join(', ')} {outOfRange.length === 1 ? 'is' : 'are'} outside the allowed range.
          </p>
        )}
        <div className="flex items-center gap-3 mt-1">
          <button className="btn primary" disabled={busy || !dirty || outOfRange.length > 0} onClick={onSave}>
            {busy ? 'Saving…' : 'Save thresholds'}
          </button>
          {dirty && !outOfRange.length && <span className="text-[12.5px] text-tx-3">Unsaved changes</span>}
        </div>
      </SettingsCard>
    </div>
  )
}

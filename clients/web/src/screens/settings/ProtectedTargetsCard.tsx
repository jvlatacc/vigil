// Never-quarantine targets: containment targets unattended response may never
// touch, whatever the confidence. The environment may add entries no one can
// remove here; rows added through this surface tighten the floor, never loosen it.
import { useState, type FormEvent } from 'react'
import { Icon } from '../../shared/icons'
import { ConfirmDialog, Field, Select, SettingsCard, TextInput } from '../../shared/ui'
import { errorText, useProtectedTargets, type ProtectedTargetView } from './useSettings'
import type { SectionProps } from './types'

const KINDS = [
  { value: 'ip', label: 'Address' },
  { value: 'cidr', label: 'Address range' },
  { value: 'hostname_glob', label: 'Hostname pattern' },
  { value: 'role', label: 'Infrastructure role' },
]

const KIND_LABELS: Record<string, string> = Object.fromEntries(KINDS.map((k) => [k.value, k.label]))

const VALUE_PLACEHOLDERS: Record<string, string> = {
  ip: '10.0.0.5',
  cidr: '10.0.0.0/24',
  hostname_glob: '*.corp.example',
  role: 'domain_controller',
}

const EMPTY_HINT =
  'Nothing is protected yet. Add the systems the daemon must never contain on its own — DNS servers, domain controllers, gateways.'

export default function ProtectedTargetsCard({ notify }: SectionProps) {
  const targets = useProtectedTargets()
  const [kind, setKind] = useState('ip')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [pendingRemove, setPendingRemove] = useState<ProtectedTargetView | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (!value.trim() || !reason.trim()) {
      setFormError('A value and a reason are both required — an invariant nobody can explain is one nobody dares remove.')
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await targets.add({ kind, value: value.trim(), reason: reason.trim() })
      setValue('')
      setReason('')
      notify('ok', 'Protected target saved.')
    } catch (err) {
      setFormError(errorText(err, 'Failed to save the protected target.'))
    } finally {
      setBusy(false)
    }
  }

  const confirmRemove = async () => {
    if (!pendingRemove) return
    const target = pendingRemove
    setBusy(true)
    try {
      await targets.remove(target.kind, target.value)
      setPendingRemove(null)
      notify('ok', 'The removal is recorded. The row keeps its history.')
    } catch (err) {
      setPendingRemove(null)
      notify('err', errorText(err, 'Failed to remove the protected target.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingsCard
      wide
      title="Never-quarantine targets"
      desc="Systems unattended containment may never touch, whatever the confidence. The environment may set entries no one can remove here."
    >
      {targets.phase === 'error' ? (
        <div className="settings-banner err">
          <Icon name="alert" size={14} />
          <span>Could not load the never-quarantine list. Nothing has been changed.</span>
          <button className="btn ghost" onClick={targets.reload}>
            Retry
          </button>
        </div>
      ) : targets.phase === 'loading' ? (
        <span className="text-xs text-tx-3">Loading the never-quarantine list…</span>
      ) : (
        <>
          {targets.unparsed.length > 0 && (
            <div className="settings-banner err mb-2">
              <Icon name="alert" size={14} />
              <span>
                These environment entries did not parse, so containment waits for a person until they are fixed:{' '}
                {targets.unparsed.map((raw) => (
                  <code key={raw} className="mx-1">
                    {raw}
                  </code>
                ))}
              </span>
            </div>
          )}
          {targets.targets.length === 0 ? (
            <span className="text-xs text-tx-3">{EMPTY_HINT}</span>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {targets.targets.map((t) => (
                <li key={`${t.kind}:${t.value}`} className="flex items-center justify-between gap-3">
                  <span className="min-w-0">
                    <code className="text-sm">{t.value}</code>
                    <span className="text-xs text-tx-3 ml-2">{KIND_LABELS[t.kind] ?? t.kind}</span>
                    {t.reason && <span className="text-xs text-tx-3 block truncate">{t.reason}</span>}
                  </span>
                  {t.origin === 'environment' || !t.removable ? (
                    <span className="lim-row-tag">
                      <Icon name="lock" size={12} /> Environment
                    </span>
                  ) : (
                    <button className="btn ghost" onClick={() => setPendingRemove(t)}>
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <form className="flex flex-col gap-3 mt-4" onSubmit={submit}>
            <div className="flex items-end gap-3">
              <Field label="What">
                <Select value={kind} options={KINDS} onSelect={setKind} />
              </Field>
              <Field label="Target" hint={`For example ${VALUE_PLACEHOLDERS[kind]}`}>
                <TextInput
                  value={value}
                  placeholder={VALUE_PLACEHOLDERS[kind]}
                  onChange={(e) => setValue(e.target.value)}
                />
              </Field>
              <Field label="Why">
                <TextInput
                  value={reason}
                  placeholder="Why this target may never be contained"
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              <button type="submit" className="btn ghost" disabled={busy}>
                Protect
              </button>
            </div>
            {formError && <span className="field-hint err">{formError}</span>}
          </form>
        </>
      )}
      <ConfirmDialog
        open={pendingRemove != null}
        title={pendingRemove ? `Stop protecting ${pendingRemove.value}?` : ''}
        body="Unattended containment of this target will be allowed again. The removal is recorded, and the row keeps its history."
        confirmLabel="Remove"
        busy={busy}
        onConfirm={confirmRemove}
        onClose={() => setPendingRemove(null)}
      />
    </SettingsCard>
  )
}

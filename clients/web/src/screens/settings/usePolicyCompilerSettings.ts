// The fast-path flag is env-declared (INTENT.md frontmatter, applied at daemon
// start); the maturity tunables are DB-backed runtime config edited live. This
// hook reads the flag's declared/effective state from the intent report so the
// section can say both things without implying the flag is editable here.
import { useCallback, useEffect, useState } from 'react'
import { configApi } from '../../services/api'

export type Phase = 'loading' | 'ready' | 'error'

export interface IntentFlagView {
  declared: boolean | null
  effective: boolean | null
  source: string | null
  phase: Phase
  reload: () => void
}

interface IntentRow {
  key: string
  declared: unknown
  effective: unknown
  source: string
}

/** One INTENT.md knob's declared-vs-effective values, by manifest key. */
export function useIntentFlag(key: string): IntentFlagView {
  const [declared, setDeclared] = useState<boolean | null>(null)
  const [effective, setEffective] = useState<boolean | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    configApi
      .getIntent()
      .then((res) => {
        if (cancelled) return
        const rows = (res.data as { rows?: IntentRow[] }).rows ?? []
        const row = rows.find((r) => r.key === key)
        setDeclared(typeof row?.declared === 'boolean' ? row.declared : null)
        setEffective(typeof row?.effective === 'boolean' ? row.effective : null)
        setSource(row?.source ?? null)
        setPhase('ready')
      })
      .catch(() => {
        if (!cancelled) setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [key, reloadKey])

  return { declared, effective, source, phase, reload }
}

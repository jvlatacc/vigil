import { useCallback, useEffect, useState } from 'react'
import {
  deceptionApi,
  type DeceptionSettingsWrite,
  type DeceptionStatus,
} from '../../services/api'

export type Phase = 'loading' | 'ready' | 'error'

/**
 * The Settings › Deception data: the resolved posture (stored row over env,
 * read through the same endpoint the daemon's decision path uses) plus the
 * save and kill-switch calls. `save` re-reads the resolved posture so the
 * section shows what will actually govern the next decision.
 */
export function useDeceptionSettings() {
  const [status, setStatus] = useState<DeceptionStatus | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setPhase((p) => (p === 'ready' ? p : 'loading'))
    setError(null)
    deceptionApi
      .getStatus()
      .then((res) => {
        if (cancelled) return
        setStatus(res.data as DeceptionStatus)
        setPhase('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setError((e as { message?: string })?.message || 'Failed to load the deception posture')
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const save = useCallback(async (data: DeceptionSettingsWrite) => {
    await deceptionApi.updateSettings(data)
    const res = await deceptionApi.getStatus()
    setStatus(res.data as DeceptionStatus)
  }, [])

  const setKillSwitch = useCallback(async (enabled: boolean, reason?: string) => {
    await deceptionApi.setKillSwitch(enabled, reason)
    const res = await deceptionApi.getStatus()
    setStatus(res.data as DeceptionStatus)
  }, [])

  return { status, phase, error, reload, save, setKillSwitch }
}

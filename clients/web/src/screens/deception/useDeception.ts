import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deceptionApi,
  type DeceptionLease,
  type DeceptionProbe,
  type DeceptionStatus,
} from '../../services/api'

export type Phase = 'loading' | 'ready' | 'error'

const POLL_MS = 10_000

/**
 * The Deception screen's data: the posture summary, every lease, and the
 * per-source probe log. Status and leases re-poll on a slow interval — the
 * daemon sweeps leases every 30 s, so the screen never shows a stale lease
 * for long — and a one-second ticker drives the TTL countdowns without
 * re-fetching. Poll failures keep the last good data on screen.
 */
export function useDeception() {
  const [status, setStatus] = useState<DeceptionStatus | null>(null)
  const [leases, setLeases] = useState<DeceptionLease[]>([])
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const inFlight = useRef(false)

  const load = useCallback(async (quiet = false) => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      const [statusRes, leasesRes] = await Promise.all([
        deceptionApi.getStatus(),
        deceptionApi.getLeases({ limit: 500 }),
      ])
      setStatus(statusRes.data as DeceptionStatus)
      setLeases((leasesRes.data as { leases: DeceptionLease[] }).leases || [])
      setPhase('ready')
      if (!quiet) setError(null)
    } catch (e) {
      // A quiet poll keeps the last good read; the first load surfaces the error.
      setError((e as { message?: string })?.message || 'Failed to load the deception posture')
      setPhase((p) => (p === 'ready' ? p : 'error'))
    } finally {
      inFlight.current = false
    }
  }, [])

  useEffect(() => {
    load()
    const poll = setInterval(() => load(true), POLL_MS)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      clearInterval(poll)
      clearInterval(tick)
    }
  }, [load])

  const release = useCallback(
    async (leaseId: string, reason?: string) => {
      await deceptionApi.releaseLease(leaseId, reason)
      await load(true)
    },
    [load],
  )

  const setKillSwitch = useCallback(
    async (enabled: boolean, reason?: string) => {
      await deceptionApi.setKillSwitch(enabled, reason)
      await load(true)
    },
    [load],
  )

  return { status, leases, phase, error, now, reload: load, release, setKillSwitch }
}

/** Probes for one source, or the most recent probes across sources when
 *  none is selected — fetched so the intel panel is never blank by default. */
export function useProbes(sourceIp: string | null) {
  const [probes, setProbes] = useState<DeceptionProbe[]>([])
  const [phase, setPhase] = useState<Phase>('loading')

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    deceptionApi
      .getProbes({ source_ip: sourceIp ?? undefined, limit: 100 })
      .then((res) => {
        if (cancelled) return
        setProbes((res.data as { probes: DeceptionProbe[] }).probes || [])
        setPhase('ready')
      })
      .catch(() => !cancelled && setPhase('error'))
    return () => {
      cancelled = true
    }
  }, [sourceIp])

  return { probes, phase }
}

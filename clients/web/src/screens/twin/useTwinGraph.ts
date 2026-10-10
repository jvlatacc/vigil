import { useCallback, useEffect, useRef, useState } from 'react'
import { casesApi, findingsApi, twinApi } from '../../services/api'
import { mapApiFinding, mapQueueCase, type ApiFinding } from '../../data/mappers'
import type { Phase } from '../cases/useCases'
import { mapApiGraph, type TwinGraphVM } from './model'

export type { Phase } from '../cases/useCases'

interface FindingsResponse {
  findings?: ApiFinding[]
}

/** Loads the twin graph together with the rows its nodes join to (findings
 *  for the popovers, cases for their pinned context) and polls every 10 s
 *  like the dashboard. Once a graph exists, a failed fetch — background or
 *  manual — leaves the last valid map on the canvas and surfaces a banner
 *  error; only a first load can land in the error phase. */
export function useTwinGraph() {
  const [graph, setGraph] = useState<TwinGraphVM | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  // ref, not state: the poll interval must not reset when the graph lands
  const hasGraphRef = useRef(false)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false

    const fetchGraph = (silent: boolean) => {
      const hasGraph = hasGraphRef.current
      if (silent || hasGraph) {
        setRefreshing(true)
      } else {
        setPhase('loading')
        setError(null)
      }
      Promise.all([
        twinApi.getGraph(),
        // 'include': the graph already honours exclusions server-side, so
        // the join wants every finding a surviving node can name
        findingsApi.getAll({ limit: 1000, exclusions: 'include' }),
        casesApi.getAll({ limit: 1000 }),
      ])
        .then(([g, f, c]) => {
          if (cancelled) return
          const rows = ((f.data as FindingsResponse | undefined)?.findings ?? []).map(mapApiFinding)
          // getAll returns queue-shaped rows; mapQueueCase is their mapper
          const caseRows = (c.data?.cases ?? []).map(mapQueueCase)
          setGraph(mapApiGraph(g.data, rows, caseRows))
          hasGraphRef.current = true
          setError(null)
          setPhase('ready')
        })
        .catch((e) => {
          if (cancelled) return
          if (hasGraph) {
            // the canvas never blanks: the banner takes the message
            setError((e as { message?: string })?.message || 'Live refresh failed')
            return
          }
          setError((e as { message?: string })?.message || 'Failed to load the twin map')
          setPhase('error')
        })
        .finally(() => {
          if (!cancelled) setRefreshing(false)
        })
    }

    fetchGraph(false)
    const id = setInterval(() => fetchGraph(true), 10_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [reloadKey])

  return { graph, phase, error, refreshing, reload }
}

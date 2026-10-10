// Data for the Compiled Policies screen. The transitions table mirrors the
// server's `_TRANSITIONS` map (policies_router.py) — the UI renders buttons
// from it and the server still enforces every edge (409 on an illegal move).
import { useCallback, useEffect, useState } from 'react'
import {
  compiledPoliciesApi,
  type CompiledPolicySummary,
  type PolicyAgreementCounts,
  type PolicyDecisionRecord,
  type PolicyDecisionsPage,
  type PolicyState,
  type PolicyTransitionAction,
} from '../../services/api'

export type Phase = 'loading' | 'ready' | 'error'

export function errMsg(e: unknown): string {
  const r = e as { response?: { data?: { detail?: string | { msg?: string }[] } }; message?: string }
  const detail = r?.response?.data?.detail
  // a 422 carries a list of {msg} objects, which must not reach the page as is
  const text = Array.isArray(detail) ? detail.map((d) => d?.msg).filter(Boolean).join('; ') : detail
  return text || r?.message || 'Something went wrong'
}

export interface TransitionSpec {
  from: PolicyState[]
  to: PolicyState
  label: string
  danger: boolean
}

/** The lifecycle edges, in the order the console shows them. */
export const TRANSITIONS: Record<PolicyTransitionAction, TransitionSpec> = {
  promote: { from: ['shadow'], to: 'active', label: 'Promote to active', danger: false },
  suspend: { from: ['shadow', 'active'], to: 'suspended', label: 'Suspend', danger: true },
  rearm: { from: ['suspended'], to: 'shadow', label: 'Re-arm to shadow', danger: false },
  retire: { from: ['candidate', 'shadow', 'active', 'suspended'], to: 'retired', label: 'Retire', danger: true },
}

/** Actions a policy in this state may take, in display order. */
export function availableActions(state: PolicyState): PolicyTransitionAction[] {
  const order: PolicyTransitionAction[] = ['promote', 'suspend', 'rearm', 'retire']
  return order.filter((action) => TRANSITIONS[action].from.includes(state))
}

/** Chip color per state, matching the console's severity palette. */
export function policyStateColor(state: PolicyState): string {
  if (state === 'active') return 'var(--ok)'
  if (state === 'suspended') return 'var(--high)'
  if (state === 'shadow') return 'var(--accent)'
  if (state === 'candidate') return 'var(--tx-2)'
  return 'var(--tx-3)' // retired
}

/** The spend-avoided KPI, derived purely from the decision log.
 *  `outcome === 'applied'` is one LLM triage the fast path replaced. */
export interface SpendAvoided {
  /** decisions the fast path acted on — each one an avoided model call */
  avoidedCalls: number
  /** every logged evaluation for the policy, any outcome */
  totalDecisions: number
  /** mean fast-path scan time over applied hits, in microseconds */
  avgEvalUs: number | null
  /** LLM per-call latency is recorded on finding metadata
   *  (ai_triage.duration_ms), not in the decision log, so a model-time-saved
   *  figure is not computable here. False until that changes. */
  llmLatencyInLog: false
}

export function spendAvoided(decisions: PolicyDecisionRecord[]): SpendAvoided {
  const applied = decisions.filter((d) => d.outcome === 'applied')
  const evals = applied.map((d) => d.evaluation_us).filter((v): v is number => v !== null)
  const avg = evals.length
    ? Math.round(evals.reduce((sum, v) => sum + v, 0) / evals.length)
    : null
  return {
    avoidedCalls: applied.length,
    totalDecisions: decisions.length,
    avgEvalUs: avg,
    llmLatencyInLog: false,
  }
}

/** "93% of 14 resolved runs" — the maturity line a list row shows. */
export function maturityLine(p: CompiledPolicySummary): string {
  const outcomes = p.maturity.outcomes ?? {}
  const total = Object.values(outcomes).reduce((sum, n) => sum + n, 0)
  return `${total} runs in ${p.maturity.window_days}d · consistency ${(p.maturity.consistency * 100).toFixed(0)}% · ${p.maturity.analyst_overrides} analyst overrides`
}

/** Truncate a content hash for row display; the full hash rides the title. */
export function shortHash(hash: string | null): string {
  if (!hash) return '—'
  const bare = hash.startsWith('sha256:') ? hash.slice(7) : hash
  return bare.slice(0, 12) + '…'
}

// --- hooks -------------------------------------------------------------------

/** The policy list, optionally filtered by state. */
export function useCompiledPolicies() {
  const [rows, setRows] = useState<CompiledPolicySummary[]>([])
  const [stateFilter, setStateFilter] = useState<PolicyState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    setError(null)
    compiledPoliciesApi
      .list(stateFilter ?? undefined)
      .then((res) => {
        if (cancelled) return
        setRows(res.data.policies)
        setPhase('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setError(errMsg(e))
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [stateFilter, reloadKey])

  return { rows, stateFilter, setStateFilter, phase, error, reload }
}

export interface DecisionsView {
  page: PolicyDecisionsPage | null
  phase: Phase
  error: string | null
  reload: () => void
}

/** The decision log for one policy (all versions), with agreement counts. */
export function usePolicyDecisions(policyId: string | null): DecisionsView {
  const [page, setPage] = useState<PolicyDecisionsPage | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    if (!policyId) {
      setPage(null)
      setPhase('ready')
      setError(null)
      return
    }
    let cancelled = false
    setPhase('loading')
    setError(null)
    compiledPoliciesApi
      .decisions(policyId, { limit: 100 })
      .then((res) => {
        if (cancelled) return
        setPage(res.data)
        setPhase('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setError(errMsg(e))
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [policyId, reloadKey])

  return { page, phase, error, reload }
}

/** One pending lifecycle action's dialog state. */
export interface PendingTransition {
  policy: CompiledPolicySummary
  action: PolicyTransitionAction
}

export interface TransitionOutcome {
  from: CompiledPolicySummary
  action: PolicyTransitionAction
}

/** Runs a transition and reports either the refreshed summary or the
 *  server's refusal (the 409 hash guard, or an illegal edge). */
export async function runTransition(
  pending: PendingTransition
): Promise<CompiledPolicySummary> {
  const res = await compiledPoliciesApi.transition(pending.policy.policy_id, pending.action, {
    version: pending.policy.version,
    content_hash: pending.policy.content_hash,
  })
  return res.data.policy
}

export type { PolicyAgreementCounts, PolicyDecisionRecord, PolicyState }

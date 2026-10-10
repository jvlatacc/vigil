// Unit tests for the Compiled Policies screen's pure helpers: which lifecycle
// buttons a state may show, the KPI math over the decision log, and the
// display shorthands.
import { describe, expect, it } from 'vitest'
import {
  TRANSITIONS,
  availableActions,
  errMsg,
  maturityLine,
  policyStateColor,
  shortHash,
  spendAvoided,
  type PolicyDecisionRecord,
} from './useCompiledPolicies'
import type { CompiledPolicySummary } from '../../services/api'

describe('TRANSITIONS — the lifecycle edges the server enforces', () => {
  it('promotes shadow to active, the only edge that removes human friction', () => {
    expect(TRANSITIONS.promote).toMatchObject({ from: ['shadow'], to: 'active' })
  })
  it('suspends from shadow and active', () => {
    expect(TRANSITIONS.suspend).toMatchObject({ from: ['shadow', 'active'], to: 'suspended' })
  })
  it('re-arms suspended policies back to shadow, never straight to active', () => {
    expect(TRANSITIONS.rearm).toMatchObject({ from: ['suspended'], to: 'shadow' })
  })
  it('retires from every live state', () => {
    expect(TRANSITIONS.retire.from).toEqual(['candidate', 'shadow', 'active', 'suspended'])
    expect(TRANSITIONS.retire.to).toBe('retired')
  })
})

describe('availableActions', () => {
  it('offers promote, suspend and retire on a shadow policy', () => {
    expect(availableActions('shadow')).toEqual(['promote', 'suspend', 'retire'])
  })
  it('offers no actions on a retired policy', () => {
    expect(availableActions('retired')).toEqual([])
  })
  it('offers re-arm and retire on a suspended policy', () => {
    expect(availableActions('suspended')).toEqual(['rearm', 'retire'])
  })
  it('a candidate has only retirement until validation promotes it', () => {
    expect(availableActions('candidate')).toEqual(['retire'])
  })
})

describe('spendAvoided — the KPI over the decision log', () => {
  const decision = (over: Partial<PolicyDecisionRecord>): PolicyDecisionRecord => ({
    id: 1,
    policy_id: 'pol_x',
    policy_version: 1,
    content_hash: 'sha256:ab',
    mode: 'active',
    outcome: 'applied',
    finding_id: 'f_1',
    decision: null,
    actual_decision: null,
    agreement_source: null,
    agrees: null,
    evaluated_at: '2026-10-09T12:00:00Z',
    evaluation_us: 140,
    ...over,
  })

  it('counts applied decisions as avoided LLM calls', () => {
    const rows = [
      decision({ id: 1, outcome: 'applied' }),
      decision({ id: 2, outcome: 'applied' }),
      decision({ id: 3, outcome: 'shadow_observed' }),
      decision({ id: 4, outcome: 'error' }),
    ]
    expect(spendAvoided(rows).avoidedCalls).toBe(2)
    expect(spendAvoided(rows).totalDecisions).toBe(4)
  })

  it('averages evaluation time over applied hits only, ignoring nulls', () => {
    const rows = [
      decision({ id: 1, outcome: 'applied', evaluation_us: 100 }),
      decision({ id: 2, outcome: 'applied', evaluation_us: 300 }),
      decision({ id: 3, outcome: 'applied', evaluation_us: null }),
      decision({ id: 4, outcome: 'shadow_observed', evaluation_us: 9999 }),
    ]
    expect(spendAvoided(rows).avgEvalUs).toBe(200)
  })

  it('reports null averages and zero avoided on an empty log', () => {
    const empty = spendAvoided([])
    expect(empty).toMatchObject({ avoidedCalls: 0, totalDecisions: 0, avgEvalUs: null })
  })
})

describe('display shorthands', () => {
  const summary = {
    maturity: { window_days: 30, consistency: 0.93, analyst_overrides: 0, outcomes: { resolved: 14, false_positive: 1 } },
  } as unknown as CompiledPolicySummary

  it('summarises the maturity evidence as runs, window and consistency', () => {
    expect(maturityLine(summary)).toContain('15 runs in 30d')
    expect(maturityLine(summary)).toContain('consistency 93%')
    expect(maturityLine(summary)).toContain('0 analyst overrides')
  })

  it('truncates the content hash after stripping the algorithm prefix', () => {
    expect(shortHash('sha256:9f2c1a4b7d6e5c3a2b1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b')).toBe(
      '9f2c1a4b7d6e…'
    )
  })

  it('renders a placeholder for a missing hash', () => {
    expect(shortHash(null)).toBe('—')
  })

  it('colors each lifecycle state', () => {
    expect(policyStateColor('active')).not.toBe(policyStateColor('retired'))
    expect(policyStateColor('shadow')).not.toBe(policyStateColor('suspended'))
  })
})

describe('errMsg', () => {
  it('prefers the server detail string', () => {
    expect(errMsg({ response: { data: { detail: 'expected content hash mismatch' } } })).toBe(
      'expected content hash mismatch'
    )
  })
  it('flattens a 422 validation list', () => {
    expect(errMsg({ response: { data: { detail: [{ msg: 'value out of range' }] } } })).toBe(
      'value out of range'
    )
  })
  it('falls back to the axios message, then a generic line', () => {
    expect(errMsg({ message: 'Network Error' })).toBe('Network Error')
    expect(errMsg('boom')).toBe('Something went wrong')
  })
})

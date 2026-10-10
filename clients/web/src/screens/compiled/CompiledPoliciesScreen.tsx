// The Compiled Policies console: the lifecycle and its evidence. Policies are
// read-only evidence plus four human actions — the server owns every edge, so
// the UI only mirrors it and surfaces refusals (the 409 hash guard) verbatim.
import { useMemo, useState } from 'react'
import { Icon } from '../../shared/icons'
import { ConfirmDialog, EmptyState, Popup } from '../../shared/ui'
import { TITLES } from '../../data/data'
import {
  compiledPoliciesApi,
  type CompiledPolicySummary,
  type PolicyExportFormat,
  type PolicyState,
  type PolicyTransitionAction,
} from '../../services/api'
import {
  TRANSITIONS,
  availableActions,
  maturityLine,
  policyStateColor,
  runTransition,
  shortHash,
  spendAvoided,
  useCompiledPolicies,
  usePolicyDecisions,
  errMsg,
  type PendingTransition,
} from './useCompiledPolicies'

const [PAGE_TITLE, PAGE_DESC] = TITLES.policies

const STATES: PolicyState[] = ['candidate', 'shadow', 'active', 'suspended', 'retired']

const EXPORT_FORMATS: { format: PolicyExportFormat; label: string; ext: string }[] = [
  { format: 'rego', label: 'OPA Rego', ext: '.rego' },
  { format: 'snort', label: 'Snort', ext: '.rules' },
  { format: 'suricata', label: 'Suricata', ext: '.rules' },
  { format: 'iptables', label: 'iptables', ext: '.conf' },
]

function StateBadge({ state }: { state: PolicyState }) {
  const color = policyStateColor(state)
  return (
    <span className="status" style={{ background: 'transparent', color, border: `1px solid ${color}55` }}>
      {state}
    </span>
  )
}

function fmtWhen(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

/** A confirmation dialog for one lifecycle action, carrying the version and
 *  the expected content hash — the same values the server checks. */
function TransitionDialog({
  pending,
  busy,
  onClose,
  onConfirm,
}: {
  pending: PendingTransition
  busy: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  const spec = TRANSITIONS[pending.action]
  const p = pending.policy
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={onConfirm}
      busy={busy}
      danger={spec.danger}
      confirmLabel={spec.label}
      title={spec.label}
      body={
        <>
          Policy <strong>{p.policy_id}</strong> version <strong>{p.version}</strong> moves{' '}
          <strong>{p.state}</strong> → <strong>{spec.to}</strong>.
          <br />
          <br />
          Expected content hash (the server refuses the move if the row has since been
          recompiled):
          <br />
          <code style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--tx-2)' }}>
            {p.content_hash}
          </code>
          {pending.action === 'promote' && (
            <>
              <br />
              <br />
              While active this policy writes its triage on every matching finding without a
              model call. Actions it routes toward stay human-only.
            </>
          )}
          {pending.action === 'retire' && (
            <>
              <br />
              <br />
              Retirement is terminal: the policy is kept for audit and its exports stay
              downloadable, but it is never evaluated again.
            </>
          )}
          {pending.action === 'rearm' && (
            <>
              <br />
              <br />
              The policy returns to shadow and must earn a fresh promotion before it writes
              triage again — a re-armed policy never goes straight to active.
            </>
          )}
        </>
      }
    />
  )
}

/** Agreement counters + spend-avoided KPI for one policy's decision log. */
function DecisionEvidence({ policyId }: { policyId: string }) {
  const { page, phase, error, reload } = usePolicyDecisions(policyId)
  const kpi = useMemo(() => spendAvoided(page?.decisions ?? []), [page])

  if (phase === 'loading') return <EmptyState compact loading icon="clock" title="Loading decisions…" />
  if (phase === 'error')
    return (
      <EmptyState
        compact
        error
        icon="alert"
        title="Couldn’t load decisions"
        body={error ?? undefined}
        primary={{ label: 'Retry', onClick: reload, icon: 'refresh' }}
      />
    )
  if (!page) return null

  const a = page.agreement
  return (
    <div className="flex flex-col gap-3 mt-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px] text-tx-2">
        <span title="Findings the fast path triaged without a model call">
          <strong className="text-tx">{kpi.avoidedCalls}</strong> LLM triage calls avoided
        </span>
        <span>
          <strong className="text-tx">{kpi.totalDecisions}</strong> evaluations logged
        </span>
        {kpi.avgEvalUs !== null && (
          <span title="Mean fast-path scan time over applied hits">
            <strong className="text-tx">{kpi.avgEvalUs.toLocaleString()} µs</strong> avg evaluation
          </span>
        )}
        <span title="Decisions whose actual outcome has not landed yet">
          <strong className="text-tx">{a.pending}</strong> pending agreement
        </span>
        <span title="Shadow evaluations that matched the eventual LLM triage">
          LLM: <strong style={{ color: 'var(--ok)' }}>{a.llm.agrees} agree</strong> /{' '}
          <strong style={{ color: 'var(--crit)' }}>{a.llm.disagrees} disagree</strong>
        </span>
        <span title="Policy-triaged closures an analyst agreed with or overrode">
          Analyst: <strong style={{ color: 'var(--ok)' }}>{a.analyst.agrees} agree</strong> /{' '}
          <strong style={{ color: 'var(--crit)' }}>{a.analyst.disagrees} disagree</strong>
        </span>
      </div>
      {page.decisions.length === 0 ? (
        <p className="text-sm text-tx-2 m-0">No evaluations logged yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>When</th>
                <th>Mode</th>
                <th>Outcome</th>
                <th>Finding</th>
                <th>Agreement</th>
                <th>Eval</th>
              </tr>
            </thead>
            <tbody>
              {page.decisions.slice(0, 20).map((d) => (
                <tr key={d.id}>
                  <td>{fmtWhen(d.evaluated_at)}</td>
                  <td>{d.mode}</td>
                  <td>{d.outcome}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{d.finding_id}</td>
                  <td>
                    {d.agreement_source
                      ? `${d.agreement_source}: ${d.agrees ? 'agrees' : 'disagrees'}`
                      : 'pending'}
                  </td>
                  <td>{d.evaluation_us !== null ? `${d.evaluation_us.toLocaleString()} µs` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {page.decisions.length > 20 && (
            <p className="text-[12px] text-tx-3 m-0 mt-2">
              Showing the 20 most recent of {page.decisions.length}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/** One policy card: identity, provenance, compiled decision, lifecycle, exports. */
function PolicyCard({
  policy,
  expanded,
  onToggle,
  onTransition,
  transitioning,
}: {
  policy: CompiledPolicySummary
  expanded: boolean
  onToggle: () => void
  onTransition: (action: PolicyTransitionAction) => void
  transitioning: boolean
}) {
  const [exportOpen, setExportOpen] = useState(false)
  const [exported, setExported] = useState<{ name: string; sha: string | null } | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const doExport = async (format: PolicyExportFormat) => {
    setExportOpen(false)
    setExportError(null)
    try {
      const dl = await compiledPoliciesApi.export(policy.policy_id, format, policy.version)
      const url = URL.createObjectURL(dl.blob)
      const a = document.createElement('a')
      a.href = url
      a.download = dl.filename
      a.click()
      URL.revokeObjectURL(url)
      setExported({ name: dl.filename, sha: dl.sha256 })
    } catch {
      setExportError(`Could not export the ${format} render.`)
    }
  }

  const actions = availableActions(policy.state)

  return (
    <div className="card card-sq" data-policy-id={policy.policy_id}>
      <div className="card-h">
        <div className="flex flex-col gap-1.5 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <StateBadge state={policy.state} />
            <strong>{policy.match.workflow_id}</strong>
            <span className="text-tx-3 text-[12.5px]">v{policy.version}</span>
          </div>
          <p className="m-0 text-[12.5px] text-tx-2" title={policy.content_hash}>
            <span style={{ fontFamily: 'var(--mono)' }}>{shortHash(policy.content_hash)}</span>
            {' · '}compiled {fmtWhen(policy.compiled_at)}
            {policy.compiled_by ? ` by ${policy.compiled_by}` : ''}
          </p>
        </div>
        <span className="grow" />
        <div className="flex items-center gap-2">
          {actions.map((action) => (
            <button
              key={action}
              className={`btn ${TRANSITIONS[action].danger ? 'ghost' : 'primary'}`}
              disabled={transitioning}
              onClick={() => onTransition(action)}
            >
              {TRANSITIONS[action].label}
            </button>
          ))}
          <div className="relative">
            <button className="btn ghost" onClick={() => setExportOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={exportOpen}>
              <Icon name="download" /> Export
            </button>
            {exportOpen && (
              <Popup open onClose={() => setExportOpen(false)} title="Export policy" width={300}>
                <div className="flex flex-col gap-1">
                  {EXPORT_FORMATS.map(({ format, label, ext }) => (
                    <button key={format} className="btn ghost" onClick={() => doExport(format)}>
                      {label} <span className="text-tx-3 text-[12px]">({ext})</span>
                    </button>
                  ))}
                </div>
              </Popup>
            )}
          </div>
        </div>
      </div>
      <div className="card-b">
        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[12.5px] text-tx-2">
          <span>
            matches <strong className="text-tx">{policy.match.workflow_id}</strong>
            {policy.match.data_source?.length ? ` on ${policy.match.data_source.join(', ')}` : ''}
          </span>
          <span>
            decides{' '}
            <strong style={{ color: 'var(--high)' }}>{policy.decision.severity}</strong>
            {` · ${policy.decision.recommended_action} · ${(policy.decision.confidence * 100).toFixed(0)}% measured agreement`}
            {policy.decision.actions_human_only ? ' · actions human-only' : ''}
          </span>
          <span>{maturityLine(policy)}</span>
        </div>
        {exportError && (
          <p className="text-[12.5px] m-0 mt-2" style={{ color: 'var(--crit)' }} role="alert">
            {exportError}
          </p>
        )}
        {exported && (
          <p className="text-[12px] m-0 mt-2 text-tx-3" title={exported.sha ?? undefined}>
            Exported {exported.name}
            {exported.sha ? ` · ${exported.sha}` : ''}
          </p>
        )}
        <button className="btn ghost text-[12.5px] mt-3" onClick={onToggle} aria-expanded={expanded}>
          <Icon name="chevD" /> {expanded ? 'Hide' : 'Show'} decision log
        </button>
        {expanded && <DecisionEvidence policyId={policy.policy_id} />}
      </div>
    </div>
  )
}

export default function CompiledPoliciesScreen() {
  const { rows, stateFilter, setStateFilter, phase, error, reload } = useCompiledPolicies()
  const [pending, setPending] = useState<PendingTransition | null>(null)
  const [busy, setBusy] = useState(false)
  const [transitionError, setTransitionError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const allCount = stateFilter === null && phase === 'ready' ? rows.length : null

  const onConfirm = async () => {
    if (!pending) return
    setBusy(true)
    setTransitionError(null)
    try {
      await runTransition(pending)
      setPending(null)
    } catch (e) {
      // a 409 (hash guard or an edge the state does not allow) surfaces the
      // server's refusal verbatim; the reload shows the row that actually won
      setTransitionError(errMsg(e))
      setPending(null)
    } finally {
      setBusy(false)
      reload()
    }
  }

  return (
    <div className="flex flex-col gap-3.5 px-[26px] pt-5">
      <div className="flex items-end justify-between gap-5">
        <div className="flex flex-col gap-[5px] min-w-0">
          <h1 className="m-0 text-[20px] leading-[1.25] tracking-[-0.2px] text-tx" style={{ fontWeight: 700 }}>
            {PAGE_TITLE}
          </h1>
          <p className="m-0 text-[13px] leading-[1.5] text-tx-2 max-w-[760px]">{PAGE_DESC}</p>
        </div>
        <button className="btn ghost" onClick={reload}>
          <Icon name="refresh" /> Refresh
        </button>
      </div>

      {transitionError && (
        <div role="alert" className="card card-sq" style={{ borderColor: 'var(--crit)', background: 'var(--crit-dim)' }}>
          <div className="card-b flex items-center gap-2 text-[13px]" style={{ color: 'var(--crit)' }}>
            <Icon name="alert" />
            {transitionError}
          </div>
        </div>
      )}

      <div className="wf-tabs" role="tablist" aria-label="Policy state filter">
        <button role="tab" aria-selected={stateFilter === null} className={stateFilter === null ? 'active' : ''} onClick={() => setStateFilter(null)}>
          All{allCount !== null ? ` · ${allCount}` : ''}
        </button>
        {STATES.map((s) => (
          <button key={s} role="tab" aria-selected={stateFilter === s} className={stateFilter === s ? 'active' : ''} onClick={() => setStateFilter(s)}>
            {s}
          </button>
        ))}
      </div>

      {phase === 'loading' && <EmptyState loading icon="shield" title="Loading compiled policies…" />}
      {phase === 'error' && (
        <EmptyState
          error
          icon="alert"
          title="Couldn’t load compiled policies"
          body={error ?? undefined}
          primary={{ label: 'Retry', onClick: reload, icon: 'refresh' }}
        />
      )}
      {phase === 'ready' && rows.length === 0 && (
        <EmptyState
          icon="shield"
          title={stateFilter ? `No ${stateFilter} policies` : 'No compiled policies yet'}
          body="When the maturity job shows a workflow consistently resolving one threat archetype, the compiler emits a candidate here for review. The fast path itself is configured in Settings and stays off until enabled."
        />
      )}
      {phase === 'ready' && rows.length > 0 && (
        <div className="flex flex-col gap-3">
          {rows.map((p) => (
            <PolicyCard
              key={`${p.policy_id}-v${p.version}`}
              policy={p}
              expanded={expandedId === p.policy_id}
              onToggle={() => setExpandedId((cur) => (cur === p.policy_id ? null : p.policy_id))}
              onTransition={(action) => {
                setTransitionError(null)
                setPending({ policy: p, action })
              }}
              transitioning={busy}
            />
          ))}
        </div>
      )}

      {pending && (
        <TransitionDialog pending={pending} busy={busy} onClose={() => !busy && setPending(null)} onConfirm={onConfirm} />
      )}
    </div>
  )
}

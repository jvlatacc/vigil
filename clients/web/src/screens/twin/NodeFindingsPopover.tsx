import { useEffect, useRef } from 'react'
import { Icon } from '../../shared/icons'
import {
  NODE_GLYPH,
  NODE_KIND_LABEL,
  SEV_COLOR,
  bucketOf,
  type TwinNodeVM,
} from './model'

/** A node's pinned context, in the dashboard FindingPopup's spirit: the
 *  findings with severity and status, the node's cases, and a click-through
 *  to each surface (findings open the FindingPopup here; cases open the
 *  console's case drawer). Esc or a click away closes it. */
export default function NodeFindingsPopover({
  node,
  onClose,
  onOpenFinding,
  onOpenCase,
}: {
  node: TwinNodeVM
  onClose: () => void
  onOpenFinding: (findingId: string) => void
  onOpenCase: (caseId: string) => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as globalThis.Node)) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [onClose])

  return (
    <div className="twin-popover" ref={ref} role="dialog" aria-label={`Findings on ${node.label}`}>
      <div className="twin-pop-head">
        <span className={`twin-node-glyph kind-${node.kind}`} aria-hidden="true">
          <Icon name={NODE_GLYPH[node.kind]} size={13} />
        </span>
        <span className="twin-pop-title">
          <span className="twin-pop-kind">{NODE_KIND_LABEL[node.kind]}</span>
          {node.label}
        </span>
        <button className="btn ghost twin-pop-close" onClick={onClose} aria-label="Close">
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className="twin-pop-body">
        <div className="twin-pop-section">
          <h4>Findings ({node.findings.length})</h4>
          {node.findings.length === 0 && <p className="twin-pop-empty">Nothing pinned here right now.</p>}
          <ul className="twin-pop-list">
            {node.findings.map((f) => (
              <li key={f.id}>
                <button className="twin-pop-row" onClick={() => onOpenFinding(f.id)} title="Open the finding">
                  <span className="twin-pop-dot" style={{ background: SEV_COLOR[bucketOf(f.sev)] }} aria-hidden="true" />
                  <span className="twin-pop-sev">{f.sev}</span>
                  <span className="twin-pop-main">{f.tech && f.tech !== '—' ? f.tech : f.id}</span>
                  <span className="twin-pop-meta">
                    {f.status} · {f.src}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="twin-pop-section">
          <h4>Cases ({node.cases.length})</h4>
          {node.cases.length === 0 && <p className="twin-pop-empty">No case gathers these findings yet.</p>}
          <ul className="twin-pop-list">
            {node.cases.map((c) => (
              <li key={c.id}>
                <button className="twin-pop-row" onClick={() => onOpenCase(c.id)} title="Open the case">
                  <span className="twin-pop-dot" aria-hidden="true" style={{ background: 'var(--accent)' }} />
                  <span className="twin-pop-sev">{c.prio}</span>
                  <span className="twin-pop-main">{c.title || c.id}</span>
                  <span className="twin-pop-meta">{c.status}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

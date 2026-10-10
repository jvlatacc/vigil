import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { Icon } from '../../shared/icons'
import {
  NODE_GLYPH,
  NODE_KIND_LABEL,
  SEV_COLOR,
  SEV_LABEL,
  countFindings,
  worstBucket,
  type TwinNodeVM,
} from './model'

/** data carried by every node on the twin canvas */
export interface TwinNodeData extends Record<string, unknown> {
  vm: TwinNodeVM
}

export type TwinNodeType = Node<TwinNodeData, 'twin'>

export default function TwinNode({ data, selected }: NodeProps<TwinNodeType>) {
  const vm = data.vm
  const worst = worstBucket(vm.severityCounts)
  const worstCount = vm.severityCounts[worst]
  const total = countFindings(vm.severityCounts)
  // readable without colour: the ring widens with the count of findings at
  // the node's worst severity, the badge states the total outright, and the
  // kind is written as text beside the glyph
  const ringWidth = 2 + Math.min(worstCount, 4)
  const description =
    `${NODE_KIND_LABEL[vm.kind]} ${vm.label} — ${total} finding${total === 1 ? '' : 's'}` +
    (worstCount > 0 ? `, ${worstCount} ${SEV_LABEL[worst]}` : '')
  return (
    <div
      className={`twin-node kind-${vm.kind}${selected ? ' selected' : ''}`}
      style={{ borderWidth: ringWidth, borderColor: SEV_COLOR[worst] }}
      title={description}
      aria-label={description}
    >
      <Handle type="target" position={Position.Top} className="twin-handle" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} className="twin-handle" isConnectable={false} />
      <span className="twin-node-glyph" aria-hidden="true">
        <Icon name={NODE_GLYPH[vm.kind]} size={13} />
      </span>
      <span className="twin-node-copy">
        <span className="twin-node-kind">{NODE_KIND_LABEL[vm.kind]}</span>
        <span className="twin-node-label">{vm.label}</span>
      </span>
      {total > 0 && (
        <span className="twin-node-badge" aria-hidden="true">
          {total}
        </span>
      )}
    </div>
  )
}

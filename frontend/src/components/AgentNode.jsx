import React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Bot } from 'lucide-react'

export default function AgentNode({ data, selected }) {
  return (
    <div className={`agent-node${selected ? ' selected' : ''}`}>
      <Handle type="target" position={Position.Left} style={{ background: 'var(--accent)', width: 8, height: 8, border: '2px solid var(--bg2)' }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: 'var(--accent-glow)', border: '1px solid rgba(79,142,247,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
        }}>
          <Bot size={14} color="var(--accent)" />
        </div>
        <div>
          <div className="node-role">{data.role || 'Agent'}</div>
          <div className="node-name">{data.label}</div>
          {data.model && <div className="node-model">{data.model}</div>}
        </div>
      </div>

      <Handle type="source" position={Position.Right} style={{ background: 'var(--accent2)', width: 8, height: 8, border: '2px solid var(--bg2)' }} />
    </div>
  )
}

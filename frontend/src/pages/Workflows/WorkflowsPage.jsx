import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ReactFlow, MiniMap, Controls, Background,
  addEdge, useNodesState, useEdgesState,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Plus, Play, Save, Trash2, GitBranch, ChevronDown, Send, X } from 'lucide-react'
import { workflowsApi, agentsApi, createMonitorSocket } from '../../api.js'
import AgentNode from '../../components/AgentNode.jsx'

const nodeTypes = { agentNode: AgentNode }

function WorkflowListPanel({ workflows, selected, onSelect, onNew, onDelete }) {
  return (
    <div style={{ width: 240, borderRight: '1px solid var(--border)', background: 'var(--bg2)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '12px 12px 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Workflows</span>
        <button className="btn btn-primary btn-sm" onClick={onNew}><Plus size={12} /></button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {workflows.map(wf => (
          <div
            key={wf.id}
            onClick={() => onSelect(wf)}
            style={{
              padding: '8px 10px', borderRadius: 6, cursor: 'pointer',
              background: selected?.id === wf.id ? 'var(--accent-glow)' : 'transparent',
              border: `1px solid ${selected?.id === wf.id ? 'rgba(79,142,247,0.3)' : 'transparent'}`,
              color: selected?.id === wf.id ? 'var(--accent)' : 'var(--text)',
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 500 }}>{wf.name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {wf.definition?.nodes?.length || 0} nodes · {wf.definition?.edges?.length || 0} edges
            </div>
          </div>
        ))}
        {workflows.length === 0 && (
          <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: 8 }}>No workflows yet</div>
        )}
      </div>
    </div>
  )
}

function AddAgentSidebar({ agents, onAdd }) {
  return (
    <div style={{ width: 200, borderLeft: '1px solid var(--border)', background: 'var(--bg2)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Add Agent</span>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {agents.map(agent => (
          <div
            key={agent.id}
            draggable
            onDragStart={e => e.dataTransfer.setData('agent', JSON.stringify(agent))}
            onClick={() => onAdd(agent)}
            style={{
              padding: '8px 10px', borderRadius: 6, cursor: 'grab',
              background: 'var(--bg3)', border: '1px solid var(--border)',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-hover)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
          >
            <div style={{ fontSize: 12, fontWeight: 600 }}>{agent.name}</div>
            <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>{agent.role}</div>
          </div>
        ))}
        {agents.length === 0 && (
          <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: 8 }}>Create agents first</div>
        )}
      </div>
    </div>
  )
}

function RunPanel({ workflow, onClose }) {
  const [message, setMessage] = useState('')
  const [run, setRun] = useState(null)
  const [logs, setLogs] = useState([])
  const [running, setRunning] = useState(false)
  const wsRef = useRef(null)
  const logsEndRef = useRef(null)

  useEffect(() => {
    return () => wsRef.current?.close()
  }, [])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const handleRun = async () => {
    if (!message.trim()) return
    setRunning(true)
    setLogs([])
    setRun(null)

    try {
      const runData = await workflowsApi.run(workflow.id, message)
      setRun(runData)

      // Subscribe to WS events for this run
      wsRef.current?.close()
      wsRef.current = createMonitorSocket((event) => {
        setLogs(prev => [...prev, event])
        if (event.event === 'run_completed' || event.event === 'run_failed') {
          setRunning(false)
        }
      }, runData.id)
    } catch (e) {
      setLogs([{ event: 'error', data: { error: e.message }, timestamp: new Date().toISOString() }])
      setRunning(false)
    }
  }

  const formatTime = (ts) => new Date(ts).toLocaleTimeString()

  return (
    <div style={{
      position: 'absolute', right: 0, top: 0, bottom: 0, width: 420,
      background: 'var(--bg2)', borderLeft: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', zIndex: 100
    }}>
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Run Workflow</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{workflow.name}</div>
        </div>
        <button onClick={onClose} style={{ color: 'var(--text-muted)', padding: 4 }}><X size={16} /></button>
      </div>

      <div style={{ padding: 14, borderBottom: '1px solid var(--border)', display: 'flex', gap: 8 }}>
        <input
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleRun()}
          placeholder="Enter input message..."
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" onClick={handleRun} disabled={running || !message.trim()}>
          {running ? '...' : <Send size={14} />}
        </button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        {logs.length === 0 && !running && (
          <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: 8 }}>Run output will appear here</div>
        )}

        <div className="log-panel" style={{ maxHeight: 'none', height: '100%' }}>
          {logs.map((log, i) => (
            <div key={i} className={`log-entry log-event-${log.event}`}>
              <span className="log-time">{formatTime(log.timestamp)}</span>
              {log.event === 'agent_message' && (
                <>
                  <span className="log-from">{log.data.from_agent}</span>
                  <span style={{ color: 'var(--text-dim)' }}>→</span>
                  <span className="log-to">{log.data.to_agent}</span>
                  <span className="log-content">{log.data.content?.slice(0, 200)}{log.data.content?.length > 200 ? '...' : ''}</span>
                </>
              )}
              {log.event === 'run_started' && (
                <span className="log-content">▶ Run started — "{log.data.input?.slice(0, 80)}"</span>
              )}
              {log.event === 'run_completed' && (
                <span className="log-content">✓ Completed — {log.data.token_count} tokens</span>
              )}
              {log.event === 'run_failed' && (
                <span className="log-content">✗ Failed: {log.data.error}</span>
              )}
              {log.event === 'error' && (
                <span className="log-content" style={{ color: 'var(--red)' }}>Error: {log.data.error}</span>
              )}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  )
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState([])
  const [agents, setAgents] = useState([])
  const [selected, setSelected] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [showRun, setShowRun] = useState(false)
  const [saving, setSaving] = useState(false)
  const [workflowName, setWorkflowName] = useState('')
  const [showNameEdit, setShowNameEdit] = useState(false)
  const [templates, setTemplates] = useState([])
  const [instantiating, setInstantiating] = useState(false)
  const reactFlowWrapper = useRef(null)

  useEffect(() => {
    loadWorkflows()
    loadAgents()
    workflowsApi.templates().then(setTemplates).catch(() => {})
  }, [])

  const instantiateTemplate = async (tmpl) => {
    setInstantiating(true)
    try {
      const wf = await workflowsApi.instantiateTemplate(tmpl.name)
      setWorkflows(prev => [wf, ...prev])
      await loadAgents()
      selectWorkflow(wf)
    } catch (e) {
      alert('Failed to instantiate template: ' + (e.response?.data?.detail || e.message))
    }
    setInstantiating(false)
  }

  const loadWorkflows = async () => {
    try { setWorkflows(await workflowsApi.list()) } catch { }
  }

  const loadAgents = async () => {
    try { setAgents(await agentsApi.list()) } catch { }
  }

  const selectWorkflow = (wf) => {
    setSelected(wf)
    setWorkflowName(wf.name)
    setNodes(wf.definition?.nodes || [])
    setEdges(wf.definition?.edges || [])
    setShowRun(false)
  }

  const newWorkflow = async () => {
    const name = `Workflow ${workflows.length + 1}`
    try {
      const wf = await workflowsApi.create({
        name,
        definition: { nodes: [], edges: [] }
      })
      setWorkflows(prev => [wf, ...prev])
      selectWorkflow(wf)
    } catch { }
  }

  const saveWorkflow = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const updated = await workflowsApi.update(selected.id, {
        name: workflowName,
        definition: { nodes, edges },
      })
      setWorkflows(prev => prev.map(w => w.id === updated.id ? updated : w))
      setSelected(updated)
    } catch { }
    setSaving(false)
  }

  const deleteWorkflow = async () => {
    if (!selected || !confirm('Delete this workflow?')) return
    await workflowsApi.delete(selected.id)
    setWorkflows(prev => prev.filter(w => w.id !== selected.id))
    setSelected(null)
    setNodes([])
    setEdges([])
  }

  const onConnect = useCallback((params) => {
    setEdges(eds => addEdge({ ...params, animated: true, style: { stroke: 'var(--accent)', strokeWidth: 2 } }, eds))
  }, [])

  const addAgentNode = (agent) => {
    const id = `node_${Date.now()}`
    const newNode = {
      id,
      type: 'agentNode',
      position: { x: 100 + nodes.length * 220, y: 150 },
      data: { agent_id: agent.id, label: agent.name, role: agent.role, model: agent.model },
    }
    setNodes(prev => [...prev, newNode])
  }

  const onDrop = useCallback((e) => {
    e.preventDefault()
    const agentData = e.dataTransfer.getData('agent')
    if (!agentData) return
    const agent = JSON.parse(agentData)
    const bounds = reactFlowWrapper.current?.getBoundingClientRect()
    const position = {
      x: e.clientX - (bounds?.left || 0) - 80,
      y: e.clientY - (bounds?.top || 0) - 25,
    }
    const id = `node_${Date.now()}`
    setNodes(prev => [...prev, {
      id, type: 'agentNode', position,
      data: { agent_id: agent.id, label: agent.name, role: agent.role, model: agent.model },
    }])
  }, [nodes])

  const onDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', flexDirection: 'column' }}>
      {/* Header */}
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {showNameEdit && selected ? (
            <input
              value={workflowName}
              onChange={e => setWorkflowName(e.target.value)}
              onBlur={() => setShowNameEdit(false)}
              onKeyDown={e => e.key === 'Enter' && setShowNameEdit(false)}
              autoFocus
              style={{ fontSize: 16, fontFamily: 'var(--font-mono)', fontWeight: 700, width: 200 }}
            />
          ) : (
            <h2 onClick={() => selected && setShowNameEdit(true)} style={{ cursor: selected ? 'text' : 'default' }}>
              {selected ? workflowName : 'Workflows'}
            </h2>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {selected && (
            <>
              <button className="btn btn-ghost" onClick={deleteWorkflow}><Trash2 size={14} /></button>
              <button className="btn btn-ghost" onClick={saveWorkflow} disabled={saving}>
                <Save size={14} /> {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => setShowRun(s => !s)}
                disabled={!nodes.length}
              >
                <Play size={14} /> Run
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <WorkflowListPanel
          workflows={workflows}
          selected={selected}
          onSelect={selectWorkflow}
          onNew={newWorkflow}
          onDelete={deleteWorkflow}
        />

        {/* Canvas area */}
        <div style={{ flex: 1, position: 'relative' }} ref={reactFlowWrapper}>
          {!selected ? (
            <div className="empty-state" style={{ height: '100%' }}>
              <GitBranch />
              <h3>Select or create a workflow</h3>
              <p>Build multi-agent pipelines with the visual editor</p>
              {templates.length > 0 && (
                <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 320 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Or start from a template</div>
                  {templates.map(t => (
                    <button
                      key={t.name}
                      className="btn btn-ghost"
                      style={{ justifyContent: 'flex-start', gap: 8, padding: '8px 12px' }}
                      onClick={() => instantiateTemplate(t)}
                      disabled={instantiating}
                    >
                      <GitBranch size={14} />
                      <div style={{ textAlign: 'left' }}>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.description}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onDrop={onDrop}
              onDragOver={onDragOver}
              nodeTypes={nodeTypes}
              fitView
              style={{ background: 'var(--bg)' }}
              defaultEdgeOptions={{ animated: true, style: { stroke: 'var(--accent)', strokeWidth: 2 } }}
            >
              <Background variant={BackgroundVariant.Dots} color="var(--border)" gap={24} size={1} />
              <Controls style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }} />
              <MiniMap style={{ background: 'var(--bg2)', border: '1px solid var(--border)' }} nodeColor="var(--accent)" />
            </ReactFlow>
          )}

          {showRun && selected && (
            <RunPanel workflow={selected} onClose={() => setShowRun(false)} />
          )}
        </div>

        {selected && (
          <AddAgentSidebar agents={agents} onAdd={addAgentNode} />
        )}
      </div>
    </div>
  )
}

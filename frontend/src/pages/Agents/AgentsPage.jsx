import React, { useState, useEffect } from 'react'
import { Bot, Plus, Pencil, Trash2, Cpu, X } from 'lucide-react'
import { agentsApi } from '../../api.js'
import { formatDistanceToNow } from 'date-fns'

const DEFAULT_FORM = {
  name: '',
  role: '',
  system_prompt: '',
  model: 'gemini-2.5-flash',
  tools: [],
  memory_config: {},
  guardrails: {},
  schedule: { enabled: false, cron: '0 9 * * 1-5', timezone: 'UTC', workflow_id: '' },
}

const MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']

function AgentModal({ agent, onClose, onSave }) {
  const [form, setForm] = useState(agent ? { ...agent } : { ...DEFAULT_FORM })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async () => {
    if (!form.name || !form.role || !form.system_prompt) {
      setError('Name, role, and system prompt are required.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      let saved
      if (agent) {
        saved = await agentsApi.update(agent.id, form)
      } else {
        saved = await agentsApi.create(form)
      }
      onSave(saved)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to save agent')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">{agent ? 'Edit Agent' : 'New Agent'}</div>

        {error && <div style={{ color: 'var(--red)', fontSize: 13 }}>{error}</div>}

        <div className="form-group">
          <label>Name</label>
          <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Researcher" />
        </div>

        <div className="form-group">
          <label>Role</label>
          <input value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} placeholder="Research Specialist" />
        </div>

        <div className="form-group">
          <label>Model</label>
          <select value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))}>
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>System Prompt</label>
          <textarea
            value={form.system_prompt}
            onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
            placeholder="You are a research specialist. When given a topic, you gather comprehensive information and present it clearly..."
            rows={6}
          />
        </div>

        <div className="form-group">
          <label>Tools</label>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {['web_search', 'calculator', 'datetime'].map(tool => (
              <label key={tool} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={(form.tools || []).includes(tool)}
                  onChange={e => {
                    const tools = form.tools || []
                    setForm(f => ({ ...f, tools: e.target.checked ? [...tools, tool] : tools.filter(t => t !== tool) }))
                  }}
                />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)' }}>{tool}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label>Max Tokens (guardrail)</label>
          <input
            type="number"
            value={form.guardrails?.max_tokens || ''}
            onChange={e => setForm(f => ({ ...f, guardrails: { ...f.guardrails, max_tokens: e.target.value ? parseInt(e.target.value) : undefined } }))}
            placeholder="1024"
            style={{ width: 120 }}
          />
        </div>

        <div className="form-group">
          <label>Memory</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <input
              type="checkbox"
              id="memEnabled"
              checked={form.memory_config?.enabled || false}
              onChange={e => setForm(f => ({ ...f, memory_config: { ...f.memory_config, enabled: e.target.checked } }))}
            />
            <label htmlFor="memEnabled" style={{ fontSize: 13, margin: 0 }}>Enable memory window</label>
          </div>
          {form.memory_config?.enabled && (
            <input
              type="number"
              value={form.memory_config?.window || 10}
              onChange={e => setForm(f => ({ ...f, memory_config: { ...f.memory_config, window: parseInt(e.target.value) } }))}
              placeholder="Window size (messages)"
              style={{ width: 120 }}
            />
          )}
        </div>

        <div className="form-group">
          <label>Schedule</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <input
              type="checkbox"
              id="schedEnabled"
              checked={form.schedule?.enabled || false}
              onChange={e => setForm(f => ({ ...f, schedule: { ...f.schedule, enabled: e.target.checked } }))}
            />
            <label htmlFor="schedEnabled" style={{ fontSize: 13, margin: 0 }}>Enable scheduled trigger</label>
          </div>
          {form.schedule?.enabled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  value={form.schedule?.cron || ''}
                  onChange={e => setForm(f => ({ ...f, schedule: { ...f.schedule, cron: e.target.value } }))}
                  placeholder="Cron: 0 9 * * 1-5"
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12 }}
                />
                <input
                  value={form.schedule?.timezone || 'UTC'}
                  onChange={e => setForm(f => ({ ...f, schedule: { ...f.schedule, timezone: e.target.value } }))}
                  placeholder="UTC"
                  style={{ width: 100 }}
                />
              </div>
              <input
                value={form.schedule?.workflow_id || ''}
                onChange={e => setForm(f => ({ ...f, schedule: { ...f.schedule, workflow_id: e.target.value } }))}
                placeholder="Workflow ID to trigger"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              />
              <input
                value={form.schedule?.trigger_message || ''}
                onChange={e => setForm(f => ({ ...f, schedule: { ...f.schedule, trigger_message: e.target.value } }))}
                placeholder="Trigger message (e.g. Run daily report)"
              />
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={loading}>
            {loading ? 'Saving...' : (agent ? 'Update Agent' : 'Create Agent')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AgentsPage() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await agentsApi.list()
      setAgents(data)
    } catch { }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleSave = (saved) => {
    setAgents(prev => {
      const idx = prev.findIndex(a => a.id === saved.id)
      if (idx >= 0) {
        const next = [...prev]; next[idx] = saved; return next
      }
      return [saved, ...prev]
    })
    setShowModal(false)
    setEditing(null)
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this agent?')) return
    await agentsApi.delete(id)
    setAgents(prev => prev.filter(a => a.id !== id))
  }

  const openCreate = () => { setEditing(null); setShowModal(true) }
  const openEdit = (a) => { setEditing(a); setShowModal(true) }

  return (
    <>
      <div className="page-header">
        <h2>Agents</h2>
        <button className="btn btn-primary" onClick={openCreate}>
          <Plus size={14} /> New Agent
        </button>
      </div>

      <div className="page-body">
        {loading && <div style={{ color: 'var(--text-muted)' }}>Loading...</div>}

        {!loading && agents.length === 0 && (
          <div className="empty-state">
            <Bot />
            <h3>No agents yet</h3>
            <p>Create your first agent to start building workflows</p>
            <button className="btn btn-primary" onClick={openCreate}>
              <Plus size={14} /> New Agent
            </button>
          </div>
        )}

        {!loading && agents.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {agents.map(agent => (
              <div key={agent.id} className="card" style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                <div style={{
                  width: 42, height: 42, borderRadius: 10,
                  background: 'var(--accent-glow)', border: '1px solid rgba(79,142,247,0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                }}>
                  <Bot size={20} color="var(--accent)" />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <strong style={{ fontSize: 15 }}>{agent.name}</strong>
                    <span style={{
                      fontSize: 11, color: 'var(--accent2)', fontFamily: 'var(--font-mono)',
                      background: 'var(--accent2-glow)', padding: '1px 7px', borderRadius: 99
                    }}>{agent.role}</span>
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8, display: 'flex', gap: 16 }}>
                    <span><Cpu size={11} style={{ verticalAlign: 'middle' }} /> {agent.model}</span>
                    <span>Created {formatDistanceToNow(new Date(agent.created_at), { addSuffix: true })}</span>
                    {agent.tools?.length > 0 && <span style={{ color: 'var(--accent)' }}>⚙ {agent.tools.join(', ')}</span>}
                    {agent.memory_config?.enabled && <span style={{ color: 'var(--green, #4ade80)' }}>🧠 memory:{agent.memory_config.window}</span>}
                    {agent.guardrails?.max_tokens && <span>🛡 {agent.guardrails.max_tokens}tok</span>}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 600 }}>
                    {agent.system_prompt}
                  </p>
                </div>

                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => openEdit(agent)}>
                    <Pencil size={12} /> Edit
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(agent.id)}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <AgentModal
          agent={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSave={handleSave}
        />
      )}
    </>
  )
}

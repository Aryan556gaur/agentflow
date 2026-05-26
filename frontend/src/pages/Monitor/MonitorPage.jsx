import React, { useState, useEffect, useRef } from 'react'
import { Activity, Zap, MessageSquare, GitBranch, Bot, RotateCcw } from 'lucide-react'
import { monitorApi, createMonitorSocket } from '../../api.js'
import { formatDistanceToNow } from 'date-fns'

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="stat-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={16} style={{ color }} />
        </div>
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">{value?.toLocaleString() ?? '—'}</div>
    </div>
  )
}

function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${status}`}>
      {status === 'running' && <span className="dot" />}
      {status}
    </span>
  )
}

export default function MonitorPage() {
  const [stats, setStats] = useState(null)
  const [runs, setRuns] = useState([])
  const [liveLogs, setLiveLogs] = useState([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const logsEndRef = useRef(null)

  useEffect(() => {
    loadData()
    connectWS()
    const interval = setInterval(loadData, 10000)
    return () => {
      clearInterval(interval)
      wsRef.current?.close()
    }
  }, [])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLogs])

  const loadData = async () => {
    try {
      const [s, r] = await Promise.all([monitorApi.stats(), monitorApi.recentRuns(15)])
      setStats(s)
      setRuns(r)
    } catch { }
  }

  const connectWS = () => {
    wsRef.current?.close()
    wsRef.current = createMonitorSocket((event) => {
      setLiveLogs(prev => {
        const next = [...prev, { ...event, _id: Date.now() + Math.random() }]
        return next.slice(-100) // keep last 100
      })
      // Refresh stats on run completion
      if (event.event === 'run_completed' || event.event === 'run_failed') {
        loadData()
      }
    })
    wsRef.current.onopen = () => setConnected(true)
    wsRef.current.onclose = () => setConnected(false)
  }

  const formatTime = (ts) => {
    try { return new Date(ts).toLocaleTimeString() } catch { return '' }
  }

  const clearLogs = () => setLiveLogs([])

  return (
    <>
      <div className="page-header">
        <h2>Monitor</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: connected ? 'var(--green)' : 'var(--red)', boxShadow: connected ? '0 0 6px var(--green)' : 'none' }} />
            <span style={{ color: 'var(--text-muted)' }}>{connected ? 'Live' : 'Disconnected'}</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={loadData}><RotateCcw size={12} /> Refresh</button>
        </div>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Stats */}
        <div className="grid-4">
          <StatCard label="Agents" value={stats?.total_agents} icon={Bot} color="var(--accent)" />
          <StatCard label="Workflows" value={stats?.total_workflows} icon={GitBranch} color="var(--accent2)" />
          <StatCard label="Total Runs" value={stats?.total_runs} icon={Zap} color="var(--green)" />
          <StatCard label="Messages" value={stats?.total_messages} icon={MessageSquare} color="var(--yellow)" />
        </div>
        {/* Token / Cost Summary */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 32, padding: '14px 20px' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Tokens Used</div>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginTop: 2 }}>{stats?.total_tokens?.toLocaleString() ?? '—'}</div>
          </div>
          <div style={{ width: 1, height: 36, background: 'var(--border)' }} />
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Est. Cost (gemini-2.5-flash)</div>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--green)', marginTop: 2 }}>
              {stats?.total_tokens != null ? `$${((stats.total_tokens / 1_000_000) * 0.15).toFixed(4)}` : '—'}
            </div>
          </div>
          <div style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-dim)' }}>$0.15 / 1M tokens · update on refresh</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {/* Recent Runs */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>Recent Runs</div>
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {runs.length === 0 ? (
                <div className="empty-state" style={{ padding: 30 }}>
                  <Zap />
                  <p>No runs yet</p>
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => (
                      <tr key={run.id}>
                        <td>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                            {run.id.slice(0, 8)}...
                          </span>
                        </td>
                        <td><StatusBadge status={run.status} /></td>
                        <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          {formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{run.token_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Run status breakdown */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>Run Status Breakdown</div>
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {stats?.runs_by_status && Object.entries(stats.runs_by_status).map(([status, count]) => (
                <div key={status}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <StatusBadge status={status} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{count}</span>
                  </div>
                  <div style={{ height: 4, background: 'var(--bg3)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 2,
                      width: `${stats.total_runs ? (count / stats.total_runs) * 100 : 0}%`,
                      background: status === 'completed' ? 'var(--green)' : status === 'running' ? 'var(--accent)' : status === 'failed' ? 'var(--red)' : 'var(--yellow)',
                      transition: 'width 0.5s ease',
                    }} />
                  </div>
                </div>
              ))}
              {!stats && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading...</div>}
            </div>
          </div>
        </div>

        {/* Live Log Stream */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: 8 }}>
              Live Event Stream
              {connected && <span style={{ width: 6, height: 6, background: 'var(--green)', borderRadius: '50%', display: 'inline-block', animation: 'pulse 1.4s infinite' }} />}
            </div>
            <button className="btn btn-ghost btn-sm" onClick={clearLogs}>Clear</button>
          </div>

          <div className="log-panel" style={{ maxHeight: 320 }}>
            {liveLogs.length === 0 && (
              <div style={{ color: 'var(--text-dim)', padding: 8 }}>
                {connected ? 'Waiting for events...' : 'Connecting...'}
              </div>
            )}
            {liveLogs.map(log => (
              <div key={log._id} className={`log-entry log-event-${log.event}`}>
                <span className="log-time">{formatTime(log.timestamp)}</span>
                {log.event === 'agent_message' && (
                  <>
                    <span className="log-from">{log.data.from_agent}</span>
                    <span style={{ color: 'var(--text-dim)' }}>→</span>
                    <span className="log-to">{log.data.to_agent}</span>
                    <span className="log-content">{log.data.content?.slice(0, 150)}{log.data.content?.length > 150 ? '...' : ''}</span>
                  </>
                )}
                {log.event === 'run_started' && (
                  <><span style={{ color: 'var(--green)' }}>RUN</span><span className="log-content">Started — "{log.data.input?.slice(0, 60)}"</span></>
                )}
                {log.event === 'run_completed' && (
                  <><span style={{ color: 'var(--green)' }}>DONE</span><span className="log-content">Completed · {log.data.token_count} tokens</span></>
                )}
                {log.event === 'run_failed' && (
                  <><span style={{ color: 'var(--red)' }}>FAIL</span><span className="log-content">{log.data.error}</span></>
                )}
                {log.event === 'tool_call' && (
                  <>
                    <span style={{ color: '#f0b429' }}>TOOL</span>
                    <span className="log-from">{log.data.agent}</span>
                    <span style={{ color: 'var(--text-dim)' }}>⚙</span>
                    <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{log.data.tool}</span>
                    <span className="log-content">{log.data.result_preview?.slice(0, 120)}</span>
                  </>
                )}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </>
  )
}

import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
})

// ── Agents ──────────────────────────────────────────────────────────────────
export const agentsApi = {
  list: () => api.get('/agents/').then(r => r.data),
  get: (id) => api.get(`/agents/${id}`).then(r => r.data),
  create: (data) => api.post('/agents/', data).then(r => r.data),
  update: (id, data) => api.put(`/agents/${id}`, data).then(r => r.data),
  delete: (id) => api.delete(`/agents/${id}`),
}

// ── Workflows ────────────────────────────────────────────────────────────────
export const workflowsApi = {
  list: () => api.get('/workflows/').then(r => r.data),
  get: (id) => api.get(`/workflows/${id}`).then(r => r.data),
  create: (data) => api.post('/workflows/', data).then(r => r.data),
  update: (id, data) => api.put(`/workflows/${id}`, data).then(r => r.data),
  delete: (id) => api.delete(`/workflows/${id}`),
  templates: () => api.get('/workflows/templates').then(r => r.data),
  instantiateTemplate: (name) => api.post(`/workflows/templates/${encodeURIComponent(name)}/instantiate`).then(r => r.data),
  run: (id, msg) => api.post(`/workflows/${id}/run`, { input_message: msg }).then(r => r.data),
  runs: (id) => api.get(`/workflows/${id}/runs`).then(r => r.data),
}

// ── Monitor ──────────────────────────────────────────────────────────────────
export const monitorApi = {
  stats: () => api.get('/monitor/stats').then(r => r.data),
  recentRuns: (limit = 20) => api.get(`/monitor/runs/recent?limit=${limit}`).then(r => r.data),
  recentMessages: (limit = 50) => api.get(`/monitor/messages/recent?limit=${limit}`).then(r => r.data),
  runMessages: (runId) => api.get(`/workflows/runs/${runId}/messages`).then(r => r.data),
}

// ── WebSocket ────────────────────────────────────────────────────────────────
const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`

export function createMonitorSocket(onMessage, runId = null) {
  const url = runId
    ? `${WS_BASE}/api/monitor/ws/${runId}`
    : `${WS_BASE}/api/monitor/ws`
  const ws = new WebSocket(url)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch { }
  }
  ws.onclose = () => console.log('WS closed')
  ws.onerror = (e) => console.error('WS error', e)
  return ws
}

export default api

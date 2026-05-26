import React from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { Bot, GitBranch, Activity } from 'lucide-react'
import AgentsPage from './pages/Agents/AgentsPage.jsx'
import WorkflowsPage from './pages/Workflows/WorkflowsPage.jsx'
import MonitorPage from './pages/Monitor/MonitorPage.jsx'

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>Agent<span>Flow</span></h1>
          <p>Multi-Agent Orchestration</p>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/agents" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Bot /> Agents
          </NavLink>
          <NavLink to="/workflows" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <GitBranch /> Workflows
          </NavLink>
          <NavLink to="/monitor" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Activity /> Monitor
          </NavLink>
        </nav>
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/agents" replace />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/workflows/:id" element={<WorkflowsPage />} />
          <Route path="/monitor" element={<MonitorPage />} />
        </Routes>
      </main>
    </div>
  )
}

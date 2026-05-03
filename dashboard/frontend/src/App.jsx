import { useState, useEffect, useCallback, useRef } from 'react'
import StepTracker from './components/StepTracker'
import LiveLogs from './components/LiveLogs'
import ReasoningPanel from './components/ReasoningPanel'
import UserControls from './components/UserControls'
import StatusBar from './components/StatusBar'
import MemoryPanel from './components/MemoryPanel'
import useWebSocket from './hooks/useWebSocket'
import './App.css'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

function App() {
  const [steps, setSteps] = useState([])
  const [logs, setLogs] = useState([])
  const [reasoning, setReasoning] = useState([])
  const [currentPlan, setCurrentPlan] = useState(null)
  const [isExecuting, setIsExecuting] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const [history, setHistory] = useState([])
  const [skills, setSkills] = useState([])

  // WebSocket connection
  const onMessage = useCallback((event) => {
    const data = JSON.parse(event.data)
    
    switch (data.type) {
      case 'plan_started':
        setCurrentPlan({
          intent: data.intent,
          summary: data.summary,
          totalSteps: data.total_steps,
          startedAt: data.timestamp,
        })
        setIsExecuting(true)
        setSteps([])
        setLogs([])
        setReasoning([])
        break

      case 'step_started':
        setSteps(prev => {
          const existing = prev.find(s => s.id === data.stepId)
          if (existing) {
            return prev.map(s => s.id === data.stepId 
              ? { ...s, status: 'running', startedAt: data.timestamp }
              : s
            )
          }
          return [...prev, {
            id: data.stepId,
            skill: data.skill,
            action: data.action,
            description: data.description,
            status: 'running',
            startedAt: data.timestamp,
          }]
        })
        if (data.reasoning) {
          setReasoning(prev => [...prev, {
            stepId: data.stepId,
            text: data.reasoning,
            timestamp: data.timestamp,
          }])
        }
        break

      case 'step_completed':
        setSteps(prev => prev.map(s => 
          s.id === data.stepId
            ? { ...s, status: 'done', result: data.result, completedAt: data.timestamp }
            : s
        ))
        break

      case 'step_failed':
        setSteps(prev => prev.map(s =>
          s.id === data.stepId
            ? { ...s, status: 'failed', error: data.error, completedAt: data.timestamp }
            : s
        ))
        break

      case 'plan_completed':
        setCurrentPlan(prev => prev ? { ...prev, status: data.status, completedAt: data.completed_at } : prev)
        setIsExecuting(false)
        break

      case 'plan_replanned':
        setLogs(prev => [...prev, {
          timestamp: data.timestamp,
          level: 'WARN',
          message: `Recovery: ${data.recovery_steps} alternative steps generated`,
          stepId: data.failed_step_id,
        }])
        break

      case 'terminal_output':
        setLogs(prev => [...prev, {
          timestamp: data.timestamp,
          level: data.stream === 'stderr' ? 'ERROR' : 'INFO',
          message: data.line,
          stream: data.stream,
        }])
        break

      case 'recovery_started':
      case 'recovery_plan_ready':
      case 'recovery_failed':
      case 'notification':
      case 'step_retrying':
        setLogs(prev => [...prev, {
          timestamp: data.timestamp,
          level: data.level || 'WARN',
          message: data.message || JSON.stringify(data),
          stepId: data.stepId,
        }])
        break

      default:
        setLogs(prev => [...prev, {
          timestamp: data.timestamp || new Date().toISOString(),
          level: 'DEBUG',
          message: JSON.stringify(data),
        }])
    }
  }, [])

  const { sendMessage, readyState } = useWebSocket(WS_URL, onMessage)

  useEffect(() => {
    const states = ['connecting', 'connected', 'closing', 'disconnected']
    setConnectionStatus(states[readyState] || 'disconnected')
  }, [readyState])

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [historyRes, skillsRes] = await Promise.all([
          fetch(`${API_URL}/history`).catch(() => null),
          fetch(`${API_URL}/skills`).catch(() => null),
        ])
        if (historyRes?.ok) {
          const data = await historyRes.json()
          setHistory(data.workflows || [])
        }
        if (skillsRes?.ok) {
          const data = await skillsRes.json()
          setSkills(data.skills || [])
        }
      } catch (e) {
        console.log('Backend not available yet')
      }
    }
    fetchData()
  }, [])

  const handleCommand = async (command) => {
    try {
      const res = await fetch(`${API_URL}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      })
      if (!res.ok) throw new Error(await res.text())
    } catch (e) {
      // Try WebSocket fallback
      sendMessage(JSON.stringify({ type: 'command', command }))
    }
  }

  const handleControl = async (action, params = {}) => {
    try {
      await fetch(`${API_URL}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, ...params }),
      })
    } catch (e) {
      sendMessage(JSON.stringify({ type: 'control', action, ...params }))
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon">🐾</span>
            <h1>OpenClaw</h1>
            <span className="version-badge">v1.0.0-α</span>
          </div>
          <p className="tagline">Intent-Based Operating System</p>
        </div>
        <StatusBar 
          connectionStatus={connectionStatus}
          isExecuting={isExecuting}
          skills={skills}
        />
      </header>

      <main className="app-main">
        <div className="panel-grid">
          {/* Left Panel — Step Tracker */}
          <section className="panel panel-steps">
            <div className="panel-header">
              <h2>
                <span className="panel-icon">📋</span>
                Step Tracker
              </h2>
              {currentPlan && (
                <span className="step-counter">
                  {steps.filter(s => s.status === 'done').length}/{currentPlan.totalSteps}
                </span>
              )}
            </div>
            <div className="panel-body">
              {currentPlan && (
                <div className="plan-summary">
                  <span className="plan-intent">{currentPlan.intent}</span>
                  <span className="plan-desc">{currentPlan.summary}</span>
                </div>
              )}
              <StepTracker steps={steps} />
              {!currentPlan && steps.length === 0 && (
                <div className="empty-state">
                  <span className="empty-icon">🎯</span>
                  <p>No active execution</p>
                  <p className="empty-hint">Enter a command below to get started</p>
                </div>
              )}
            </div>
          </section>

          {/* Center Panel — Live Logs */}
          <section className="panel panel-logs">
            <div className="panel-header">
              <h2>
                <span className="panel-icon">📡</span>
                Live Logs
              </h2>
              <span className="log-counter">{logs.length} entries</span>
            </div>
            <div className="panel-body">
              <LiveLogs logs={logs} />
            </div>
          </section>

          {/* Right Panel — AI Reasoning */}
          <section className="panel panel-reasoning">
            <div className="panel-header">
              <h2>
                <span className="panel-icon">🧠</span>
                AI Reasoning
              </h2>
            </div>
            <div className="panel-body">
              <ReasoningPanel reasoning={reasoning} />
              {reasoning.length === 0 && (
                <div className="empty-state">
                  <span className="empty-icon">💭</span>
                  <p>Chain-of-thought will appear here</p>
                </div>
              )}
            </div>
          </section>
        </div>

        <div style={{ marginTop: '16px', marginBottom: '16px' }}>
          <MemoryPanel />
        </div>

        {/* Bottom — User Controls */}
        <UserControls
          onCommand={handleCommand}
          onControl={handleControl}
          isExecuting={isExecuting}
          history={history}
        />
      </main>
    </div>
  )
}

export default App

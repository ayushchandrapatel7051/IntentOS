/**
 * MemoryPanel — RAG Memory Explorer for OpenClaw Dashboard
 * 
 * Aesthetic: dark terminal-meets-neural-net
 * Shows: semantic workflow search, knowledge base, failure patterns
 */

import { useState, useEffect, useCallback } from "react"

const API_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) 
  || 'http://localhost:8000/api'

// ── Hex grid background effect ──────────────────────────────────────────
const HexPattern = () => (
  <svg 
    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.04, pointerEvents: 'none' }}
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs>
      <pattern id="hex" x="0" y="0" width="56" height="48" patternUnits="userSpaceOnUse">
        <polygon 
          points="14,2 42,2 56,24 42,46 14,46 0,24" 
          fill="none" 
          stroke="#00ff88" 
          strokeWidth="0.8"
        />
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#hex)" />
  </svg>
)

// ── Similarity badge ─────────────────────────────────────────────────────
const SimBadge = ({ sim }) => {
  const pct = Math.round(sim * 100)
  const color = pct > 80 ? '#00ff88' : pct > 60 ? '#ffcc00' : '#ff6644'
  return (
    <span style={{
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: '10px',
      padding: '2px 7px',
      borderRadius: '3px',
      border: `1px solid ${color}33`,
      background: `${color}11`,
      color,
      fontWeight: 700,
      flexShrink: 0,
    }}>
      {pct}%
    </span>
  )
}

// ── Outcome chip ─────────────────────────────────────────────────────────
const OutcomeChip = ({ outcome }) => {
  const map = {
    completed: { color: '#00ff88', label: 'DONE' },
    failed: { color: '#ff4455', label: 'FAIL' },
    aborted: { color: '#ffaa33', label: 'STOP' },
  }
  const { color, label } = map[outcome] || { color: '#888', label: outcome?.toUpperCase() || '?' }
  return (
    <span style={{
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: '9px',
      padding: '1px 6px',
      borderRadius: '2px',
      background: `${color}18`,
      color,
      fontWeight: 800,
      border: `1px solid ${color}44`,
      letterSpacing: '0.1em',
    }}>
      {label}
    </span>
  )
}

// ── Tab bar ──────────────────────────────────────────────────────────────
const Tab = ({ label, icon, active, onClick, count }) => (
  <button onClick={onClick} style={{
    background: active ? '#00ff8815' : 'transparent',
    border: 'none',
    borderBottom: active ? '2px solid #00ff88' : '2px solid transparent',
    color: active ? '#00ff88' : '#556688',
    padding: '8px 14px',
    cursor: 'pointer',
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'all 150ms',
    whiteSpace: 'nowrap',
  }}>
    <span>{icon}</span>
    {label}
    {count !== undefined && (
      <span style={{
        background: active ? '#00ff8833' : '#22334455',
        color: active ? '#00ff88' : '#556688',
        borderRadius: '10px',
        padding: '0 6px',
        fontSize: '9px',
        minWidth: '18px',
        textAlign: 'center',
      }}>
        {count}
      </span>
    )}
  </button>
)

// ── Search input ─────────────────────────────────────────────────────────
const SearchBox = ({ value, onChange, onSearch, placeholder, loading }) => (
  <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
    <div style={{ flex: 1, position: 'relative' }}>
      <span style={{
        position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)',
        color: '#445566', fontSize: '13px', pointerEvents: 'none',
      }}>⌕</span>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && onSearch()}
        placeholder={placeholder}
        style={{
          width: '100%',
          background: '#090d16',
          border: '1px solid #1a2840',
          borderRadius: '6px',
          color: '#c8d8f0',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '12px',
          padding: '8px 10px 8px 30px',
          outline: 'none',
          transition: 'border-color 150ms',
        }}
        onFocus={e => e.target.style.borderColor = '#00ff8866'}
        onBlur={e => e.target.style.borderColor = '#1a2840'}
      />
    </div>
    <button onClick={onSearch} disabled={loading} style={{
      background: loading ? '#0a1a2a' : '#00ff8818',
      border: '1px solid #00ff8844',
      borderRadius: '6px',
      color: '#00ff88',
      padding: '8px 14px',
      cursor: loading ? 'wait' : 'pointer',
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: '11px',
      fontWeight: 700,
      display: 'flex',
      alignItems: 'center',
      gap: '5px',
      whiteSpace: 'nowrap',
    }}>
      {loading ? '⋯' : '◉'} {loading ? 'Searching' : 'Search'}
    </button>
  </div>
)

// ── Workflow result card ──────────────────────────────────────────────────
const WorkflowCard = ({ item }) => {
  const [expanded, setExpanded] = useState(false)
  let steps = []
  try { steps = JSON.parse(item.plan_json || '{}').steps || [] } catch {}

  return (
    <div style={{
      background: '#0a1221',
      border: '1px solid #1a2840',
      borderRadius: '8px',
      padding: '10px 12px',
      marginBottom: '8px',
      cursor: 'pointer',
      transition: 'border-color 150ms',
    }}
    onClick={() => setExpanded(x => !x)}
    onMouseEnter={e => e.currentTarget.style.borderColor = '#00ff8844'}
    onMouseLeave={e => e.currentTarget.style.borderColor = '#1a2840'}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <SimBadge sim={item.similarity} />
        <OutcomeChip outcome={item.outcome} />
        <span style={{ color: '#c8d8f0', fontSize: '12px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.intent}
        </span>
        <span style={{ color: '#334466', fontSize: '10px', fontFamily: 'monospace', flexShrink: 0 }}>
          {item.step_count}s
        </span>
        <span style={{ color: '#334466', fontSize: '11px' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && steps.length > 0 && (
        <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #1a2840' }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
              <span style={{ color: '#334466', fontFamily: 'monospace', fontSize: '10px', width: '20px' }}>
                {i + 1}.
              </span>
              <span style={{
                background: '#0d1f35', border: '1px solid #1a3050',
                borderRadius: '3px', padding: '1px 6px',
                color: '#4488cc', fontFamily: 'monospace', fontSize: '10px',
              }}>
                {s.skill}
              </span>
              <span style={{ color: '#00cc88', fontFamily: 'monospace', fontSize: '10px' }}>
                .{s.action}
              </span>
              <span style={{ color: '#445566', fontSize: '10px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.description}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Knowledge result card ─────────────────────────────────────────────────
const KnowledgeCard = ({ item }) => {
  const [expanded, setExpanded] = useState(false)
  const preview = item.content?.replace(/SOURCE:[^\n]*\n?TITLE:[^\n]*\n?/, '').trim().slice(0, 300)
  
  return (
    <div style={{
      background: '#0a1221',
      border: '1px solid #1a2840',
      borderRadius: '8px',
      padding: '10px 12px',
      marginBottom: '8px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <SimBadge sim={item.similarity} />
        <span style={{ color: '#88aaff', fontSize: '12px', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.title || 'Untitled'}
        </span>
        {item.tags?.length > 0 && item.tags.map(t => (
          <span key={t} style={{
            background: '#1a2840', color: '#4477aa',
            borderRadius: '3px', padding: '1px 5px',
            fontSize: '9px', fontFamily: 'monospace',
          }}>{t}</span>
        ))}
      </div>
      {item.source && (
        <div style={{ color: '#334466', fontFamily: 'monospace', fontSize: '10px', marginBottom: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          ⌂ {item.source}
        </div>
      )}
      <div style={{ color: '#778899', fontSize: '11px', lineHeight: 1.5 }}>
        {expanded ? (item.content || '').slice(0, 1200) : preview}
        {(item.content?.length || 0) > 300 && (
          <button onClick={() => setExpanded(x => !x)} style={{
            background: 'none', border: 'none', color: '#00ff8888',
            cursor: 'pointer', fontFamily: 'monospace', fontSize: '10px', padding: '0 4px',
          }}>
            {expanded ? ' [collapse]' : '... [expand]'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Failure card ─────────────────────────────────────────────────────────
const FailureCard = ({ item }) => (
  <div style={{
    background: '#120a0a',
    border: '1px solid #3a1818',
    borderRadius: '8px',
    padding: '10px 12px',
    marginBottom: '8px',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
      <SimBadge sim={item.similarity} />
      <span style={{ background: '#2a0a0a', border: '1px solid #ff444433', borderRadius: '3px', padding: '1px 6px', color: '#ff6655', fontFamily: 'monospace', fontSize: '10px' }}>
        {item.skill}.{item.action}
      </span>
    </div>
    <div style={{ color: '#aa5544', fontFamily: 'monospace', fontSize: '11px', lineHeight: 1.4 }}>
      ✗ {item.error}
    </div>
  </div>
)

// ── Stats bar ─────────────────────────────────────────────────────────────
const StatsBar = ({ stats }) => {
  if (!stats) return null
  const items = [
    { label: 'Workflows', value: stats.workflows, color: '#00ff88' },
    { label: 'Knowledge', value: stats.knowledge, color: '#4488ff' },
    { label: 'Failures', value: stats.failures, color: '#ff4455' },
  ]
  return (
    <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
      {items.map(({ label, value, color }) => (
        <div key={label} style={{
          flex: 1, background: '#090d16', border: `1px solid ${color}22`,
          borderRadius: '8px', padding: '10px 14px',
        }}>
          <div style={{ color, fontFamily: "'JetBrains Mono', monospace", fontSize: '22px', fontWeight: 700, lineHeight: 1 }}>
            {value ?? '—'}
          </div>
          <div style={{ color: '#445566', fontFamily: 'monospace', fontSize: '10px', marginTop: '3px', letterSpacing: '0.1em' }}>
            {label.toUpperCase()}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Add Knowledge form ────────────────────────────────────────────────────
const AddKnowledgeForm = ({ onAdd }) => {
  const [form, setForm] = useState({ content: '', title: '', source: '' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSubmit = async () => {
    if (!form.content.trim()) return
    setSaving(true)
    try {
      const r = await fetch(`${API_URL}/rag/knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, tags: ['manual'] }),
      })
      if (r.ok) {
        setSaved(true)
        setForm({ content: '', title: '', source: '' })
        onAdd?.()
        setTimeout(() => setSaved(false), 2000)
      }
    } catch {}
    setSaving(false)
  }

  const inputStyle = {
    width: '100%', background: '#090d16', border: '1px solid #1a2840',
    borderRadius: '6px', color: '#c8d8f0', fontFamily: "'JetBrains Mono', monospace",
    fontSize: '12px', padding: '8px 10px', outline: 'none', boxSizing: 'border-box',
    marginBottom: '8px', transition: 'border-color 150ms',
  }

  return (
    <div style={{ background: '#0a1221', border: '1px solid #1a2840', borderRadius: '8px', padding: '14px' }}>
      <div style={{ color: '#445566', fontFamily: 'monospace', fontSize: '10px', letterSpacing: '0.1em', marginBottom: '10px' }}>
        ✦ ADD KNOWLEDGE
      </div>
      <input
        value={form.title}
        onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
        placeholder="Title..."
        style={inputStyle}
        onFocus={e => e.target.style.borderColor = '#4488ff66'}
        onBlur={e => e.target.style.borderColor = '#1a2840'}
      />
      <input
        value={form.source}
        onChange={e => setForm(f => ({ ...f, source: e.target.value }))}
        placeholder="Source URL or path..."
        style={inputStyle}
        onFocus={e => e.target.style.borderColor = '#4488ff66'}
        onBlur={e => e.target.style.borderColor = '#1a2840'}
      />
      <textarea
        value={form.content}
        onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
        placeholder="Content to remember..."
        rows={4}
        style={{ ...inputStyle, resize: 'vertical', marginBottom: '10px' }}
        onFocus={e => e.target.style.borderColor = '#4488ff66'}
        onBlur={e => e.target.style.borderColor = '#1a2840'}
      />
      <button onClick={handleSubmit} disabled={saving || !form.content.trim()} style={{
        background: saved ? '#00ff8818' : '#1a2840',
        border: `1px solid ${saved ? '#00ff8844' : '#2a3a50'}`,
        borderRadius: '6px', color: saved ? '#00ff88' : '#4488cc',
        padding: '8px 16px', cursor: 'pointer',
        fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', fontWeight: 700,
      }}>
        {saving ? '⋯ Saving...' : saved ? '✓ Saved!' : '+ Add to Memory'}
      </button>
    </div>
  )
}

// ── Main MemoryPanel component ────────────────────────────────────────────
export default function MemoryPanel() {
  const [tab, setTab] = useState('search')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState(null)
  const [collection, setCollection] = useState('workflows')
  const [error, setError] = useState('')

  const fetchStats = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/rag/stats`)
      if (r.ok) setStats(await r.json())
    } catch {
      setStats(null)
    }
  }, [])

  useEffect(() => {
    fetchStats()
    const id = setInterval(fetchStats, 10000)
    return () => clearInterval(id)
  }, [fetchStats])

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      const r = await fetch(`${API_URL}/rag/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, n_results: 6, collection }),
      })
      if (r.ok) {
        const data = await r.json()
        setResults(data.results || [])
        if ((data.results || []).length === 0) setError('No matching memories found')
      } else {
        setError('Search failed — is the backend running?')
      }
    } catch {
      setError('Cannot reach backend — start OpenClaw first')
    }
    setLoading(false)
  }

  const handleSync = async () => {
    try {
      await fetch(`${API_URL}/rag/sync`, { method: 'POST' })
      await fetchStats()
    } catch {}
  }

  const notReady = stats && !stats.ready

  return (
    <div style={{
      background: '#060c18',
      borderRadius: '12px',
      border: '1px solid #0d1f35',
      overflow: 'hidden',
      fontFamily: 'system-ui, sans-serif',
      minHeight: '500px',
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <HexPattern />

      {/* Header */}
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid #0d1f35',
        background: '#08101f',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        position: 'relative',
      }}>
        <div style={{
          width: '8px', height: '8px', borderRadius: '50%',
          background: stats?.ready ? '#00ff88' : '#ff4455',
          boxShadow: stats?.ready ? '0 0 8px #00ff88' : '0 0 4px #ff4455',
        }} />
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: '13px',
          fontWeight: 700, color: '#c8d8f0', letterSpacing: '0.05em',
        }}>
          NEURAL MEMORY
        </span>
        <span style={{ color: '#223344', fontFamily: 'monospace', fontSize: '10px' }}>
          / RAG STORE
        </span>
        <div style={{ flex: 1 }} />
        <button onClick={handleSync} title="Sync YAML workflows" style={{
          background: '#0d1f35', border: '1px solid #1a3050',
          borderRadius: '5px', color: '#4477aa',
          padding: '4px 10px', cursor: 'pointer',
          fontFamily: 'monospace', fontSize: '10px',
        }}>
          ↺ Sync
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid #0d1f35',
        background: '#07101e',
        overflowX: 'auto',
      }}>
        <Tab label="SEARCH" icon="⌕" active={tab === 'search'} onClick={() => setTab('search')} />
        <Tab label="WORKFLOWS" icon="◈" active={tab === 'workflows'} onClick={() => { setTab('workflows'); setCollection('workflows') }} count={stats?.workflows} />
        <Tab label="KNOWLEDGE" icon="◉" active={tab === 'knowledge'} onClick={() => { setTab('knowledge'); setCollection('knowledge') }} count={stats?.knowledge} />
        <Tab label="FAILURES" icon="✗" active={tab === 'failures'} onClick={() => { setTab('failures'); setCollection('failures') }} count={stats?.failures} />
        <Tab label="ADD" icon="+" active={tab === 'add'} onClick={() => setTab('add')} />
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '16px 18px', overflow: 'auto' }}>

        {notReady && (
          <div style={{
            background: '#1a0a00', border: '1px solid #ff440033',
            borderRadius: '8px', padding: '14px 16px', marginBottom: '16px',
            color: '#ff7744', fontFamily: 'monospace', fontSize: '12px', lineHeight: 1.5,
          }}>
            ⚠ RAG store not initialized.<br />
            Install: <code style={{ background: '#220a00', padding: '2px 6px', borderRadius: '3px' }}>
              pip install chromadb sentence-transformers
            </code><br />
            Then restart OpenClaw.
          </div>
        )}

        <StatsBar stats={stats} />

        {/* Search tab */}
        {tab === 'search' && (
          <>
            <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
              {['workflows', 'knowledge', 'failures'].map(c => (
                <button key={c} onClick={() => setCollection(c)} style={{
                  background: collection === c ? '#00ff8818' : '#0a1221',
                  border: `1px solid ${collection === c ? '#00ff8844' : '#1a2840'}`,
                  borderRadius: '4px', color: collection === c ? '#00ff88' : '#445566',
                  padding: '4px 10px', cursor: 'pointer',
                  fontFamily: 'monospace', fontSize: '10px', fontWeight: 700,
                }}>
                  {c.toUpperCase()}
                </button>
              ))}
            </div>
            <SearchBox
              value={query}
              onChange={setQuery}
              onSearch={handleSearch}
              placeholder={`Search ${collection}...`}
              loading={loading}
            />
            {error && (
              <div style={{ color: '#ff5544', fontFamily: 'monospace', fontSize: '11px', marginBottom: '10px' }}>
                {error}
              </div>
            )}
            {results.map((item, i) => (
              collection === 'workflows' ? <WorkflowCard key={i} item={item} /> :
              collection === 'knowledge' ? <KnowledgeCard key={i} item={item} /> :
              <FailureCard key={i} item={item} />
            ))}
          </>
        )}

        {/* Workflows tab - search preset */}
        {(tab === 'workflows' || tab === 'failures') && tab !== 'search' && (
          <>
            <SearchBox
              value={query}
              onChange={setQuery}
              onSearch={handleSearch}
              placeholder={`Search ${tab}...`}
              loading={loading}
            />
            {error && <div style={{ color: '#ff5544', fontFamily: 'monospace', fontSize: '11px', marginBottom: '10px' }}>{error}</div>}
            {results.length === 0 && !loading && !error && (
              <div style={{ color: '#334455', fontFamily: 'monospace', fontSize: '12px', textAlign: 'center', padding: '40px 0' }}>
                {stats?.[tab] === 0
                  ? `No ${tab} recorded yet. Run some commands first.`
                  : `Type a query to search ${stats?.[tab] || 0} ${tab}`
                }
              </div>
            )}
            {results.map((item, i) =>
              tab === 'failures' ? <FailureCard key={i} item={item} /> : <WorkflowCard key={i} item={item} />
            )}
          </>
        )}

        {/* Knowledge tab */}
        {tab === 'knowledge' && (
          <>
            <SearchBox
              value={query}
              onChange={setQuery}
              onSearch={handleSearch}
              placeholder="Search knowledge base..."
              loading={loading}
            />
            {error && <div style={{ color: '#ff5544', fontFamily: 'monospace', fontSize: '11px', marginBottom: '10px' }}>{error}</div>}
            {results.length === 0 && !loading && !error && (
              <div style={{ color: '#334455', fontFamily: 'monospace', fontSize: '12px', textAlign: 'center', padding: '40px 0' }}>
                {stats?.knowledge === 0
                  ? 'No knowledge stored yet. Extract page content to populate.'
                  : `Search ${stats?.knowledge || 0} knowledge documents`
                }
              </div>
            )}
            {results.map((item, i) => <KnowledgeCard key={i} item={item} />)}
          </>
        )}

        {/* Add knowledge tab */}
        {tab === 'add' && (
          <AddKnowledgeForm onAdd={fetchStats} />
        )}
      </div>
    </div>
  )
}

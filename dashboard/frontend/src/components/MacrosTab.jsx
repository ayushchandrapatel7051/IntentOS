import { useState, useEffect } from 'react'

const API = 'http://localhost:8000/api'

const ICONS = ['⚡','🌅','🌙','💻','📋','🚀','🔧','📧','📁','🎯','🔔','🌐','💡','🎵','📊']

function emptyMacro() {
  return { id: '', label: '', description: '', icon: '⚡', trigger_phrases: '', tags: '', steps: [] }
}
function emptyStep() {
  return { skill: '', action: '', label: '', params: {} }
}

export default function MacrosTab() {
  const [macros, setMacros]     = useState([])
  const [selected, setSelected] = useState(null)   // macro being edited
  const [form, setForm]         = useState(emptyMacro())
  const [stepForm, setStepForm] = useState(emptyStep())
  const [adding, setAdding]     = useState(false)   // new vs edit
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [toast, setToast]       = useState(null)
  const [search, setSearch]     = useState('')
  const [confirmDel, setConfirmDel] = useState(null)

  useEffect(() => { load() }, [])

  const load = () =>
    fetch(`${API}/macros`).then(r => r.json()).then(d => setMacros(d.macros || [])).catch(() => {})

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  const openNew = () => {
    setForm(emptyMacro())
    setSelected(null)
    setAdding(true)
    setStepForm(emptyStep())
  }

  const openEdit = (m) => {
    setForm({
      ...m,
      trigger_phrases: (m.trigger_phrases || []).join(', '),
      tags: (m.tags || []).join(', '),
    })
    setSelected(m.id)
    setAdding(false)
    setStepForm(emptyStep())
  }

  const closeEditor = () => { setSelected(null); setAdding(false) }

  const handleSave = async () => {
    if (!form.label.trim()) return showToast('Label is required', false)
    setSaving(true)
    const payload = {
      id: form.id || form.label.trim().toLowerCase().replace(/\s+/g, '_'),
      label: form.label.trim(),
      description: form.description,
      icon: form.icon,
      trigger_phrases: form.trigger_phrases.split(',').map(s => s.trim()).filter(Boolean),
      tags: form.tags.split(',').map(s => s.trim()).filter(Boolean),
      steps: form.steps || [],
    }
    const r = await fetch(`${API}/macros`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const d = await r.json()
    setSaving(false)
    if (r.ok) { showToast(d.message || 'Saved!'); load(); closeEditor() }
    else showToast(d.detail || 'Save failed', false)
  }

  const handleDelete = async (id) => {
    setDeleting(id)
    const r = await fetch(`${API}/macros/${id}`, { method: 'DELETE' })
    const d = await r.json()
    setDeleting(null)
    setConfirmDel(null)
    if (r.ok) { showToast(d.message || 'Deleted'); load(); if (selected === id) closeEditor() }
    else showToast(d.detail || 'Delete failed', false)
  }

  const addStep = () => {
    if (!stepForm.skill || !stepForm.action) return
    setForm(f => ({ ...f, steps: [...(f.steps || []), { ...stepForm, params: {} }] }))
    setStepForm(emptyStep())
  }

  const removeStep = (i) => setForm(f => ({ ...f, steps: f.steps.filter((_, idx) => idx !== i) }))

  const filtered = macros.filter(m =>
    !search || m.label.toLowerCase().includes(search.toLowerCase()) ||
    (m.description || '').toLowerCase().includes(search.toLowerCase())
  )

  const editorOpen = adding || selected !== null

  return (
    <div style={{ display: 'flex', height: '100%', gap: 0, overflow: 'hidden' }}>

      {/* ── Left: macro list ── */}
      <div style={{
        width: editorOpen ? 280 : '100%', flexShrink: 0,
        borderRight: editorOpen ? '0.5px solid rgba(255,255,255,0.06)' : 'none',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        transition: 'width 0.2s ease',
      }}>
        {/* Header */}
        <div style={{ padding: '16px 18px 12px', borderBottom: '0.5px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 9, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.6)', letterSpacing: '2px', marginBottom: 3 }}>SOUL.md</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#e8eaf0' }}>Macros <span style={{ fontSize: 11, color: '#4b5563', fontWeight: 400 }}>({macros.length})</span></div>
            </div>
            <button
              onClick={openNew}
              style={{
                background: 'rgba(0,212,170,0.12)', border: '1px solid rgba(0,212,170,0.25)',
                color: '#00d4aa', borderRadius: 8, padding: '6px 12px', cursor: 'pointer',
                fontSize: 12, fontWeight: 600, fontFamily: 'Inter, sans-serif',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >+ New</button>
          </div>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search macros…"
            style={{
              width: '100%', background: 'rgba(255,255,255,0.03)',
              border: '0.5px solid rgba(255,255,255,0.08)', borderRadius: 7,
              padding: '7px 11px', fontSize: 12, color: '#e8eaf0',
              fontFamily: 'Inter, sans-serif', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* List */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '8px 10px' }}>
          {filtered.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: 40, color: '#374151', fontSize: 12, fontFamily: 'Space Mono, monospace' }}>
              {macros.length === 0 ? 'No macros yet.\nClick + New to create one.' : 'No results.'}
            </div>
          )}
          {filtered.map(m => (
            <div
              key={m.id}
              onClick={() => openEdit(m)}
              style={{
                padding: '10px 12px', borderRadius: 9, marginBottom: 5, cursor: 'pointer',
                background: selected === m.id ? 'rgba(0,212,170,0.08)' : 'rgba(255,255,255,0.02)',
                border: `0.5px solid ${selected === m.id ? 'rgba(0,212,170,0.2)' : 'rgba(255,255,255,0.05)'}`,
                transition: 'all 0.15s',
                position: 'relative',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <span style={{ fontSize: 18, flexShrink: 0 }}>{m.icon || '⚡'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#e8eaf0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.label}</div>
                  {m.description && <div style={{ fontSize: 10, color: '#4b5563', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.description}</div>}
                </div>
                <button
                  onClick={e => { e.stopPropagation(); setConfirmDel(m.id) }}
                  style={{
                    background: 'none', border: 'none', color: '#374151', cursor: 'pointer',
                    fontSize: 14, padding: '2px 4px', borderRadius: 4, flexShrink: 0,
                    transition: 'color 0.15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                  onMouseLeave={e => e.currentTarget.style.color = '#374151'}
                >✕</button>
              </div>
              {m.trigger_phrases?.length > 0 && (
                <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {m.trigger_phrases.slice(0, 3).map(p => (
                    <span key={p} style={{
                      fontSize: 9, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.55)',
                      background: 'rgba(0,212,170,0.06)', border: '0.5px solid rgba(0,212,170,0.12)',
                      padding: '1px 6px', borderRadius: 3,
                    }}>"{p}"</span>
                  ))}
                  {m.trigger_phrases.length > 3 && <span style={{ fontSize: 9, color: '#374151', fontFamily: 'Space Mono, monospace' }}>+{m.trigger_phrases.length - 3}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: editor ── */}
      {editorOpen && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Editor header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e8eaf0' }}>
              {adding ? 'New Macro' : `Editing: ${form.label}`}
            </div>
            <button onClick={closeEditor} style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>✕</button>
          </div>

          {/* Icon picker */}
          <Field label="Icon">
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {ICONS.map(ic => (
                <button key={ic} onClick={() => setForm(f => ({ ...f, icon: ic }))}
                  style={{
                    fontSize: 20, background: form.icon === ic ? 'rgba(0,212,170,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${form.icon === ic ? 'rgba(0,212,170,0.35)' : 'rgba(255,255,255,0.07)'}`,
                    borderRadius: 7, width: 36, height: 36, cursor: 'pointer', transition: 'all 0.12s',
                  }}
                >{ic}</button>
              ))}
            </div>
          </Field>

          {/* ID (only new) */}
          {adding && (
            <Field label="ID (auto-generated from label if left blank)">
              <Input value={form.id} onChange={v => setForm(f => ({ ...f, id: v }))} placeholder="e.g. my_morning_routine" mono />
            </Field>
          )}

          <Field label="Label *">
            <Input value={form.label} onChange={v => setForm(f => ({ ...f, label: v }))} placeholder="e.g. Start My Day" />
          </Field>

          <Field label="Description">
            <Input value={form.description} onChange={v => setForm(f => ({ ...f, description: v }))} placeholder="Short description…" />
          </Field>

          <Field label="Trigger Phrases (comma-separated)">
            <Input value={form.trigger_phrases} onChange={v => setForm(f => ({ ...f, trigger_phrases: v }))} placeholder="e.g. start my day, good morning, morning routine" />
          </Field>

          <Field label="Tags (comma-separated)">
            <Input value={form.tags} onChange={v => setForm(f => ({ ...f, tags: v }))} placeholder="e.g. daily, morning, routine" />
          </Field>

          {/* Steps */}
          <div>
            <div style={{ fontSize: 10, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.6)', letterSpacing: '1.5px', marginBottom: 8 }}>STEPS ({(form.steps||[]).length})</div>
            {(form.steps || []).map((s, i) => (
              <div key={i} style={{
                background: 'rgba(255,255,255,0.025)', border: '0.5px solid rgba(255,255,255,0.07)',
                borderRadius: 8, padding: '10px 12px', marginBottom: 6,
                display: 'flex', alignItems: 'flex-start', gap: 10,
              }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 9, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.5)' }}>{s.skill}.{s.action}</span>
                  {s.label && <div style={{ fontSize: 12, color: '#e8eaf0', marginTop: 2 }}>{s.label}</div>}
                </div>
                <button onClick={() => removeStep(i)} style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 13 }}
                  onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                  onMouseLeave={e => e.currentTarget.style.color = '#4b5563'}
                >✕</button>
              </div>
            ))}

            {/* Add step */}
            <div style={{
              background: 'rgba(255,255,255,0.02)', border: '0.5px dashed rgba(255,255,255,0.08)',
              borderRadius: 8, padding: '12px 14px', marginTop: 4,
            }}>
              <div style={{ fontSize: 10, fontFamily: 'Space Mono, monospace', color: '#4b5563', marginBottom: 8, letterSpacing: '1px' }}>ADD STEP</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <Input value={stepForm.skill} onChange={v => setStepForm(f => ({ ...f, skill: v }))} placeholder="skill (e.g. terminal)" mono small />
                <Input value={stepForm.action} onChange={v => setStepForm(f => ({ ...f, action: v }))} placeholder="action (e.g. execute)" mono small />
              </div>
              <Input value={stepForm.label} onChange={v => setStepForm(f => ({ ...f, label: v }))} placeholder="Step label (description)" small />
              <button
                onClick={addStep}
                disabled={!stepForm.skill || !stepForm.action}
                style={{
                  marginTop: 8, background: 'rgba(0,212,170,0.1)', border: '1px solid rgba(0,212,170,0.2)',
                  color: '#00d4aa', borderRadius: 6, padding: '6px 14px', cursor: 'pointer',
                  fontSize: 12, fontFamily: 'Inter, sans-serif', opacity: (!stepForm.skill || !stepForm.action) ? 0.4 : 1,
                }}
              >+ Add Step</button>
            </div>
          </div>

          {/* Save / Delete */}
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button
              onClick={handleSave} disabled={saving}
              style={{
                flex: 1, padding: '10px 0', borderRadius: 8, fontSize: 13, fontWeight: 600,
                background: '#00d4aa', color: '#0a0c0f', border: 'none', cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.7 : 1, fontFamily: 'Inter, sans-serif', transition: 'all 0.15s',
              }}
              onMouseEnter={e => { if (!saving) e.currentTarget.style.background = '#00bfa5' }}
              onMouseLeave={e => { e.currentTarget.style.background = '#00d4aa' }}
            >{saving ? '⟳ Saving…' : '✓ Save Macro'}</button>
            {!adding && (
              <button
                onClick={() => setConfirmDel(form.id || selected)}
                style={{
                  padding: '10px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                  background: 'rgba(239,68,68,0.1)', color: '#ef4444',
                  border: '1px solid rgba(239,68,68,0.25)', cursor: 'pointer', fontFamily: 'Inter, sans-serif',
                }}
              >Delete</button>
            )}
          </div>
        </div>
      )}

      {/* ── Delete confirm dialog ── */}
      {confirmDel && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
        }}>
          <div style={{
            background: '#14171d', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 12,
            padding: '24px 28px', width: 340, boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
          }}>
            <div style={{ fontSize: 20, marginBottom: 10 }}>🗑️</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e8eaf0', marginBottom: 6 }}>Delete macro?</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 20, fontFamily: 'Space Mono, monospace' }}>{confirmDel}</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setConfirmDel(null)} style={{ flex: 1, padding: '8px 0', borderRadius: 7, fontSize: 12, background: 'rgba(255,255,255,0.05)', border: '0.5px solid rgba(255,255,255,0.1)', color: '#6b7280', cursor: 'pointer' }}>Cancel</button>
              <button
                onClick={() => handleDelete(confirmDel)}
                disabled={deleting === confirmDel}
                style={{ flex: 1, padding: '8px 0', borderRadius: 7, fontSize: 12, fontWeight: 600, background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', cursor: 'pointer' }}
              >{deleting === confirmDel ? '⟳ Deleting…' : 'Delete'}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 10000,
          background: toast.ok ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
          border: `1px solid ${toast.ok ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
          color: toast.ok ? '#10b981' : '#ef4444',
          borderRadius: 10, padding: '10px 16px', fontSize: 13, fontFamily: 'Inter, sans-serif',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          animation: 'fa-slide-in 0.25s ease',
        }}>{toast.ok ? '✓' : '✕'} {toast.msg}</div>
      )}
    </div>
  )
}

// ── Small helpers ────────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 10, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.6)', letterSpacing: '1.5px', marginBottom: 6 }}>{label.toUpperCase()}</div>
      {children}
    </div>
  )
}

function Input({ value, onChange, placeholder, mono, small }) {
  return (
    <input
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: '100%', boxSizing: 'border-box',
        background: 'rgba(255,255,255,0.03)', border: '0.5px solid rgba(255,255,255,0.09)',
        borderRadius: 7, padding: small ? '6px 10px' : '8px 12px',
        fontSize: small ? 11 : 12, color: '#e8eaf0', outline: 'none',
        fontFamily: mono ? 'Space Mono, monospace' : 'Inter, sans-serif',
        transition: 'border-color 0.15s',
      }}
      onFocus={e => e.target.style.borderColor = 'rgba(0,212,170,0.35)'}
      onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.09)'}
    />
  )
}

/**
 * ExecutionTimeline — Workflow orchestration visualization.
 * Uses Font Awesome icons via the central icons.jsx registry.
 */

import { useState } from 'react'
import { I, skillIcon } from '../icons'
import {
  faCheck, faXmark, faSpinner,
  faAngleRight, faArrowsRotate, faClipboard, faBolt, faGear,
} from '../icons'

// ── Sanitize raw result text ────────────────────────────────────────────────
function sanitize(text) {
  if (!text || typeof text !== 'string') return null
  let t = text.replace(/\$\{[^}]+\}/g, '').trim()
  if (t.startsWith('{') || t.startsWith('[')) {
    try { JSON.parse(t); return null } catch {}
  }
  if (/^\[object /i.test(t)) return null
  if (t.length > 400) t = t.slice(0, 400) + '…'
  t = t.split('\n')
    .filter(l => !l.match(/^\s*(Traceback|File "|raise |Exception|Error:|at line \d|CategoryInfo|FullyQualifiedErrorId)/))
    .join('\n').trim()
  return t || null
}

// ── Status badge config ─────────────────────────────────────────────────────
const BADGE = {
  done:    { label: 'DONE',     color: '#10b981', bg: 'rgba(16,185,129,0.12)'  },
  running: { label: 'RUNNING',  color: '#f59e0b', bg: 'rgba(245,158,11,0.12)'  },
  failed:  { label: 'FAILED',   color: '#ef4444', bg: 'rgba(239,68,68,0.12)'   },
  skipped: { label: 'SKIPPED',  color: '#6b7280', bg: 'rgba(107,114,128,0.1)'  },
  pending: { label: 'QUEUED',   color: '#374151', bg: 'rgba(55,65,81,0.08)'    },
}
function badge(status) { return BADGE[status] || BADGE.pending }

// ── Timeline circle ─────────────────────────────────────────────────────────
function StepCircle({ status, index }) {
  const isDone = status === 'done'
  const isRun  = status === 'running'
  const isFail = status === 'failed'
  const isPend = !status || status === 'pending'

  const borderColor = isDone ? '#10b981' : isRun ? '#f59e0b' : isFail ? '#ef4444' : 'rgba(255,255,255,0.1)'
  const bgColor     = isDone ? 'rgba(16,185,129,0.12)' : isRun ? 'rgba(245,158,11,0.12)' : isFail ? 'rgba(239,68,68,0.1)' : 'rgba(255,255,255,0.03)'
  const glow        = isRun ? '0 0 14px rgba(245,158,11,0.35)' : isDone ? '0 0 10px rgba(16,185,129,0.2)' : 'none'

  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%',
      background: bgColor, border: `1.5px solid ${borderColor}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0, boxShadow: glow, transition: 'all 0.4s ease',
    }}>
      {isDone && <I icon={faCheck}   color="#10b981" size="xs" />}
      {isFail && <I icon={faXmark}  color="#ef4444" size="xs" />}
      {isRun  && <I icon={faSpinner} color="#f59e0b" size="xs" spin />}
      {isPend && <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', fontFamily: 'Space Mono, monospace' }}>{index + 1}</span>}
      {status === 'skipped' && <I icon={faXmark} color="#6b7280" size="xs" />}
    </div>
  )
}

// ── Single step card ────────────────────────────────────────────────────────
function StepCard({ step, index, totalSteps }) {
  const { icon, label } = skillIcon(step.skill, step.action, step.description)
  const b       = badge(step.status)
  const isDone  = step.status === 'done'
  const isRun   = step.status === 'running'
  const isFail  = step.status === 'failed'
  const isPend  = !step.status || step.status === 'pending'
  const cleanResult = isDone ? sanitize(step.result) : null

  return (
    <div style={{ display: 'flex', gap: 0, opacity: isPend ? 0.45 : 1, transition: 'opacity 0.35s ease' }}>
      {/* Spine */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 36, flexShrink: 0 }}>
        <StepCircle status={step.status} index={index} />
        {index < totalSteps - 1 && (
          <div style={{
            width: 1, flex: 1, minHeight: 14,
            background: isDone
              ? 'linear-gradient(180deg,rgba(16,185,129,0.5) 0%,rgba(16,185,129,0.08) 100%)'
              : 'rgba(255,255,255,0.06)',
            margin: '4px 0', transition: 'background 0.4s ease',
          }} />
        )}
      </div>

      {/* Card */}
      <div style={{
        flex: 1, marginLeft: 12,
        marginBottom: index < totalSteps - 1 ? 6 : 0,
        background: isRun
          ? 'linear-gradient(135deg,rgba(245,158,11,0.06) 0%,rgba(16,17,20,0.85) 100%)'
          : isDone ? 'rgba(16,185,129,0.03)' : 'rgba(255,255,255,0.015)',
        border: `0.5px solid ${isRun ? 'rgba(245,158,11,0.22)' : isDone ? 'rgba(16,185,129,0.12)' : isFail ? 'rgba(239,68,68,0.18)' : 'rgba(255,255,255,0.05)'}`,
        borderRadius: 9, padding: '11px 14px',
        transition: 'all 0.35s ease',
        boxShadow: isRun ? '0 4px 18px rgba(245,158,11,0.07)' : 'none',
      }}>
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Skill icon */}
          <span style={{
            width: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <I icon={icon} color={isDone ? '#10b981' : isRun ? '#f59e0b' : isFail ? '#ef4444' : 'rgba(255,255,255,0.3)'} size="sm" />
          </span>

          {/* Label */}
          <span style={{
            flex: 1, fontSize: 13, fontWeight: 500,
            color: isPend ? 'rgba(255,255,255,0.3)' : '#e8eaf0',
            letterSpacing: '0.1px',
          }}>{label}</span>

          {/* Status badge */}
          <span style={{
            fontSize: 9, fontFamily: 'Space Mono, monospace', fontWeight: 700,
            color: b.color, background: b.bg,
            padding: '2px 8px', borderRadius: 4, letterSpacing: '0.8px', flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 5,
            animation: isRun ? 'fa-badge-blink 1.4s ease-in-out infinite' : 'none',
          }}>
            {isRun && <I icon={faBolt} color="#f59e0b" size="xs" />}
            {isDone && <I icon={faCheck} color="#10b981" size="xs" />}
            {isFail && <I icon={faXmark} color="#ef4444" size="xs" />}
            {b.label}
          </span>
        </div>

        {/* Tool tag */}
        <div style={{ marginTop: 7, display: 'flex', gap: 5, alignItems: 'center' }}>
          <I icon={faGear} color="rgba(0,212,170,0.4)" size="xs" />
          <span style={{
            fontSize: 9, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.55)',
            background: 'rgba(0,212,170,0.05)', border: '0.5px solid rgba(0,212,170,0.12)',
            padding: '1px 7px', borderRadius: 3,
          }}>{step.skill}.{step.action}</span>
        </div>

        {/* Sanitized result */}
        {cleanResult && (
          <div style={{
            fontSize: 11, color: 'rgba(255,255,255,0.4)',
            fontFamily: 'Space Mono, monospace',
            marginTop: 8, borderTop: '0.5px solid rgba(255,255,255,0.05)',
            paddingTop: 7, lineHeight: 1.55, wordBreak: 'break-word',
          }}>{cleanResult}</div>
        )}

        {/* Error */}
        {isFail && step.error && (
          <div style={{
            fontSize: 11, color: 'rgba(239,68,68,0.75)',
            fontFamily: 'Space Mono, monospace',
            marginTop: 6, borderTop: '0.5px solid rgba(239,68,68,0.08)',
            paddingTop: 6,
          }}>{sanitize(step.error) || 'Step failed.'}</div>
        )}
      </div>
    </div>
  )
}

// ── Main ExecutionTimeline ──────────────────────────────────────────────────
export default function ExecutionTimeline({
  planStatus, planSummary, steps, logs,
  commandError, loading, badgeLabel, badgeClass,
  onRetry, onCopy, lastResult,
}) {
  const [showTrace, setShowTrace] = useState(false)

  const isIdle      = planStatus === 'idle' && !loading
  const isCompleted = planStatus === 'completed'
  const isFailed    = planStatus === 'failed'
  const isRunning   = planStatus === 'running' || loading

  const doneCount  = steps.filter(s => s.status === 'done').length
  const totalCount = steps.length
  const toolSet    = [...new Set(steps.map(s => s.skill).filter(Boolean))]

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px 28px', display: 'flex', flexDirection: 'column' }}>
      <style>{`
        @keyframes fa-badge-blink { 0%,100%{opacity:1} 50%{opacity:0.45} }
        @keyframes fa-slide-in { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes fa-skeleton { 0%,100%{opacity:0.3} 50%{opacity:0.07} }
      `}</style>

      {/* ── IDLE ── */}
      {isIdle && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, paddingTop: '8vh' }}>
          <I icon={faBolt} color="rgba(0,212,170,0.2)" size="2x" />
          <div style={{ fontSize: 17, color: '#e8eaf0', fontWeight: 500 }}>How can I help you today?</div>
          <div style={{ fontSize: 11, color: '#4b5563', fontFamily: 'Space Mono, monospace' }}>Type a request below to get started.</div>
        </div>
      )}

      {/* ── ACTIVE ── */}
      {!isIdle && (
        <div style={{ animation: 'fa-slide-in 0.4s ease forwards' }}>

          {/* Execution header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, gap: 12, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 9, fontFamily: 'Space Mono, monospace', color: 'rgba(0,212,170,0.55)', letterSpacing: '2px', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
                <I icon={isRunning ? faSpinner : isCompleted ? faCheck : faXmark}
                   color={isRunning ? '#f59e0b' : isCompleted ? '#10b981' : '#ef4444'}
                   size="xs" spin={isRunning} />
                {isRunning ? 'BUILDING EXECUTION PLAN' : isCompleted ? 'EXECUTION COMPLETE' : 'EXECUTION STOPPED'}
              </div>
              <div style={{ fontSize: 17, fontWeight: 600, color: '#e8eaf0', letterSpacing: '-0.3px', lineHeight: 1.35, maxWidth: 520 }}>
                {planSummary || (loading ? 'Planning…' : 'Processing')}
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
              <span className={badgeClass} style={{ fontSize: 9 }}>{badgeLabel}</span>
              {totalCount > 0 && (
                <span style={{ fontSize: 9, fontFamily: 'Space Mono, monospace', color: '#4b5563', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <I icon={faCheck} color="#4b5563" size="xs" />
                  {doneCount}/{totalCount} STEPS · {toolSet.length} TOOLS
                </span>
              )}
            </div>
          </div>

          {/* Timeline steps */}
          {steps.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 14 }}>
              {steps.map((step, i) => (
                <StepCard key={step.id} step={step} index={i} totalSteps={steps.length} />
              ))}
            </div>
          )}

          {/* Skeleton (no steps yet while running) */}
          {isRunning && steps.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1, 2, 3].map(i => (
                <div key={i} style={{
                  height: 58, borderRadius: 9,
                  background: 'rgba(255,255,255,0.02)',
                  border: '0.5px solid rgba(255,255,255,0.05)',
                  animation: `fa-skeleton ${0.9 + i * 0.2}s ease-in-out infinite`,
                }} />
              ))}
            </div>
          )}

          {/* Completion bar */}
          {isCompleted && (
            <div style={{
              background: 'linear-gradient(135deg,rgba(16,185,129,0.07) 0%,rgba(10,12,15,0.9) 100%)',
              border: '0.5px solid rgba(16,185,129,0.18)',
              borderRadius: 10, padding: '14px 18px', marginTop: 8,
              animation: 'fa-slide-in 0.5s ease forwards',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: '50%',
                  background: 'rgba(16,185,129,0.12)', border: '1.5px solid #10b981',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 0 14px rgba(16,185,129,0.2)',
                }}>
                  <I icon={faCheck} color="#10b981" size="sm" />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e8eaf0', marginBottom: 2 }}>Workflow Complete</div>
                  <div style={{ fontSize: 11, color: '#4b5563', fontFamily: 'Space Mono, monospace' }}>
                    {doneCount} step{doneCount !== 1 ? 's' : ''} executed successfully
                  </div>
                </div>
              </div>
              {lastResult && (
                <button onClick={() => onCopy && onCopy(lastResult)} style={{
                  background: 'rgba(255,255,255,0.04)', border: '0.5px solid rgba(255,255,255,0.08)',
                  color: '#6b7280', borderRadius: 6, padding: '5px 11px',
                  cursor: 'pointer', fontSize: 11, fontFamily: 'Space Mono, monospace',
                  display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.2s',
                }}>
                  <I icon={faClipboard} color="#6b7280" size="xs" /> Copy
                </button>
              )}
            </div>
          )}

          {/* Failure bar */}
          {isFailed && (
            <div style={{
              background: 'linear-gradient(135deg,rgba(239,68,68,0.07) 0%,rgba(10,12,15,0.9) 100%)',
              border: '0.5px solid rgba(239,68,68,0.18)',
              borderRadius: 10, padding: '14px 18px', marginTop: 8,
              animation: 'fa-slide-in 0.5s ease forwards',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <div style={{
                width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                background: 'rgba(239,68,68,0.1)', border: '1.5px solid rgba(239,68,68,0.35)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <I icon={faXmark} color="#ef4444" size="sm" />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#e8eaf0', marginBottom: 2 }}>Execution Stopped</div>
                {commandError && (
                  <div style={{ fontSize: 11, color: 'rgba(239,68,68,0.65)', fontFamily: 'Space Mono, monospace', lineHeight: 1.5 }}>
                    {sanitize(commandError) || commandError?.slice(0, 120) || 'An error occurred.'}
                  </div>
                )}
              </div>
              <button onClick={onRetry} style={{
                background: 'rgba(239,68,68,0.07)', border: '0.5px solid rgba(239,68,68,0.22)',
                color: '#ef4444', borderRadius: 6, padding: '5px 11px', cursor: 'pointer',
                fontSize: 11, fontFamily: 'Space Mono, monospace',
                display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
                transition: 'all 0.2s',
              }}>
                <I icon={faArrowsRotate} color="#ef4444" size="xs" /> Retry
              </button>
            </div>
          )}

          {/* Technical trace */}
          {(steps.length > 0 || logs.length > 0) && (
            <div style={{ marginTop: 18, borderTop: '0.5px solid rgba(255,255,255,0.05)', paddingTop: 12 }}>
              <button
                onClick={() => setShowTrace(v => !v)}
                style={{
                  background: 'none', border: 'none', color: '#374151', cursor: 'pointer',
                  fontSize: 11, fontFamily: 'Space Mono, monospace',
                  display: 'flex', alignItems: 'center', gap: 7, padding: 0, transition: 'color 0.2s',
                }}
              >
                <I icon={faAngleRight} color="#374151" size="xs" style={{ transform: showTrace ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }} />
                View Technical Trace
              </button>
              {showTrace && (
                <div style={{
                  marginTop: 10, padding: 12,
                  background: 'rgba(0,0,0,0.5)', border: '0.5px solid rgba(255,255,255,0.06)',
                  borderRadius: 8, fontFamily: 'Space Mono, monospace', fontSize: 10,
                  maxHeight: 260, overflowY: 'auto', color: '#374151',
                }}>
                  {logs.map((log, i) => (
                    <div key={i} style={{ marginBottom: 3, display: 'flex', gap: 8 }}>
                      <span style={{ color: '#1f2937', flexShrink: 0 }}>[{log.timestamp?.slice(11, 19) || ''}]</span>
                      <span style={{ color: log.level === 'ERROR' ? '#ef4444' : log.level === 'WARN' ? '#f59e0b' : '#00d4aa', flexShrink: 0 }}>[{log.level}]</span>
                      <span>{log.message}</span>
                    </div>
                  ))}
                  {steps.map((s, i) => (
                    <div key={i} style={{ marginBottom: 3, display: 'flex', gap: 8, opacity: 0.5 }}>
                      <span style={{ color: '#1f2937', flexShrink: 0 }}>[STEP]</span>
                      <span style={{ color: '#00d4aa', flexShrink: 0 }}>[{s.status?.toUpperCase()}]</span>
                      <span>{s.id}: {s.skill}.{s.action}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

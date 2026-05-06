/**
 * ExecutionTimeline — Workflow orchestration visualization.
 *
 * Renders the center execution area as a cinematic step-by-step timeline.
 * Consumes the same step/status props already maintained in App.jsx state.
 *
 * Output sanitization rules:
 *   - ${variable} tokens → hidden
 *   - raw JSON / object text → hidden
 *   - shell debug noise → hidden
 *   - only clean result summaries shown
 */

import { useState } from "react";

// ─── Sanitize raw result text ──────────────────────────────────────────────
function sanitize(text) {
  if (!text || typeof text !== "string") return null;
  // Remove unresolved ${var} tokens
  let t = text.replace(/\$\{[^}]+\}/g, "").trim();
  // Remove raw JSON dumps
  if (t.startsWith("{") || t.startsWith("[")) {
    try { JSON.parse(t); return null; } catch {}
  }
  // Remove object-looking noise
  if (/^\[object /i.test(t)) return null;
  // Remove shell paths / debug traces (long lines with backslashes/pipes)
  if (t.length > 400) t = t.slice(0, 400) + "…";
  // Remove terminal noise lines
  t = t.split("\n")
    .filter(l => !l.match(/^\s*(Traceback|File "|raise |Exception|Error:|at line \d|CategoryInfo|FullyQualifiedErrorId)/))
    .join("\n").trim();
  return t || null;
}

// ─── Skill → icon / label map ─────────────────────────────────────────────
function getStepMeta(step) {
  const { skill, action, description } = step;
  const toolTag = `${skill}.${action}`;

  const icons = {
    "browser.navigate":     { icon: "🌐", label: description || "Opening browser" },
    "browser.search":       { icon: "🔍", label: description || "Searching the web" },
    "files.write_file":     { icon: "📝", label: description || "Writing file" },
    "files.read_file":      { icon: "📖", label: description || "Reading file" },
    "files.create_dir":     { icon: "📁", label: description || "Creating directory" },
    "files.delete":         { icon: "🗑", label:  description || "Deleting file" },
    "files.move":           { icon: "📦", label: description || "Moving file" },
    "apps.open_app":        { icon: "🚀", label: description || "Launching application" },
    "terminal.execute":     { icon: "⚡", label: description || "Running command" },
    "ai.ask":               { icon: "🧠", label: description || "Thinking…" },
    "ai.summarize":         { icon: "📋", label: description || "Summarizing" },
    "extension.navigate":   { icon: "🌐", label: description || "Navigating page" },
    "extension.getEvents":  { icon: "📅", label: description || "Fetching calendar" },
    "extension.sendMail":   { icon: "✉️",  label: description || "Sending email" },
    "extension.getUnread":  { icon: "📬", label: description || "Checking inbox" },
    "messaging.send_message": { icon: "💬", label: description || "Sending message" },
  };

  return icons[toolTag] || {
    icon: skill === "extension" ? "🔌" : skill === "ai" ? "🧠" : "⚙️",
    label: description || toolTag,
  };
}

// ─── Status badge config ──────────────────────────────────────────────────
function stepBadge(status) {
  return {
    done:    { label: "DONE",    color: "#10b981", bg: "rgba(16,185,129,0.12)" },
    running: { label: "RUNNING…",color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
    failed:  { label: "FAILED",  color: "#ef4444", bg: "rgba(239,68,68,0.12)"  },
    skipped: { label: "SKIPPED", color: "#6b7280", bg: "rgba(107,114,128,0.1)" },
    pending: { label: "QUEUED",  color: "#4b5563", bg: "rgba(75,85,99,0.08)"   },
  }[status] || { label: "QUEUED", color: "#4b5563", bg: "rgba(75,85,99,0.08)" };
}

// ─── Single step card ─────────────────────────────────────────────────────
function StepCard({ step, index, totalSteps }) {
  const { icon, label } = getStepMeta(step);
  const badge  = stepBadge(step.status);
  const isDone = step.status === "done";
  const isRun  = step.status === "running";
  const isFail = step.status === "failed";
  const isPend = step.status === "pending" || !step.status;
  const cleanResult = isDone ? sanitize(step.result) : null;

  return (
    <div style={{
      display: "flex", gap: 0,
      opacity: isPend ? 0.5 : 1,
      transition: "opacity 0.3s ease",
    }}>
      {/* ── Timeline spine ── */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 36, flexShrink: 0 }}>
        {/* Circle */}
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: isDone ? "rgba(16,185,129,0.15)" : isRun ? "rgba(245,158,11,0.15)" : isFail ? "rgba(239,68,68,0.15)" : "rgba(255,255,255,0.04)",
          border: `1.5px solid ${isDone ? "#10b981" : isRun ? "#f59e0b" : isFail ? "#ef4444" : "rgba(255,255,255,0.12)"}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, flexShrink: 0,
          boxShadow: isRun ? "0 0 12px rgba(245,158,11,0.3)" : isDone ? "0 0 10px rgba(16,185,129,0.2)" : "none",
          animation: isRun ? "tl-pulse 1.8s ease-in-out infinite" : "none",
          transition: "all 0.4s ease",
        }}>
          {isDone ? <span style={{ color: "#10b981", fontWeight: 700, fontSize: 14 }}>✓</span>
           : isFail ? <span style={{ color: "#ef4444", fontWeight: 700, fontSize: 14 }}>✗</span>
           : isRun  ? <span style={{ color: "#f59e0b", fontSize: 11, fontWeight: 700 }}>{index + 1}</span>
           : <span style={{ color: "rgba(255,255,255,0.25)", fontSize: 11 }}>{index + 1}</span>}
        </div>
        {/* Connector */}
        {index < totalSteps - 1 && (
          <div style={{
            width: 1, flex: 1, minHeight: 16,
            background: isDone
              ? "linear-gradient(180deg,#10b981 0%,rgba(16,185,129,0.2) 100%)"
              : "rgba(255,255,255,0.07)",
            margin: "4px 0",
            transition: "background 0.4s ease",
          }} />
        )}
      </div>

      {/* ── Card body ── */}
      <div style={{
        flex: 1, marginLeft: 12, marginBottom: index < totalSteps - 1 ? 8 : 0,
        background: isRun
          ? "linear-gradient(135deg, rgba(245,158,11,0.07) 0%, rgba(20,20,20,0.8) 100%)"
          : isDone ? "rgba(16,185,129,0.04)" : "rgba(255,255,255,0.02)",
        border: `0.5px solid ${isRun ? "rgba(245,158,11,0.25)" : isDone ? "rgba(16,185,129,0.15)" : isFail ? "rgba(239,68,68,0.2)" : "rgba(255,255,255,0.06)"}`,
        borderRadius: 10, padding: "12px 16px",
        transition: "all 0.35s ease",
        boxShadow: isRun ? "0 4px 20px rgba(245,158,11,0.08)" : "none",
      }}>
        {/* Row 1 — icon + label + badge */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: cleanResult ? 8 : 0 }}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>{icon}</span>
          <span style={{
            flex: 1, fontSize: 13, fontWeight: 500, color: isPend ? "rgba(255,255,255,0.35)" : "#e8eaf0",
            letterSpacing: "0.1px",
          }}>{label}</span>
          {/* Badge */}
          <span style={{
            fontSize: 9, fontFamily: "Space Mono, monospace", fontWeight: 700,
            color: badge.color, background: badge.bg, padding: "2px 8px",
            borderRadius: 4, letterSpacing: "0.8px", flexShrink: 0,
            animation: isRun ? "badge-blink 1.5s ease-in-out infinite" : "none",
          }}>{badge.label}</span>
        </div>

        {/* Row 2 — tool tag */}
        <div style={{ display: "flex", gap: 6, marginBottom: cleanResult ? 8 : 0 }}>
          <span style={{
            fontSize: 9, fontFamily: "Space Mono, monospace", color: "rgba(0,212,170,0.6)",
            background: "rgba(0,212,170,0.06)", border: "0.5px solid rgba(0,212,170,0.15)",
            padding: "1px 7px", borderRadius: 3,
          }}>{step.skill}.{step.action}</span>
        </div>

        {/* Row 3 — sanitized result (done only) */}
        {cleanResult && (
          <div style={{
            fontSize: 11, color: "rgba(255,255,255,0.45)", fontFamily: "Space Mono, monospace",
            marginTop: 4, lineHeight: 1.5,
            borderTop: "0.5px solid rgba(255,255,255,0.05)", paddingTop: 8,
            wordBreak: "break-word",
          }}>{cleanResult}</div>
        )}

        {/* Row 4 — failure message */}
        {isFail && step.error && (
          <div style={{
            fontSize: 11, color: "rgba(239,68,68,0.8)", fontFamily: "Space Mono, monospace",
            marginTop: 6, borderTop: "0.5px solid rgba(239,68,68,0.1)", paddingTop: 6,
          }}>{sanitize(step.error) || "Step failed."}</div>
        )}
      </div>
    </div>
  );
}

// ─── Main ExecutionTimeline ───────────────────────────────────────────────
export default function ExecutionTimeline({
  planStatus,
  planSummary,
  steps,
  logs,
  commandError,
  loading,
  badgeLabel,
  badgeClass,
  onRetry,
  onCopy,
  lastResult,
}) {
  const [showTrace, setShowTrace] = useState(false);

  const isIdle      = planStatus === "idle" && !loading;
  const isCompleted = planStatus === "completed";
  const isFailed    = planStatus === "failed";
  const isRunning   = planStatus === "running" || loading;

  const doneCount  = steps.filter(s => s.status === "done").length;
  const totalCount = steps.length;
  const toolSet    = [...new Set(steps.map(s => s.skill).filter(Boolean))];

  return (
    <div style={{
      flex: 1, overflowY: "auto", padding: "20px 32px 28px",
      display: "flex", flexDirection: "column",
    }}>
      {/* ── Keyframes injected once ── */}
      <style>{`
        @keyframes tl-pulse { 0%,100%{box-shadow:0 0 12px rgba(245,158,11,0.3)} 50%{box-shadow:0 0 22px rgba(245,158,11,0.6)} }
        @keyframes badge-blink { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes tl-slide-in { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
        @keyframes tl-fade-in  { from{opacity:0} to{opacity:1} }
        .tl-area::-webkit-scrollbar{width:4px}
        .tl-area::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:2px}
      `}</style>

      {/* ── IDLE state ── */}
      {isIdle && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, paddingTop: "10vh" }}>
          <div style={{ fontSize: 36, opacity: 0.25, filter: "drop-shadow(0 0 16px rgba(255,255,255,0.3))" }}>✨</div>
          <div style={{ fontSize: 18, color: "#e8eaf0", fontWeight: 500 }}>How can I help you today?</div>
          <div style={{ fontSize: 12, color: "#6b7280", fontFamily: "Space Mono, monospace" }}>Type a request below to get started.</div>
        </div>
      )}

      {/* ── Active execution ── */}
      {!isIdle && (
        <div style={{ animation: "tl-slide-in 0.4s ease forwards" }}>

          {/* ── Execution header ── */}
          <div style={{
            display: "flex", alignItems: "flex-start", justifyContent: "space-between",
            marginBottom: 20, gap: 12, flexWrap: "wrap",
          }}>
            <div>
              <div style={{
                fontSize: 9, fontFamily: "Space Mono, monospace", color: "rgba(0,212,170,0.6)",
                letterSpacing: "2px", marginBottom: 6, textTransform: "uppercase",
              }}>
                {isRunning ? "BUILDING EXECUTION PLAN" : isCompleted ? "EXECUTION COMPLETE" : "EXECUTION STOPPED"}
              </div>
              <div style={{
                fontSize: 18, fontWeight: 600, color: "#e8eaf0",
                letterSpacing: "-0.3px", lineHeight: 1.3,
                maxWidth: 520,
              }}>
                {planSummary || (loading ? "Planning…" : "Processing")}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
              <span className={badgeClass} style={{ fontSize: 9 }}>{badgeLabel}</span>
              {totalCount > 0 && (
                <span style={{ fontSize: 9, fontFamily: "Space Mono, monospace", color: "#6b7280" }}>
                  {doneCount}/{totalCount} STEPS · {toolSet.length} TOOLS
                </span>
              )}
            </div>
          </div>

          {/* ── Timeline steps ── */}
          {steps.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", marginBottom: 16 }}>
              {steps.map((step, i) => (
                <StepCard key={step.id} step={step} index={i} totalSteps={steps.length} />
              ))}
            </div>
          )}

          {/* ── Loading skeleton (no steps yet) ── */}
          {isRunning && steps.length === 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[1,2,3].map(i => (
                <div key={i} style={{
                  height: 60, borderRadius: 10,
                  background: "rgba(255,255,255,0.025)",
                  border: "0.5px solid rgba(255,255,255,0.06)",
                  animation: `badge-blink ${0.8 + i * 0.2}s ease-in-out infinite`,
                }} />
              ))}
            </div>
          )}

          {/* ── Completion summary ── */}
          {isCompleted && (
            <div style={{
              background: "linear-gradient(135deg, rgba(16,185,129,0.07) 0%, rgba(10,12,15,0.9) 100%)",
              border: "0.5px solid rgba(16,185,129,0.2)",
              borderRadius: 12, padding: "16px 20px",
              marginTop: 8, animation: "tl-slide-in 0.5s ease forwards",
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
              boxShadow: "0 8px 32px rgba(16,185,129,0.06)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: "rgba(16,185,129,0.15)",
                  border: "1.5px solid #10b981",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, color: "#10b981",
                  boxShadow: "0 0 16px rgba(16,185,129,0.25)",
                }}>✓</div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e8eaf0", marginBottom: 2 }}>Workflow Complete</div>
                  <div style={{ fontSize: 11, color: "#6b7280", fontFamily: "Space Mono, monospace" }}>
                    {doneCount} step{doneCount !== 1 ? "s" : ""} executed successfully
                  </div>
                </div>
              </div>
              {lastResult && (
                <button onClick={() => onCopy && onCopy(lastResult)} style={{
                  background: "rgba(255,255,255,0.05)", border: "0.5px solid rgba(255,255,255,0.1)",
                  color: "#6b7280", borderRadius: 6, padding: "6px 12px", cursor: "pointer",
                  fontSize: 11, fontFamily: "Space Mono, monospace", transition: "all 0.2s",
                }}>📋 Copy</button>
              )}
            </div>
          )}

          {/* ── Failure summary ── */}
          {isFailed && (
            <div style={{
              background: "linear-gradient(135deg, rgba(239,68,68,0.07) 0%, rgba(10,12,15,0.9) 100%)",
              border: "0.5px solid rgba(239,68,68,0.2)",
              borderRadius: 12, padding: "16px 20px",
              marginTop: 8, animation: "tl-slide-in 0.5s ease forwards",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: commandError ? 10 : 0 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: "rgba(239,68,68,0.12)", border: "1.5px solid rgba(239,68,68,0.4)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, color: "#ef4444",
                }}>✗</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e8eaf0", marginBottom: 2 }}>Execution Stopped</div>
                  {commandError && (
                    <div style={{
                      fontSize: 11, color: "rgba(239,68,68,0.75)",
                      fontFamily: "Space Mono, monospace", lineHeight: 1.5,
                    }}>{sanitize(commandError) || commandError?.slice(0,120) || "An error occurred."}</div>
                  )}
                </div>
                <button onClick={onRetry} style={{
                  background: "rgba(239,68,68,0.08)", border: "0.5px solid rgba(239,68,68,0.25)",
                  color: "#ef4444", borderRadius: 6, padding: "6px 12px", cursor: "pointer",
                  fontSize: 11, fontFamily: "Space Mono, monospace", transition: "all 0.2s",
                  flexShrink: 0,
                }}>🔄 Retry</button>
              </div>
            </div>
          )}

          {/* ── Technical trace (collapsed by default) ── */}
          {(steps.length > 0 || logs.length > 0) && (
            <div style={{ marginTop: 20, borderTop: "0.5px solid rgba(255,255,255,0.05)", paddingTop: 14 }}>
              <button
                onClick={() => setShowTrace(v => !v)}
                style={{
                  background: "none", border: "none", color: "#4b5563", cursor: "pointer",
                  fontSize: 11, fontFamily: "Space Mono, monospace", display: "flex",
                  alignItems: "center", gap: 6, transition: "color 0.2s",
                  padding: 0,
                }}
              >
                <span style={{ transform: showTrace ? "rotate(90deg)" : "none", display: "inline-block", transition: "transform 0.2s" }}>▶</span>
                View Technical Trace
              </button>
              {showTrace && (
                <div style={{
                  marginTop: 12, padding: 12,
                  background: "rgba(0,0,0,0.5)", border: "0.5px solid rgba(255,255,255,0.06)",
                  borderRadius: 8, fontFamily: "Space Mono, monospace", fontSize: 10,
                  maxHeight: 280, overflowY: "auto", color: "#4b5563",
                }}>
                  {logs.map((log, i) => (
                    <div key={i} style={{ marginBottom: 3, display: "flex", gap: 8 }}>
                      <span style={{ color: "#374151", flexShrink: 0 }}>[{log.timestamp?.slice(11,19) || ""}]</span>
                      <span style={{ color: log.level === "ERROR" ? "#ef4444" : log.level === "WARN" ? "#f59e0b" : "#00d4aa", flexShrink: 0 }}>[{log.level}]</span>
                      <span>{log.message}</span>
                    </div>
                  ))}
                  {steps.map((s, i) => (
                    <div key={i} style={{ marginBottom: 3, display: "flex", gap: 8, opacity: 0.6 }}>
                      <span style={{ color: "#374151", flexShrink: 0 }}>[STEP]</span>
                      <span style={{ color: "#00d4aa", flexShrink: 0 }}>[{s.status?.toUpperCase()}]</span>
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
  );
}

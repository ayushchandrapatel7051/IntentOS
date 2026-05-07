/**
 * IntentOS — App.jsx
 * ==================
 * Frontend wired directly to the FastAPI backend defined in:
 *   dashboard/backend/routes.py
 *   dashboard/backend/ws_manager.py
 *   dashboard/backend/app.py
 *
 * API contracts inferred from source:
 *   POST /api/command        → CommandResponse { success, message, plan_summary, total_steps }
 *   GET  /api/status         → { agent_running, execution: { plan, current_step_index, is_paused, logs, ... } }
 *   POST /api/control        → { action: "pause"|"resume"|"skip"|"abort"|"override" }
 *   GET  /api/history        → { workflows: [...], stats: {...} }
 *   GET  /api/skills         → { skills: [...] }
 *   WS   /ws                 → { type, timestamp, stepId, status, result, error, ... }
 *
 * Voice: browser MediaRecorder → Blob. Wire to your Sarvam endpoint when ready.
 *        Look for the TODO comment: "WIRE SARVAM HERE"
 */

import { useState, useEffect, useRef, useCallback } from "react";
import ExecutionTimeline from "./components/ExecutionTimeline";
import { I, NavIcons, ControlIcons } from "./icons";
import {
  faCheck, faBolt, faListCheck, faPlugCircleBolt, faGear,
  faPause, faPlay, faForwardStep, faCircleStop, faArrowsRotate,
  faClipboard, faMicrophone, faArrowRight, faStar,
  faFile, faEnvelope, faCalendar, faMessage, faFolder,
} from "./icons";

// ─── Config ────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_URL   = import.meta.env.VITE_WS_URL   || "ws://localhost:8000/ws";
// Set VITE_SARVAM_ENDPOINT in .env when your voice route is ready
const SARVAM_ENDPOINT = import.meta.env.VITE_SARVAM_ENDPOINT || null;

// ─── Helpers ───────────────────────────────────────────────────────────────
const api = {
  post: (path, body) =>
    fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
  get: (path) =>
    fetch(`${API_BASE}${path}`).then((r) => r.json()),
};

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso.slice(11, 19) || "";
  }
}

function stepStatusClass(status) {
  switch (status) {
    case "running": return "dot-running";
    case "done":    return "dot-done";
    case "failed":  return "dot-failed";
    case "skipped": return "dot-skipped";
    default:        return "dot-pending";
  }
}

// ─── Styles ────────────────────────────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0a0c0f;
    --surface:   #111419;
    --surface2:  #161b22;
    --border:    rgba(255,255,255,0.07);
    --border2:   rgba(255,255,255,0.13);
    --text:      #e8eaf0;
    --muted:     #6b7280;
    --accent:    #00d4aa;
    --accent2:   #7c6fff;
    --warn:      #f59e0b;
    --danger:    #ef4444;
    --success:   #10b981;
    --mono:      'Space Mono', monospace;
    --ui:        'DM Sans', sans-serif;
  }

  body { background: var(--bg); color: var(--text); font-family: var(--ui); font-size: 14px; min-height: 100vh; overflow-x: hidden; }

  /* ── Shell ── */
  .shell { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

  /* ── Topbar ── */
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 9px 18px; background: var(--surface);
    border-bottom: 0.5px solid var(--border2); flex-shrink: 0; gap: 12px;
  }
  .topbar-left { display: flex; align-items: center; gap: 10px; }
  .os-logo { font-family: var(--mono); font-size: 13px; font-weight: 700; color: var(--accent); letter-spacing: 2.5px; }
  .os-ver  { font-size: 9px; font-family: var(--mono); background: rgba(0,212,170,.1); color: var(--accent); border: 0.5px solid rgba(0,212,170,.3); padding: 2px 7px; border-radius: 3px; letter-spacing: 1px; }
  .topbar-center { display: flex; align-items: center; gap: 7px; flex: 1; justify-content: center; }
  .pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse 2.2s ease-in-out infinite; }
  .pulse.off { background: var(--muted); animation: none; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.7)} }
  .topbar-status { font-size: 11px; font-family: var(--mono); color: var(--muted); }
  .topbar-right { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  .topbar-stat  { font-size: 10px; font-family: var(--mono); color: var(--muted); }
  .topbar-stat span { color: var(--accent); }

  /* ── Main layout ── */
  .layout { display: grid; grid-template-columns: 240px 1fr; flex: 1; min-height: 0; overflow: hidden; background: #050505; }

  /* ── Left panel ── */
  .left-panel { background: #0a0a0a; border-right: 0.5px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; overflow-y: auto; padding-bottom: 12px; }
  .sec-label { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1.5px; padding: 12px 14px 5px; text-transform: uppercase; }
  .nav-item  {
    display: flex; align-items: center; gap: 8px; padding: 7px 14px;
    font-size: 12px; color: var(--muted); cursor: pointer; border-left: 2px solid transparent;
    transition: all .15s; user-select: none;
  }
  .nav-item:hover  { background: rgba(255,255,255,.03); color: var(--text); }
  .nav-item.active { background: rgba(0,212,170,.06); color: var(--accent); border-left-color: var(--accent); }
  .nav-icon { width: 15px; height: 15px; border-radius: 3px; display: flex; align-items: center; justify-content: center; font-size: 10px; flex-shrink: 0; }
  .hist-item { flex-direction: column; align-items: flex-start; gap: 2px; }
  .hist-title { font-size: 11px; color: var(--text); }
  .hist-meta  { font-size: 9px; color: var(--muted); font-family: var(--mono); }
  .spacer { flex: 1; }
  .mem-chip { margin: 10px; background: rgba(255,255,255,0.02); border: 0.5px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; }
  .mem-label { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1px; margin-bottom: 7px; }
  .mem-row { margin-bottom: 6px; }
  .bar-wrap { background: rgba(255,255,255,.05); border-radius: 2px; height: 3px; margin-bottom: 3px; overflow: hidden; }
  .bar { height: 100%; border-radius: 2px; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .8s ease; }
  .bar-meta { display: flex; justify-content: space-between; font-size: 9px; font-family: var(--mono); color: var(--muted); }
  .bar-meta span:last-child { color: var(--accent); }

  /* ── Center panel ── */
  .center { display: flex; flex-direction: column; background: #050505; overflow: hidden; }
  .tab-bar { display: flex; padding: 0 16px; background: #0a0a0a; border-bottom: 0.5px solid rgba(255,255,255,0.06); flex-shrink: 0; }
  .tab { font-size: 10px; font-family: var(--mono); color: var(--muted); padding: 8px 12px; cursor: pointer; border-bottom: 1.5px solid transparent; transition: all .15s; letter-spacing: .5px; white-space: nowrap; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* ── Intent input ── */
  .intent-area { padding: 14px 16px; border-bottom: 0.5px solid rgba(255,255,255,0.06); flex-shrink: 0; background: #0a0a0a; }
  .field-label { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1.5px; margin-bottom: 7px; }
  .input-wrap {
    display: flex; align-items: center; gap: 10px;
    background: #111111; border: 0.5px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 9px 13px; transition: border-color .2s;
  }
  .input-wrap:focus-within { border-color: var(--accent); }
  .prompt-arrow { font-family: var(--mono); font-size: 13px; color: var(--accent); flex-shrink: 0; }
  .intent-input {
    flex: 1; background: transparent; border: none; outline: none;
    color: var(--text); font-family: var(--mono); font-size: 12px;
    caret-color: var(--accent);
  }
  .intent-input::placeholder { color: var(--muted); }
  .btn-run {
    background: var(--accent); color: #0a0c0f; border: none; border-radius: 5px;
    padding: 5px 14px; font-size: 11px; font-family: var(--mono); font-weight: 700;
    cursor: pointer; letter-spacing: 1px; transition: opacity .15s; flex-shrink: 0;
  }
  .btn-run:hover { opacity: .85; }
  .btn-run:disabled { opacity: .4; cursor: not-allowed; }
  .btn-voice {
    width: 28px; height: 28px; border-radius: 50%; background: rgba(14, 185, 128, 0.75);
    border: 0.5px solid var(--border2); cursor: pointer; display: flex;
    align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0;
    transition: all .15s;
  }
  .btn-voice:hover { border-color: rgba(0,212,170,.4); background: rgba(14, 185, 128, 0.5); }
  .btn-voice.recording { background: rgba(14, 185, 128, 0.35); rgba(14, 185, 128, 0.95); animation: pulse 1s ease-in-out infinite; }
  .pills { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
  .pill {
    font-size: 9px; font-family: var(--mono); color: var(--muted);
    border: 0.5px solid var(--border2); padding: 3px 9px; border-radius: 4px;
    cursor: pointer; transition: all .15s; user-select: none;
  }
  .pill:hover { color: var(--accent); border-color: rgba(0,212,170,.3); background: rgba(0,212,170,.05); }

  /* ── AI Execution Area ── */
  .exec-area { flex: 1; overflow-y: auto; display: flex; flex-direction: column; min-height: 0; }

  /* ── Loading spinner ── */
  .spinner { width: 12px; height: 12px; border: 1.5px solid rgba(255,255,255,.1); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Control bar ── */
  .ctrl-bar { display: flex; gap: 6px; padding: 10px 16px; border-top: 0.5px solid var(--border); flex-shrink: 0; background: var(--surface); }
  .btn-ctrl {
    font-size: 9px; font-family: var(--mono); color: var(--muted);
    background: transparent; border: 0.5px solid var(--border2); border-radius: 4px;
    padding: 4px 11px; cursor: pointer; transition: all .15s; letter-spacing: .5px;
  }
  .btn-ctrl:hover:not(:disabled) { color: var(--text); border-color: rgba(255,255,255,.22); }
  .btn-ctrl:disabled { opacity: .3; cursor: not-allowed; }
  .btn-ctrl.danger:hover:not(:disabled) { color: var(--danger); border-color: rgba(239,68,68,.4); }

  /* ── Right panel ── */
  .right-panel { background: var(--surface); border-left: 0.5px solid var(--border); display: flex; flex-direction: column; overflow-y: auto; }
  .rp-sec { padding: 12px 14px; border-bottom: 0.5px solid var(--border); }
  .rp-title { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1.5px; margin-bottom: 10px; text-transform: uppercase; }

  /* ── Log items ── */
  .log-item { display: flex; align-items: flex-start; gap: 7px; padding: 4px 0; border-bottom: 0.5px solid var(--border); }
  .log-item:last-child { border-bottom: none; }
  .log-time { font-size: 9px; font-family: var(--mono); color: var(--muted); flex-shrink: 0; padding-top: 1px; }
  .log-msg  { font-size: 10px; color: var(--muted); line-height: 1.4; word-break: break-word; flex: 1; }
  .log-tag  { font-size: 8px; font-family: var(--mono); padding: 1px 5px; border-radius: 2px; flex-shrink: 0; margin-top: 1px; }
  .tag-info  { background: rgba(0,212,170,.08); color: var(--accent); }
  .tag-warn  { background: rgba(245,158,11,.1);  color: var(--warn); }
  .tag-error { background: rgba(239,68,68,.1);   color: var(--danger); }

  /* ── Skills list ── */
  .skill-badge { font-size: 9px; font-family: var(--mono); color: var(--accent2); background: rgba(124,111,255,.1); border: 0.5px solid rgba(124,111,255,.2); padding: 2px 7px; border-radius: 3px; display: inline-block; margin: 2px; }

  /* ── Connection indicator ── */
  .conn-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 5px; }
  .conn-ok  { background: var(--success); }
  .conn-err { background: var(--danger); }
  .conn-off { background: var(--muted); }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,.08); border-radius: 2px; }

  /* ── Tabs content ── */
  .tab-content { flex: 1; overflow-y: auto; padding: 14px 16px; }

  /* ── History ── */
  .hist-card { background: var(--surface); border: 0.5px solid var(--border); border-radius: 6px; padding: 9px 11px; margin-bottom: 7px; }
  .hist-card-title { font-size: 11px; color: var(--text); margin-bottom: 3px; word-break: break-word; }
  .hist-card-meta  { font-size: 9px; color: var(--muted); font-family: var(--mono); display: flex; gap: 10px; flex-wrap: wrap; }
  .hist-status-done    { color: var(--success); }
  .hist-status-failed  { color: var(--danger); }
  .hist-status-aborted { color: var(--muted); }

  /* ── Toasts ── */
  .toast-container {
    position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column-reverse; gap: 12px; z-index: 9999; pointer-events: none;
  }
  .toast {
    pointer-events: auto;
    background: rgba(15, 15, 15, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px;
    padding: 16px 20px; width: 340px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    animation: toast-slide-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    position: relative; overflow: hidden;
  }
  .toast.closing {
    animation: toast-fade-out 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  @keyframes toast-slide-in {
    from { opacity: 0; transform: translateX(50px) scale(0.95); }
    to { opacity: 1; transform: translateX(0) scale(1); }
  }
  @keyframes toast-fade-out {
    to { opacity: 0; transform: scale(0.95); margin-top: -100px; }
  }
  .toast-header { display: flex; align-items: center; gap: 14px; margin-bottom: 8px; }
  .toast-icon { font-size: 24px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; background: rgba(255,255,255,0.05); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
  .toast-body { display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
  .toast-title { font-size: 14px; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .toast-subtitle { font-size: 12px; color: var(--success); font-family: var(--ui); display: flex; align-items: center; gap: 4px; }
  .toast-path { font-size: 10px; color: var(--muted); font-family: var(--mono); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
  .toast-actions { display: flex; gap: 8px; margin-top: 14px; }
  .toast-btn {
    background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
    cursor: pointer; transition: all 0.2s; flex: 1; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px;
  }
  .toast-btn:hover { background: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.2); transform: translateY(-1px); }
  .toast-close { position: absolute; top: 12px; right: 12px; background: transparent; border: none; color: var(--muted); cursor: pointer; font-size: 16px; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 4px; transition: all 0.2s; }
  .toast-close:hover { color: var(--text); background: rgba(255,255,255,0.1); }
  .toast-progress { position: absolute; bottom: 0; left: 0; height: 3px; background: var(--success); animation: toast-timer linear forwards; border-top-right-radius: 3px; border-bottom-right-radius: 3px; }
  @keyframes toast-timer { from { width: 100%; } to { width: 0%; } }

  /* ── Inline Confirmation Card ── */
  .confirm-inline {
    margin: 6px 0 10px 48px;
    background: linear-gradient(135deg, rgba(245,158,11,0.08) 0%, rgba(14,17,21,0.95) 100%);
    border: 1px solid rgba(245,158,11,0.28);
    border-radius: 10px;
    padding: 14px 16px;
    animation: confirm-slide-in 0.28s cubic-bezier(0.16,1,0.3,1);
  }
  @keyframes confirm-slide-in {
    from { opacity:0; transform:translateY(-6px); }
    to   { opacity:1; transform:translateY(0); }
  }
  .confirm-inline-header {
    display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  }
  .confirm-inline-icon { font-size: 15px; flex-shrink: 0; }
  .confirm-inline-label {
    font-size: 9px; font-family: var(--mono); color: var(--warn);
    letter-spacing: 1.5px; text-transform: uppercase; font-weight: 700;
  }
  .confirm-inline-msg {
    font-size: 12px; color: var(--text); line-height: 1.55;
    background: rgba(255,255,255,0.03); border: 0.5px solid rgba(255,255,255,0.06);
    border-radius: 6px; padding: 9px 12px; margin-bottom: 12px;
    font-family: var(--ui);
  }
  .confirm-inline-action {
    font-size: 9px; font-family: var(--mono); color: rgba(245,158,11,0.55);
    letter-spacing: 1px; margin-bottom: 10px;
  }
  .confirm-inline-btns { display: flex; gap: 8px; }
  .confirm-inline-btn {
    flex: 1; padding: 8px 0; border-radius: 7px; font-size: 12px; font-weight: 600;
    cursor: pointer; border: none; transition: all 0.18s; font-family: var(--ui);
    letter-spacing: 0.2px;
  }
  .confirm-inline-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .confirm-inline-yes { background: rgba(245,158,11,0.18); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
  .confirm-inline-yes:hover:not(:disabled) { background: rgba(245,158,11,0.28); border-color: rgba(245,158,11,0.5); transform: translateY(-1px); }
  .confirm-inline-no  { background: rgba(255,255,255,0.04); color: var(--muted); border: 0.5px solid rgba(255,255,255,0.1); }
  .confirm-inline-no:hover:not(:disabled)  { background: rgba(239,68,68,0.08); color: var(--danger); border-color: rgba(239,68,68,0.25); }
`;


function Toast({ toast, onRemove, onDirectCommand }) {

  const [isHovered, setIsHovered] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  useEffect(() => {
    if (isHovered) return;
    const timer = setTimeout(() => { close(); }, 6000);
    return () => clearTimeout(timer);
  }, [isHovered]);

  const close = () => {
    setIsClosing(true);
    setTimeout(() => onRemove(toast.id), 400);
  };

  const openFile = () => {
    if (!toast.path) return;
    // Invoke-Item opens the file in its default application with the exact path
    onDirectCommand(`Invoke-Item "${toast.path}"`);
  };

  const showInFolder = () => {
    if (!toast.path) return;
    // explorer.exe /select highlights the file in its parent folder
    onDirectCommand(`explorer.exe /select,"${toast.path}"`);
  };

  const getIcon = (filename) => {
    if (!filename) return "📄";
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
      txt: "📝", pdf: "📕", png: "🖼️", jpg: "🖼️", jpeg: "🖼️", gif: "🖼️",
      json: "👨‍💻", js: "👨‍💻", py: "👨‍💻", html: "🌐", css: "🎨", csv: "📊",
      xlsx: "📊", docx: "📘", md: "📝"
    };
    return icons[ext] || "📄";
  };

  return (
    <div className={`toast ${isClosing ? 'closing' : ''}`} onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
      <button className="toast-close" onClick={close}>×</button>
      <div className="toast-header">
        <div className="toast-icon">{getIcon(toast.filename)}</div>
        <div className="toast-body">
          <div className="toast-title" title={toast.filename}>{toast.filename || "File"}</div>
          <div className="toast-subtitle"><span className="check-icon" style={{fontSize: 10}}>✓</span> {toast.message || "Saved successfully"}</div>
        </div>
      </div>
      {toast.path && <div className="toast-path" title={toast.path}>&lrm;{toast.path}&lrm;</div>}
      <div className="toast-actions">
        <button className="toast-btn" onClick={openFile}><span>📂</span> Open</button>
        <button className="toast-btn" onClick={showInFolder}><span>📁</span> Show Folder</button>
      </div>
      {!isHovered && <div className="toast-progress" style={{ animationDuration: '6s' }} />}
    </div>
  );
}

// ─── Component ─────────────────────────────────────────────────────────────
export default function App() {
  // ── State ──
  const [commandInput, setCommandInput] = useState("");
  const [loading, setLoading]           = useState(false);
  const [activeTab, setActiveTab]       = useState("execution");
  const [wsConnected, setWsConnected]   = useState(false);

  // Confirmation queue — populated when executor emits confirm_required events
  const [confirmQueue, setConfirmQueue] = useState([]);  // [{stepId, action, message, params}]

  const removeConfirm = useCallback((stepId) => {
    setConfirmQueue(prev => prev.filter(c => c.stepId !== stepId));
  }, []);

  // Execution state — populated from WS events + /api/status polling
  const [planSummary,   setPlanSummary]   = useState(null);   // string | null
  const [planStatus,    setPlanStatus]    = useState("idle"); // idle|running|completed|failed|aborted
  const [steps,         setSteps]         = useState([]);     // Step[]  from plan.steps
  const [currentIdx,    setCurrentIdx]    = useState(-1);     // current_step_index
  const [logs,          setLogs]          = useState([]);     // {timestamp,level,message,step_id}[]
  const [commandError,  setCommandError]  = useState(null);

  // History & skills (side data)
  const [history, setHistory] = useState([]);
  const [skills,  setSkills]  = useState([]);

  // Toasts
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const checkAndTriggerToast = useCallback((skill, action, result) => {
    if (!result || typeof result !== 'string') return;

    let fullPath = null;

    // Priority 1: IntentOS backend write_file format: "Written {path} (XX chars)"
    const writeMatch = result.match(/(?:Written|Appended to) (.+?) \(\d+ chars\)/i);
    if (writeMatch) {
      fullPath = writeMatch[1].trim();
    }

    // Priority 2: Explicit file skill
    if (!fullPath && skill === 'files' && ['write_file', 'download', 'export', 'save'].includes(action)) {
      // Try absolute Windows path
      const winPath = result.match(/([A-Za-z]:\\[^\n"'<>|*?]+)/); 
      if (winPath) fullPath = winPath[1].trim().replace(/[.,;]+$/, '');
      if (!fullPath) {
        // Try any filename.ext in the result
        const extMatch = result.match(/([\w\-. ]+\.(?:txt|pdf|png|jpg|jpeg|md|json|js|py|csv|xlsx|docx|html|yaml))/i);
        if (extMatch) fullPath = extMatch[1].trim();
      }
    }

    // Priority 3: Broad fallback — any result mentioning a saved filename
    if (!fullPath) {
      const extMatch = result.match(/([\w\-. ]+\.(?:txt|pdf|png|jpg|jpeg|md|json|js|py|csv|xlsx|docx|html|yaml))/i);
      if (extMatch && (result.toLowerCase().includes('written') || result.toLowerCase().includes('saved') || result.toLowerCase().includes('created'))) {
        fullPath = extMatch[1].trim();
      }
    }

    if (fullPath) {
      fullPath = fullPath.replace(/[.,;:]+$/, '').trim();
      const filename = fullPath.split(/[\\/]/).pop();
      if (filename && filename.includes('.') && filename.length < 200) {
        const id = Date.now() + Math.random();
        setToasts(prev => [...prev, { id, path: fullPath, filename, message: "Saved successfully" }]);
      }
    }
  }, []);

  // Voice recording
  const [recording, setRecording]     = useState(false);
  const mediaRecorderRef              = useRef(null);
  const audioChunksRef                = useRef([]);

  // WS ref
  const wsRef       = useRef(null);
  const reconnectRef = useRef(null);

  // Uptime
  const [uptime, setUptime] = useState("0s");
  const startRef = useRef(Date.now());
  useEffect(() => {
    const t = setInterval(() => {
      const s = Math.floor((Date.now() - startRef.current) / 1000);
      if (s < 60) setUptime(`${s}s`);
      else if (s < 3600) setUptime(`${Math.floor(s/60)}m ${s%60}s`);
      else setUptime(`${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // ── Load side data once ──
  useEffect(() => {
    api.get("/api/history?limit=10")
       .then((d) => { if (d.workflows) setHistory(d.workflows); })
       .catch(() => {});
    api.get("/api/skills")
       .then((d) => { if (d.skills) setSkills(d.skills); })
       .catch(() => {});
  }, []);

  // ── WebSocket ──
  const applyWsEvent = useCallback((event) => {
    const { type } = event;

    if (type === "plan_started") {
      setPlanStatus("running");
      setPlanSummary(event.summary || event.intent || null);
      setSteps([]);
      setCurrentIdx(-1);
      setLogs([]);
      setCommandError(null);
    }

    if (type === "step_started") {
      setSteps((prev) => {
        const updated = prev.map((s) =>
          s.id === event.stepId ? { ...s, status: "running", started_at: event.timestamp } : s
        );
        // If step not yet in list (WS faster than status poll), append placeholder
        if (!updated.find((s) => s.id === event.stepId)) {
          updated.push({
            id: event.stepId,
            skill: event.skill || "",
            action: event.action || "",
            description: event.description || event.stepId,
            reasoning: event.reasoning || "",
            status: "running",
            started_at: event.timestamp,
            result: null,
            error: null,
          });
        }
        return updated;
      });
    }

    if (type === "step_completed") {
      // Use skill/action from the WS event directly — more reliable than stepsRef lookup
      checkAndTriggerToast(
        event.skill || '',
        event.action || '',
        event.result || ''
      );
      setSteps((prev) =>
        prev.map((s) =>
          s.id === event.stepId
            ? { ...s, status: "done", result: event.result, completed_at: event.timestamp }
            : s
        )
      );
    }

    if (type === "step_failed") {
      setSteps((prev) =>
        prev.map((s) =>
          s.id === event.stepId
            ? { ...s, status: "failed", error: event.error, completed_at: event.timestamp }
            : s
        )
      );
    }

    if (type === "plan_completed") {
      setPlanStatus(event.status || "completed");
      setLoading(false);
    }

    if (type === "plan_replanned") {
      // Recovery inserted new steps — re-fetch status to sync
      api.get("/api/status").then(syncFromStatus).catch(() => {});
    }

    if (type === "confirm_required") {
      // Execution is paused — show modal to user
      setConfirmQueue(prev => {
        // Avoid duplicates if WS fires twice
        if (prev.find(c => c.stepId === event.stepId)) return prev;
        return [...prev, {
          stepId:  event.stepId,
          action:  event.action,
          message: event.message,
          params:  event.params || {},
        }];
      });
    }
  }, []);

  const syncFromStatus = useCallback((data) => {
    if (!data) return;
    if (data.execution) {
      const ex = data.execution;
      setPlanStatus(ex.plan?.status || "idle");
      setPlanSummary(ex.plan?.summary || ex.plan?.intent || null);
      setCurrentIdx(ex.current_step_index ?? -1);
      if (ex.plan?.steps) setSteps(ex.plan.steps);
      if (ex.logs) setLogs(ex.logs);
    } else {
      if (!data.agent_running) setPlanStatus("idle");
    }
  }, []);

  const connectWS = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < 2) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      clearTimeout(reconnectRef.current);
      // Sync state from REST on connect
      api.get("/api/status").then(syncFromStatus).catch(() => {});
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        applyWsEvent(event);
      } catch {}
    };

    ws.onclose = () => {
      setWsConnected(false);
      reconnectRef.current = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => ws.close();
  }, [applyWsEvent, syncFromStatus]);

  useEffect(() => {
    connectWS();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connectWS]);

  // Poll /api/status when WS is disconnected as fallback
  useEffect(() => {
    if (wsConnected) return;
    const t = setInterval(() => {
      api.get("/api/status").then(syncFromStatus).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [wsConnected, syncFromStatus]);

  // ── Submit command ──
  const submitCommand = async (text) => {
    const cmd = (text || commandInput).trim();
    if (!cmd) return;
    setLoading(true);
    setCommandError(null);
    setPlanStatus("running");
    setPlanSummary(null);
    setSteps([]);
    setLogs([]);

    try {
      const res = await api.post("/api/command", { command: cmd, voice: false });
      // res: { success, message, plan_summary, total_steps }
      if (res.success) {
        setPlanSummary(res.plan_summary || res.message || cmd);
        // If WS is live, step updates will arrive automatically.
        // If not, poll status.
        if (!wsConnected) {
          const poll = setInterval(async () => {
            const status = await api.get("/api/status").catch(() => null);
            if (status) {
              syncFromStatus(status);
              if (status.execution?.plan?.status &&
                  ["completed", "failed", "aborted"].includes(status.execution.plan.status)) {
                clearInterval(poll);
                setLoading(false);
              }
            }
          }, 800);
        }
      } else {
        setCommandError(res.detail || res.message || "Command failed");
        setPlanStatus("failed");
        setLoading(false);
      }
    } catch (err) {
      setCommandError(`Connection error: ${err.message}`);
      setPlanStatus("failed");
      setLoading(false);
    }
  };

  // ── Control actions ──
  const control = async (action, extra = {}) => {
    try {
      await api.post("/api/control", { action, ...extra });
      if (action === "abort") { setPlanStatus("aborted"); setLoading(false); }
      if (action === "pause")  setPlanStatus("paused");
      if (action === "resume") setPlanStatus("running");
    } catch (e) {
      console.error("Control error:", e);
    }
  };

  // ── Voice recording ──
  // The backend's SarvamSTTClient lives server-side and is triggered by `voice: true` in
  // the command request, but requires the audio to already be transcribed on the backend.
  // Since no /voice REST route is exposed in routes.py, we implement two paths:
  //   1. If VITE_SARVAM_ENDPOINT is set → POST raw WAV blob to that endpoint → get transcript → submit
  //   2. Otherwise → use browser Web Speech API if available
  const startVoice = async () => {
    // Path 2: browser Web Speech API (no Sarvam endpoint configured)
    if (!SARVAM_ENDPOINT && "SpeechRecognition" in window || "webkitSpeechRecognition" in window) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      const rec = new SR();
      rec.lang = "en-IN";
      rec.interimResults = false;
      rec.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        setCommandInput(transcript);
        submitCommand(transcript);
      };
      rec.start();
      setRecording(true);
      rec.onend = () => setRecording(false);
      return;
    }

    // Path 1: MediaRecorder → Sarvam (or raw WAV if no endpoint)
    if (!navigator.mediaDevices) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
    if (!stream) return;

    const mr = new MediaRecorder(stream);
    audioChunksRef.current = [];
    mr.ondataavailable = (e) => audioChunksRef.current.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(audioChunksRef.current, { type: "audio/wav" });
      setRecording(false);

      if (SARVAM_ENDPOINT) {
        // TODO: WIRE SARVAM HERE
        // Replace the fetch below with the correct Sarvam multipart/base64 format
        // per SarvamSTTClient.transcribe() in voice.py
        try {
          const fd = new FormData();
          fd.append("audio", blob, "voice.wav");
          fd.append("model", "saaras:v3");
          fd.append("language", "auto");
          const r = await fetch(SARVAM_ENDPOINT, {
            method: "POST",
            headers: { "api-subscription-key": import.meta.env.VITE_SARVAM_API_KEY || "" },
            body: fd,
          });
          const d = await r.json();
          const transcript = d.transcript || "";
          if (transcript) { setCommandInput(transcript); submitCommand(transcript); }
        } catch (e) {
          setCommandError("Voice transcription failed: " + e.message);
        }
      }
    };

    mediaRecorderRef.current = mr;
    mr.start();
    setRecording(true);
  };

  const stopVoice = () => {
    if (!mediaRecorderRef.current) return;

    // delay stop by 3 seconds
    setTimeout(() => {
      mediaRecorderRef.current?.stop();
    }, 3000);
  };

  // ── Derived ──
  const isRunning = planStatus === "running";
  const isPaused  = planStatus === "paused";
  const isDone    = ["completed", "failed", "aborted"].includes(planStatus);

  const badgeClass = {
    running:   "status-badge badge-running",
    paused:    "status-badge badge-running",
    completed: "status-badge badge-done",
    failed:    "status-badge badge-failed",
    aborted:   "status-badge badge-aborted",
    idle:      "status-badge badge-idle",
  }[planStatus] || "status-badge badge-idle";

  const badgeLabel = {
    running:   "● RUNNING",
    paused:    "⏸ PAUSED",
    completed: "✓ DONE",
    failed:    "✗ FAILED",
    aborted:   "✗ ABORTED",
    idle:      "IDLE",
  }[planStatus] || "IDLE";

  // Last completed step result for output card
  const lastResult = [...steps].reverse().find((s) => s.status === "done" && s.result)?.result;
  const planFailed = planStatus === "failed";

  // ── Render ──
  return (
    <>
      <style>{CSS}</style>
      <div className="shell">
        {/* ── Topbar ── */}
        <div className="topbar">
          <div className="topbar-left">
            <span className="os-logo">INTENTOS</span>
            <span className="os-ver">v0.1 ALPHA</span>
          </div>
          <div className="topbar-center">
            <div className={`pulse ${wsConnected ? "" : "off"}`} />
            <span className="topbar-status">
              {wsConnected
                ? "GEMINI CONNECTED · WS LIVE"
                : "CONNECTING TO BACKEND..."}
            </span>
          </div>
          <div className="topbar-right">
            <span className="topbar-stat">INTENTS <span>{history.length}</span></span>
            <span className="topbar-stat">UPTIME <span>{uptime}</span></span>
          </div>
        </div>

        {/* ── Layout ── */}
        <div className="layout">
          {/* ── Left Panel ── */}
          <div className="left-panel">
            <div className="sec-label">Navigation</div>
            <div
              className={`nav-item ${activeTab === "execution" ? "active" : ""}`}
              onClick={() => setActiveTab("execution")}
            >
              <div className="nav-icon" style={{ background: "rgba(0,212,170,.1)", color: "var(--accent)" }}>
                <I icon={faBolt} color="var(--accent)" size="xs" />
              </div>
              Intent Runner
            </div>
            <div
              className={`nav-item ${activeTab === "history" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("history");
                api.get("/api/history?limit=20").then((d) => { if (d.workflows) setHistory(d.workflows); }).catch(() => {});
              }}
            >
              <div className="nav-icon" style={{ background: "rgba(245,158,11,.1)", color: "var(--warn)" }}>
                <I icon={faListCheck} color="var(--warn)" size="xs" />
              </div>
              Audit Log
            </div>
            <div
              className={`nav-item ${activeTab === "skills" ? "active" : ""}`}
              onClick={() => setActiveTab("skills")}
            >
              <div className="nav-icon" style={{ background: "rgba(124,111,255,.1)", color: "var(--accent2)" }}>
                <I icon={faPlugCircleBolt} color="var(--accent2)" size="xs" />
              </div>
              Skills
            </div>

            {history.length > 0 && (
              <>
                <div className="sec-label" style={{ marginTop: 8 }}>Recent Intents</div>
                {history.slice(0, 5).map((wf, i) => (
                  <div
                    key={i}
                    className="nav-item hist-item"
                    onClick={() => setCommandInput(wf.intent || wf.command || "")}
                    title={wf.intent || wf.command || ""}
                  >
                    <div className="hist-title" style={{ width: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {wf.intent || wf.command || "—"}
                    </div>
                    <div className="hist-meta">
                      <span className={
                        wf.status === "completed" ? "hist-status-done" :
                        wf.status === "failed"    ? "hist-status-failed" : "hist-status-aborted"
                      }>
                        {wf.status === "completed" ? "✓" : wf.status === "failed" ? "✗" : "○"}
                        {" "}{wf.status}
                      </span>
                    </div>
                  </div>
                ))}
              </>
            )}

            <div className="spacer" />

            {/* Memory store chip — sizes from /api/status if available */}
            <div className="mem-chip">
              <div className="mem-label">SYSTEM</div>
              <div className="mem-row">
                <div className="bar-wrap"><div className="bar" style={{ width: wsConnected ? "100%" : "0%" }} /></div>
                <div className="bar-meta"><span>WS</span><span>{wsConnected ? "live" : "off"}</span></div>
              </div>
              <div className="mem-row">
                <div className="bar-wrap"><div className="bar" style={{ width: steps.length > 0 ? `${Math.min(100, steps.filter(s=>s.status==="done").length / Math.max(1,steps.length) * 100)}%` : "0%" }} /></div>
                <div className="bar-meta"><span>Progress</span><span>{steps.length > 0 ? `${steps.filter(s=>s.status==="done").length}/${steps.length}` : "—"}</span></div>
              </div>
            </div>
          </div>

          {/* ── Center Panel ── */}
          <div className="center">
            {/* Tab bar */}
            <div className="tab-bar">
              {["execution", "history", "skills"].map((t) => (
                <div
                  key={t}
                  className={`tab ${activeTab === t ? "active" : ""}`}
                  onClick={() => setActiveTab(t)}
                >
                  {t.toUpperCase()}
                </div>
              ))}
            </div>

            {/* Intent input — always visible */}
            <div className="intent-area">
              <div className="field-label">INTENT INPUT</div>
              <div className="input-wrap">
                <span className="prompt-arrow">→</span>
                <input
                  className="intent-input"
                  placeholder="Describe what you want to do..."
                  value={commandInput}
                  onChange={(e) => setCommandInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !loading && submitCommand()}
                  disabled={loading}
                />
                {loading && <div className="spinner" />}
                <button
                  className={`btn-voice ${recording ? "recording" : ""}`}
                  title="Voice input"
                  onClick={recording ? stopVoice : startVoice}
                >
                  <I icon={faMicrophone} color={recording ? "#10b981" : "#e8eaf0"} size="sm" />
                </button>
                <button
                  className="btn-run"
                  onClick={() => submitCommand()}
                  disabled={loading || !commandInput.trim()}
                >
                  RUN
                </button>
              </div>
              <div className="pills">
                {[
                  "Send daily standup to Slack",
                  "Search YouTube for lofi music",
                  "Create a Google Meet for tomorrow 3pm",
                  "Summarise my unread emails",
                ].map((p) => (
                  <div key={p} className="pill" onClick={() => { setCommandInput(p); submitCommand(p); }}>
                    {p}
                  </div>
                ))}
              </div>
            </div>

            {/* Tab content */}
            {activeTab === "execution" && (
              <>
                <div className="exec-area">
                  <ExecutionTimeline
                    planStatus={planStatus}
                    planSummary={planSummary}
                    steps={steps}
                    logs={logs}
                    commandError={commandError}
                    loading={loading}
                    badgeLabel={badgeLabel}
                    badgeClass={badgeClass}
                    lastResult={lastResult}
                    onRetry={() => submitCommand(commandInput)}
                    onCopy={(text) => navigator.clipboard.writeText(text)}
                    confirmQueue={confirmQueue}
                    onConfirmRespond={removeConfirm}
                  />
                </div>
                <div className="ctrl-bar">
                  <button className="btn-ctrl" disabled={!isRunning} onClick={() => control("pause")}>
                    <I icon={faPause} size="xs" /> Pause
                  </button>
                  <button className="btn-ctrl" disabled={!isPaused} onClick={() => control("resume")}>
                    <I icon={faPlay} size="xs" /> Resume
                  </button>
                  <button className="btn-ctrl" disabled={!isRunning && !isPaused} onClick={() => control("skip")}>
                    <I icon={faForwardStep} size="xs" /> Skip
                  </button>
                  <button className="btn-ctrl danger" disabled={!isRunning && !isPaused} onClick={() => control("abort")}>
                    <I icon={faCircleStop} size="xs" /> Abort
                  </button>
                </div>
              </>
            )}

            {activeTab === "history" && (
              <div className="tab-content">
                {history.length === 0
                  ? <div className="empty-state"><div className="empty-icon">📋</div><div className="empty-text">No past workflows yet</div></div>
                  : history.map((wf, i) => (
                    <div className="hist-card" key={i} onClick={() => { setCommandInput(wf.intent || wf.command || ""); setActiveTab("execution"); }}>
                      <div className="hist-card-title">{wf.intent || wf.command || "—"}</div>
                      <div className="hist-card-meta">
                        <span className={`hist-status-${wf.status || "idle"}`}>{wf.status}</span>
                        {wf.created_at && <span>{fmtTime(wf.created_at)}</span>}
                        {wf.execution_time && <span>{wf.execution_time.toFixed(1)}s</span>}
                      </div>
                    </div>
                  ))
                }
              </div>
            )}

            {activeTab === "skills" && (
              <div className="tab-content">
                <div className="rp-title" style={{ marginBottom: 12 }}>AVAILABLE SKILLS</div>
                {skills.length === 0
                  ? <div className="empty-state"><div className="empty-icon">🔌</div><div className="empty-text">No skills loaded yet</div></div>
                  : <div>{skills.map((s) => <span key={s} className="skill-badge">{s}</span>)}</div>
                }
              </div>
            )}
          </div>
        </div>
        <div className="toast-container">
          {toasts.map(t => (
            <Toast
              key={t.id}
              toast={t}
              onRemove={removeToast}
              onDirectCommand={(cmd) => api.post('/api/command', { command: cmd, voice: false })}
            />
          ))}
        </div>
      </div>
    </>
  );
}

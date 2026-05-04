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
  .layout { display: grid; grid-template-columns: 210px 1fr 255px; flex: 1; min-height: 0; overflow: hidden; }

  /* ── Left panel ── */
  .left-panel { background: var(--surface); border-right: 0.5px solid var(--border); display: flex; flex-direction: column; overflow-y: auto; padding-bottom: 12px; }
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
  .mem-chip { margin: 10px; background: var(--surface2); border: 0.5px solid var(--border); border-radius: 8px; padding: 10px; }
  .mem-label { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1px; margin-bottom: 7px; }
  .mem-row { margin-bottom: 6px; }
  .bar-wrap { background: rgba(255,255,255,.05); border-radius: 2px; height: 3px; margin-bottom: 3px; overflow: hidden; }
  .bar { height: 100%; border-radius: 2px; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .8s ease; }
  .bar-meta { display: flex; justify-content: space-between; font-size: 9px; font-family: var(--mono); color: var(--muted); }
  .bar-meta span:last-child { color: var(--accent); }

  /* ── Center panel ── */
  .center { display: flex; flex-direction: column; background: var(--bg); overflow: hidden; }
  .tab-bar { display: flex; padding: 0 16px; background: var(--surface); border-bottom: 0.5px solid var(--border); flex-shrink: 0; }
  .tab { font-size: 10px; font-family: var(--mono); color: var(--muted); padding: 8px 12px; cursor: pointer; border-bottom: 1.5px solid transparent; transition: all .15s; letter-spacing: .5px; white-space: nowrap; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* ── Intent input ── */
  .intent-area { padding: 14px 16px; border-bottom: 0.5px solid var(--border); flex-shrink: 0; }
  .field-label { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1.5px; margin-bottom: 7px; }
  .input-wrap {
    display: flex; align-items: center; gap: 10px;
    background: var(--surface); border: 0.5px solid var(--border2);
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
    width: 28px; height: 28px; border-radius: 50%; background: var(--surface2);
    border: 0.5px solid var(--border2); cursor: pointer; display: flex;
    align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0;
    transition: all .15s;
  }
  .btn-voice:hover { border-color: rgba(0,212,170,.4); background: rgba(0,212,170,.08); }
  .btn-voice.recording { background: rgba(239,68,68,.15); border-color: var(--danger); animation: pulse 1s ease-in-out infinite; }
  .pills { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
  .pill {
    font-size: 9px; font-family: var(--mono); color: var(--muted);
    border: 0.5px solid var(--border2); padding: 3px 9px; border-radius: 4px;
    cursor: pointer; transition: all .15s; user-select: none;
  }
  .pill:hover { color: var(--accent); border-color: rgba(0,212,170,.3); background: rgba(0,212,170,.05); }

  /* ── Execution area ── */
  .exec-area { flex: 1; overflow-y: auto; padding: 14px 16px; }
  .exec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .exec-title { font-size: 9px; font-family: var(--mono); color: var(--muted); letter-spacing: 1.5px; }
  .status-badge {
    font-size: 9px; font-family: var(--mono); padding: 2px 8px; border-radius: 3px;
  }
  .badge-running { background: rgba(245,158,11,.1); color: var(--warn); border: 0.5px solid rgba(245,158,11,.3); }
  .badge-done    { background: rgba(16,185,129,.1); color: var(--success); border: 0.5px solid rgba(16,185,129,.3); }
  .badge-failed  { background: rgba(239,68,68,.1); color: var(--danger); border: 0.5px solid rgba(239,68,68,.3); }
  .badge-aborted { background: rgba(107,114,128,.1); color: var(--muted); border: 0.5px solid rgba(107,114,128,.3); }
  .badge-idle    { background: rgba(255,255,255,.04); color: var(--muted); border: 0.5px solid var(--border); }

  /* ── Intent summary card ── */
  .intent-card { background: var(--surface); border: 0.5px solid var(--border2); border-radius: 8px; padding: 11px 13px; margin-bottom: 12px; }
  .ic-header { display: flex; align-items: flex-start; gap: 9px; }
  .ic-icon { width: 26px; height: 26px; border-radius: 5px; background: rgba(0,212,170,.1); border: 0.5px solid rgba(0,212,170,.2); display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
  .ic-title { font-size: 13px; font-weight: 500; color: var(--text); line-height: 1.4; word-break: break-word; }
  .ic-meta  { font-size: 9px; color: var(--muted); font-family: var(--mono); margin-top: 3px; }

  /* ── Step chain ── */
  .step-chain { display: flex; flex-direction: column; }
  .step-row { display: flex; align-items: flex-start; gap: 10px; animation: step-in .35s ease forwards; opacity: 0; }
  @keyframes step-in { to { opacity:1; transform: translateY(0); } from { opacity:0; transform: translateY(5px); } }
  .step-left { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; padding-top: 4px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; position: relative; border: 1.5px solid; }
  .dot-pending { border-color: rgba(255,255,255,.18); background: transparent; }
  .dot-running { border-color: var(--warn); background: transparent; }
  .dot-running::after { content:''; position:absolute; inset:-3px; border-radius:50%; border:1px solid var(--warn); opacity:.5; animation: ring 1s ease-out infinite; }
  @keyframes ring { 0%{transform:scale(1);opacity:.5} 100%{transform:scale(1.9);opacity:0} }
  .dot-done    { background: var(--success); border-color: var(--success); }
  .dot-failed  { background: var(--danger);  border-color: var(--danger); }
  .dot-skipped { background: var(--muted);   border-color: var(--muted); }
  .step-line { width: 1px; flex: 1; min-height: 14px; background: var(--border); margin: 2px 0; }
  .step-content { flex: 1; padding-bottom: 13px; min-width: 0; }
  .step-name   { font-size: 11px; font-weight: 500; color: var(--text); margin-bottom: 2px; }
  .step-name.muted { color: var(--muted); }
  .step-desc   { font-size: 10px; color: var(--muted); font-family: var(--mono); word-break: break-word; }
  .step-code   { font-size: 9px; font-family: var(--mono); background: var(--surface2); border: 0.5px solid var(--border); border-radius: 4px; padding: 4px 8px; margin-top: 4px; display: inline-block; color: var(--accent2); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .step-result { font-size: 10px; color: var(--success); font-family: var(--mono); margin-top: 3px; word-break: break-word; }
  .step-error  { font-size: 10px; color: var(--danger); font-family: var(--mono); margin-top: 3px; word-break: break-word; }
  .step-time   { font-size: 9px; font-family: var(--mono); color: var(--muted); margin-top: 2px; }

  /* ── Output card ── */
  .output-card { background: var(--surface2); border: 0.5px solid rgba(16,185,129,.22); border-radius: 8px; padding: 10px 12px; margin-top: 8px; animation: step-in .4s ease forwards; }
  .output-label { font-size: 9px; font-family: var(--mono); color: var(--success); letter-spacing: 1px; margin-bottom: 6px; }
  .output-text  { font-size: 12px; color: var(--text); line-height: 1.6; word-break: break-word; }

  /* ── Error card ── */
  .error-card { background: rgba(239,68,68,.06); border: 0.5px solid rgba(239,68,68,.22); border-radius: 8px; padding: 10px 12px; margin-top: 8px; animation: step-in .3s ease forwards; }
  .error-label { font-size: 9px; font-family: var(--mono); color: var(--danger); letter-spacing: 1px; margin-bottom: 4px; }
  .error-text  { font-size: 11px; color: rgba(239,68,68,.85); font-family: var(--mono); word-break: break-word; }

  /* ── Empty state ── */
  .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 10px; padding: 40px; text-align: center; }
  .empty-icon  { font-size: 32px; opacity: .3; }
  .empty-text  { font-size: 12px; color: var(--muted); font-family: var(--mono); line-height: 1.7; }

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
`;

// ─── Component ─────────────────────────────────────────────────────────────
export default function App() {
  // ── State ──
  const [commandInput, setCommandInput] = useState("");
  const [loading, setLoading]           = useState(false);
  const [activeTab, setActiveTab]       = useState("execution");
  const [wsConnected, setWsConnected]   = useState(false);

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
    mediaRecorderRef.current?.stop();
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
              <div className="nav-icon" style={{ background: "rgba(0,212,170,.1)", color: "var(--accent)" }}>⚡</div>
              Intent Runner
            </div>
            <div
              className={`nav-item ${activeTab === "history" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("history");
                api.get("/api/history?limit=20").then((d) => { if (d.workflows) setHistory(d.workflows); }).catch(() => {});
              }}
            >
              <div className="nav-icon" style={{ background: "rgba(245,158,11,.1)", color: "var(--warn)" }}>📋</div>
              Audit Log
            </div>
            <div
              className={`nav-item ${activeTab === "skills" ? "active" : ""}`}
              onClick={() => setActiveTab("skills")}
            >
              <div className="nav-icon" style={{ background: "rgba(124,111,255,.1)", color: "var(--accent2)" }}>🔌</div>
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
                  🎙
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
                  <div className="exec-header">
                    <span className="exec-title">EXECUTION TRACE</span>
                    <span className={badgeClass}>{badgeLabel}</span>
                  </div>

                  {/* No data yet */}
                  {planStatus === "idle" && !loading && (
                    <div className="empty-state">
                      <div className="empty-icon">⚡</div>
                      <div className="empty-text">
                        Type an intent above and press RUN<br />
                        Execution steps will appear here in real time
                      </div>
                    </div>
                  )}

                  {/* Intent summary */}
                  {planSummary && (
                    <div className="intent-card">
                      <div className="ic-header">
                        <div className="ic-icon">⚡</div>
                        <div>
                          <div className="ic-title">{planSummary}</div>
                          <div className="ic-meta">
                            {steps.length > 0 && `${steps.length} step${steps.length !== 1 ? "s" : ""} · `}
                            {planStatus}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Steps */}
                  {steps.length > 0 && (
                    <div className="step-chain">
                      {steps.map((step, i) => (
                        <div className="step-row" key={step.id} style={{ animationDelay: `${i * 0.08}s` }}>
                          <div className="step-left">
                            <div className={`dot ${stepStatusClass(step.status)}`} />
                            {i < steps.length - 1 && <div className="step-line" />}
                          </div>
                          <div className="step-content">
                            <div className={`step-name ${step.status === "pending" ? "muted" : ""}`}>
                              {step.skill && step.action
                                ? `${step.skill}.${step.action}`
                                : step.description || step.id}
                            </div>
                            {step.description && step.description !== `${step.skill}.${step.action}` && (
                              <div className="step-desc">{step.description}</div>
                            )}
                            {step.reasoning && (
                              <div className="step-code" title={step.reasoning}>{step.reasoning}</div>
                            )}
                            {step.status === "done" && step.result && (
                              <div className="step-result">
                                ✓ {step.result.length > 120 ? step.result.slice(0, 120) + "…" : step.result}
                              </div>
                            )}
                            {step.status === "failed" && step.error && (
                              <div className="step-error">✗ {step.error.slice(0, 160)}</div>
                            )}
                            {(step.started_at || step.completed_at) && (
                              <div className="step-time">
                                {step.started_at && fmtTime(step.started_at)}
                                {step.started_at && step.completed_at && " → "}
                                {step.completed_at && fmtTime(step.completed_at)}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Output card — only when plan completed */}
                  {planStatus === "completed" && lastResult && (
                    <div className="output-card">
                      <div className="output-label">OUTPUT</div>
                      <div className="output-text">{lastResult}</div>
                    </div>
                  )}

                  {/* Error card */}
                  {commandError && (
                    <div className="error-card">
                      <div className="error-label">ERROR</div>
                      <div className="error-text">{commandError}</div>
                    </div>
                  )}
                </div>

                {/* Control bar */}
                <div className="ctrl-bar">
                  <button className="btn-ctrl" disabled={!isRunning} onClick={() => control("pause")}>⏸ Pause</button>
                  <button className="btn-ctrl" disabled={!isPaused} onClick={() => control("resume")}>▶ Resume</button>
                  <button className="btn-ctrl" disabled={!isRunning && !isPaused} onClick={() => control("skip")}>⏭ Skip</button>
                  <button className="btn-ctrl danger" disabled={!isRunning && !isPaused} onClick={() => control("abort")}>✗ Abort</button>
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

          {/* ── Right Panel ── */}
          <div className="right-panel">
            {/* Connection status */}
            <div className="rp-sec">
              <div className="rp-title">System Status</div>
              <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.8 }}>
                <div>
                  <span className={`conn-dot ${wsConnected ? "conn-ok" : "conn-err"}`} />
                  WebSocket: {wsConnected ? <span style={{ color: "var(--success)" }}>connected</span> : <span style={{ color: "var(--danger)" }}>disconnected</span>}
                </div>
                <div>
                  <span className="conn-dot conn-ok" />
                  API: {API_BASE}
                </div>
                {steps.length > 0 && (
                  <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 10, color: "var(--muted)" }}>
                    {steps.filter(s => s.status === "done").length} done ·{" "}
                    {steps.filter(s => s.status === "failed").length} failed ·{" "}
                    {steps.filter(s => s.status === "pending").length} pending
                  </div>
                )}
              </div>
            </div>

            {/* Step detail — current running step */}
            {steps.find(s => s.status === "running") && (() => {
              const running = steps.find(s => s.status === "running");
              return (
                <div className="rp-sec">
                  <div className="rp-title">Current Step</div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 500, marginBottom: 4 }}>
                    {running.skill}.{running.action}
                  </div>
                  {running.description && (
                    <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)", marginBottom: 4, wordBreak: "break-word" }}>
                      {running.description}
                    </div>
                  )}
                  {running.reasoning && (
                    <div style={{ fontSize: 9, color: "var(--accent2)", fontFamily: "var(--mono)", wordBreak: "break-word" }}>
                      {running.reasoning}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Logs — from backend ExecutionContext.logs */}
            <div className="rp-sec" style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              <div className="rp-title">
                Execution Logs
                {logs.length > 0 && (
                  <span style={{ marginLeft: 6, color: "var(--muted)", fontWeight: 400 }}>
                    ({logs.length})
                  </span>
                )}
              </div>
              {logs.length === 0
                ? <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)" }}>Waiting for logs…</div>
                : [...logs].reverse().slice(0, 40).map((log, i) => (
                  <div className="log-item" key={i}>
                    <span className="log-time">{fmtTime(log.timestamp)}</span>
                    <span className="log-msg">{log.message?.slice(0, 180)}</span>
                    <span className={`log-tag ${log.level === "ERROR" ? "tag-error" : log.level === "WARN" ? "tag-warn" : "tag-info"}`}>
                      {log.level}
                    </span>
                  </div>
                ))
              }
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

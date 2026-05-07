"""
OpenClaw Pi Engine — Executor
==============================
Dispatches action plan steps to the appropriate skill modules.
Streams status updates and logs to the dashboard via WebSocket.

Extension routing:
  When the Chrome extension is connected and the planner chose 'browser'
  for a Google/YouTube action, the executor automatically redirects to
  the 'extension' skill — no planner change needed.

Fixes in v3.1:
  - VerificationError from extension_bridge is caught and treated as a
    real step failure (not silently ignored), so Gmail / Calendar steps
    that weren't confirmed will trigger recovery / replan as appropriate.
"""

import asyncio
import re
import traceback
from datetime import datetime, date
from typing import Optional, Callable, Awaitable

from agent.planner import ActionPlan, Step, StepStatus, Planner
from agent.recovery import RecoveryManager
from utils.date_utils import normalize_date

# SoulReader for safety validation and variable resolution
# Import lazily to avoid circular imports at module load time
try:
    from memory.soul_reader import SoulReader as _SoulReaderType
except ImportError:
    _SoulReaderType = None  # type: ignore

# Import VerificationError so we can handle it specifically in _execute_step
try:
    from skills.browser.extension_bridge import VerificationError
except ImportError:
    # Fallback if import path differs — define a local alias so isinstance checks work
    class VerificationError(RuntimeError):
        pass

# Import ConfirmationRequiredException so the executor can intercept terminal
# git push / other soft-blocked commands and route them to the SOUL.md confirmation gate
try:
    from skills.terminal.shell_executor import ConfirmationRequiredException
except ImportError:
    class ConfirmationRequiredException(Exception):  # type: ignore
        command: str = ""
        reason: str = ""



# ---------------------------------------------------------------------------
# Extension routing table
# ---------------------------------------------------------------------------

_EXTENSION_ROUTABLE_ACTIONS = {
    # YouTube
    "youtube_search", "search_youtube", "searchyoutube",
    "play_youtube",   "playyoutube",
    "pause_youtube",  "pauseyoutube",
    "set_volume",     "setvolume",
    "seek_to",        "seekto",
    "get_video_info", "getvideoinfo",
    "next_video",     "nextvideo",
    # Gmail
    "compose_mail",   "composemail",
    "send_mail",      "sendmail",
    "search_mail",    "searchmail",
    "reply_mail",     "replymail",
    "get_unread",     "getunread",
    # Calendar
    "create_event",   "createevent",
    "get_events",     "getevents",
    "open_calendar",  "opencalendar",
    # Meet
    "join_meet",      "joinmeet",
    "schedule_meet",  "schedulemeet",
    "mute_mic",       "mutemic",
    "mute_camera",    "mutecamera",
    "leave_meet",     "leavemeet",
    # Drive
    "search_drive",   "searchdrive",
    "open_drive",     "opendrive",
    # Agentic web interaction
    "web_agent",      "webagent",
    "web_interact",   "webinteract",
    # Direct content extraction (no LLM cost)
    "get_page_text",  "getpagetext",
    "page_text",      "pagetext",
    "extract_text",   "extracttext",
}

_GOOGLE_DOMAINS = {
    "youtube.com", "music.youtube.com", "mail.google.com", "gmail.com",
    "calendar.google.com", "meet.google.com",
    "drive.google.com", "docs.google.com",
    "chat.openai.com", "chatgpt.com",
}


def _action_key(action: str) -> str:
    return action.lower().replace("_", "").replace("-", "")


def _should_route_to_extension(skill: str, action: str, params: dict) -> bool:
    key = _action_key(action)

    if key in {_action_key(a) for a in _EXTENSION_ROUTABLE_ACTIONS}:
        return True

    if action in ("navigate", "search"):
        url = params.get("url", "") or ""
        if url and url != "about:blank":
            return True

    return False


class SkillRegistry:
    """Registry of available skill modules for step dispatch."""

    def __init__(self):
        self._skills = {}

    def register(self, name: str, handler):
        self._skills[name] = handler

    def get(self, name: str):
        return self._skills.get(name)

    def available_skills(self) -> list:
        return list(self._skills.keys())


class ExecutionContext:
    """Holds state for a single execution run."""

    def __init__(self, plan: ActionPlan):
        self.plan = plan
        self.current_step_index = 0
        self.is_paused = False
        self.is_aborted = False
        self.logs: list = []
        self.started_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.shared: dict = {}
        self.recovery_count: int = 0
        self.max_recoveries: int = 1

    @property
    def current_step(self) -> Optional[Step]:
        if 0 <= self.current_step_index < len(self.plan.steps):
            return self.plan.steps[self.current_step_index]
        return None

    @property
    def remaining_steps(self) -> list:
        return self.plan.steps[self.current_step_index + 1:]

    @property
    def is_complete(self) -> bool:
        return self.current_step_index >= len(self.plan.steps)

    def add_log(self, level: str, message: str, step_id: str = ""):
        self.logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "step_id": step_id,
        })

    def to_dict(self):
        return {
            "plan": self.plan.to_dict(),
            "current_step_index": self.current_step_index,
            "is_paused": self.is_paused,
            "is_aborted": self.is_aborted,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "logs": self.logs[-50:],
        }


BroadcastFn = Callable[[dict], Awaitable[None]]


class Executor:
    """
    Pi Engine Executor — runs action plans step by step.

    Dispatches each step to the appropriate skill, handles pausing/skipping/aborting,
    and broadcasts state changes to the dashboard via a callback.

    SOUL.md integration (Phase 2):
      - _validate_action_safety(): checks blocked_actions + require_confirmation
        from soul_reader before every step. Blocked steps fail fast; steps that
        need confirmation emit a WS event so the frontend can show a modal.
      - _resolve_soul_vars(): expands ${today_date}, ${workspace}, ${last_project}
        etc. in step params. Lightweight regex — NOT a full templating engine.

    WHAT IS NOT HERE (future roadmap):
      Formal confirmation FSM, plugin sandboxing, proactive behavior daemons,
      multi-agent orchestration — all deferred per architecture analysis.
    """

    def __init__(
        self,
        planner: Planner,
        skill_registry: SkillRegistry,
        broadcast: Optional[BroadcastFn] = None,
        soul_reader=None,
    ):
        self.planner = planner
        self.skills = skill_registry
        self.recovery = RecoveryManager(planner)
        self.broadcast = broadcast or self._noop_broadcast
        self.context: Optional[ExecutionContext] = None
        # SoulReader reference — used for safety validation and var resolution
        # We grab it from planner.soul_reader if not explicitly provided
        self.soul_reader = soul_reader or getattr(planner, "soul_reader", None)

        # ── Confirmation gate ──────────────────────────────────────────────────
        # Maps step_id → (asyncio.Event, confirmed: bool)
        # When a step needs confirmation, an event is created and awaited.
        # The /api/confirm/{step_id} route calls resolve_confirmation() to unblock it.
        self._pending_confirmations: dict[str, dict] = {}

    async def _noop_broadcast(self, event: dict):
        pass

    async def _emit(self, event_type: str, data: dict):
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data,
        }
        await self.broadcast(event)

    async def execute_plan(self, plan: ActionPlan) -> ExecutionContext:
        self.context = ExecutionContext(plan)
        plan.status = "running"

        await self._emit("plan_started", {
            "intent": plan.intent,
            "summary": plan.summary,
            "total_steps": len(plan.steps),
        })

        self.context.add_log("INFO", f"Starting execution: {plan.summary}")

        while not self.context.is_complete and not self.context.is_aborted:
            while self.context.is_paused:
                await asyncio.sleep(0.5)

            step = self.context.current_step
            if not step:
                break

            success = await self._execute_step(step)

            if not success and not self.context.is_aborted:
                recovered = await self._handle_failure(step)
                if not recovered:
                    self.context.add_log(
                        "ERROR",
                        f"Step {step.id} failed permanently. Stopping execution.",
                        step.id,
                    )
                    plan.status = "failed"
                    break

            self.context.current_step_index += 1

        if self.context.is_aborted:
            plan.status = "aborted"
            self.context.add_log("WARN", "Execution aborted by user.")
        elif self.context.is_complete:
            plan.status = "completed"
            self.context.add_log("INFO", "All steps completed successfully.")

        self.context.completed_at = datetime.now().isoformat()

        await self._emit("plan_completed", {
            "status": plan.status,
            "completed_at": self.context.completed_at,
        })

        return self.context

    # ── SOUL.md: variable resolution ─────────────────────────────────────────

    def _resolve_soul_vars(self, params: dict) -> dict:
        """
        Expand variable tokens in step params using a simple runtime context.

        SUPPORTED VARIABLE FORMATS:
          ${today_date}         → YYYY-MM-DD  (SOUL.md macro vars)
          ${workspace}          → from soul preferences.directories.workspace
          ${downloads}          → etc.
          $env:USERPROFILE      → Windows env vars (LLM generates these in paths)
          $env:USERNAME
          $env:APPDATA
          ~                     → expanded to $env:USERPROFILE (home dir)
        """
        import os as _os

        now = datetime.now()

        # ── Base env context ─────────────────────────────────────────────────────
        userprofile = _os.environ.get("USERPROFILE", _os.path.expanduser("~"))
        username = _os.environ.get("USERNAME", "User")

        # ── SOUL.md preferences context ──────────────────────────────────────────
        if self.soul_reader:
            prefs = self.soul_reader.get_preferences()
            dirs = prefs.get("directories", {}) if isinstance(prefs, dict) else {}
            workspace = dirs.get("workspace", f"{userprofile}\\projects")
            downloads = dirs.get("downloads", f"{userprofile}\\Downloads")
            screenshots = dirs.get("screenshots", f"{userprofile}\\Pictures\\Screenshots")
            documents = dirs.get("documents", f"{userprofile}\\Documents")
            user_name = self.soul_reader.get_user_name()
        else:
            workspace = f"{userprofile}\\projects"
            downloads = f"{userprofile}\\Downloads"
            screenshots = f"{userprofile}\\Pictures\\Screenshots"
            documents = f"{userprofile}\\Documents"
            user_name = username

        soul_ctx = {
            "today_date": now.strftime("%Y-%m-%d"),
            "current_time": now.strftime("%H:%M"),
            "workspace": workspace,
            "downloads": downloads,
            "screenshots": screenshots,
            "documents": documents,
            "user_name": user_name,
            "last_project": workspace,
        }

        def _expand(value: str) -> str:
            # 1. Expand SOUL.md ${var} tokens
            def soul_replacer(m):
                return soul_ctx.get(m.group(1), m.group(0))
            value = re.sub(r"\$\{([\w_]+)\}", soul_replacer, value)

            # 2. Expand Windows $env:VAR tokens that the LLM frequently generates
            def env_replacer(m):
                return _os.environ.get(m.group(1), m.group(0))
            value = re.sub(r"\$env:(\w+)", env_replacer, value, flags=re.IGNORECASE)

            # 3. Expand bare ~ to home directory
            if value.startswith("~"):
                value = userprofile + value[1:]

            return value

        resolved = {}
        for k, v in params.items():
            resolved[k] = _expand(v) if isinstance(v, str) else v
        return resolved


    # ── SOUL.md: safety validation ────────────────────────────────────────────

    async def _validate_action_safety(self, step: Step) -> bool:
        """
        Check step against SOUL.md safety_rules before execution.

        WHY SIMPLE:
          We deliberately avoid a formal policy engine or permission matrix.
          A direct text-match against blocked_actions patterns is fast, readable,
          and catches the genuinely dangerous cases (rm -rf /, format c:, etc.).
          More nuanced policy is future roadmap.

        RETURNS:
          True  → safe to proceed
          False → step is blocked (step already marked FAILED before return)

        SIDE EFFECTS:
          - Emits 'step_blocked' WS event when an action is hard-blocked.
          - Emits 'confirm_required' WS event when confirmation is needed.
            The confirm_required case still returns True — the executor continues
            and the frontend is expected to show a modal. This is intentional:
            for now we emit-and-proceed (Phase 2 stub). A future phase can add
            an asyncio.Event that actually pauses execution until the user responds.
        """
        if not self.soul_reader:
            return True

        # Build a string representing the full command / action being attempted
        # so we can match it against safety_rules patterns
        command_text = (
            step.params.get("command", "")
            or step.params.get("path", "")
            or f"{step.skill}.{step.action}"
        ).lower()

        # ── Hard block check ───────────────────────────────────────────────────
        block_reason = self.soul_reader.is_action_blocked(command_text)
        if block_reason:
            step.status = StepStatus.FAILED
            step.error = f"[SOUL SAFETY] Blocked: {block_reason}"
            step.completed_at = datetime.now().isoformat()

            await self._emit("step_blocked", {
                "stepId": step.id,
                "reason": block_reason,
                "command": command_text,
                "message": f"This action is blocked by your SOUL.md safety rules: {block_reason}",
            })

            if self.context:
                self.context.add_log(
                    "ERROR",
                    f"[SOUL SAFETY] Step {step.id} blocked: {block_reason}",
                    step.id,
                )
            print(f"  [Safety] ✗ {step.id} BLOCKED: {block_reason}")
            return False

        # ── Confirmation check — BLOCKING until user responds ─────────────────
        confirm_msg = self.soul_reader.requires_confirmation(step.action)
        if confirm_msg:
            # Create an asyncio Event that will be resolved by the /api/confirm endpoint
            # (frontend modal) or by the CLI's input handler.
            evt = asyncio.Event()
            self._pending_confirmations[step.id] = {
                "event": evt,
                "confirmed": False,
                "action": step.action,
                "message": confirm_msg,
                "params": step.params,
            }

            # Notify frontend/CLI that confirmation is required — execution is paused
            await self._emit("confirm_required", {
                "stepId": step.id,
                "action": step.action,
                "message": confirm_msg,
                "params": step.params,
            })
            if self.context:
                self.context.add_log(
                    "WARN",
                    f"[SOUL SAFETY] Waiting for user confirmation: {step.action} — {confirm_msg}",
                    step.id,
                )

            print(f"\n  ⚠  [Confirmation Required] {confirm_msg}")
            print(f"     Action: {step.action} | Step: {step.id}")
            print(f"     Reply via dashboard or type y/n in terminal...")

            # Wait up to 120 seconds for the user to respond
            try:
                await asyncio.wait_for(evt.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                self._pending_confirmations.pop(step.id, None)
                step.status = StepStatus.SKIPPED
                step.error = "Confirmation timed out after 120s — step skipped."
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_failed", {
                    "stepId": step.id,
                    "status": "skipped",
                    "error": step.error,
                })
                if self.context:
                    self.context.add_log("WARN", f"[SOUL SAFETY] Confirmation timed out for {step.action}", step.id)
                print(f"  ✗ Confirmation timed out — step skipped.")
                return False

            entry = self._pending_confirmations.pop(step.id, {})
            confirmed = entry.get("confirmed", False)

            if not confirmed:
                step.status = StepStatus.SKIPPED
                step.error = "User declined confirmation — step skipped."
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_failed", {
                    "stepId": step.id,
                    "status": "skipped",
                    "error": step.error,
                })
                if self.context:
                    self.context.add_log("WARN", f"[SOUL SAFETY] User declined {step.action}", step.id)
                print(f"  ✗ User declined — step skipped.")
                return False

            if self.context:
                self.context.add_log("INFO", f"[SOUL SAFETY] User confirmed {step.action} — proceeding.", step.id)
            print(f"  ✓ Confirmed — proceeding with {step.action}.")

        return True

    def resolve_confirmation(self, step_id: str, confirmed: bool) -> bool:
        """
        Called by the /api/confirm route (frontend modal) or CLI input handler
        to unblock a pending confirmation gate.

        Parameters:
          step_id   — the step that is waiting
          confirmed — True = proceed, False = skip
        """
        entry = self._pending_confirmations.get(step_id)
        if entry:
            entry["confirmed"] = confirmed
            entry["event"].set()
            print(f"  [Confirm] {step_id} → {'✓ confirmed' if confirmed else '✗ declined'}")
            return True
        return False

    def get_pending_confirmations(self) -> list:
        """Returns a list of step IDs currently awaiting confirmation."""
        return [
            {
                "stepId": sid,
                "action": v["action"],
                "message": v["message"],
                "params": v["params"],
            }
            for sid, v in self._pending_confirmations.items()
        ]

    # ── Template variable resolution ({{steps.step_N.result}} system) ─────────

    def _resolve_params(self, params: dict) -> dict:
        import re as _re
        import json as _json
        if not self.context:
            return params

        step_results: dict[str, str] = {}
        step_failed:  dict[str, bool] = {}
        for s in self.context.plan.steps:
            if s.result:
                step_results[s.id] = s.result
            if s.status.value in ("failed", "skipped") or s.error:
                step_failed[s.id] = True

        def _extract_field(result_str: str, field: str) -> str:
            try:
                json_start = result_str.find('{')
                if json_start != -1:
                    obj = _json.loads(result_str[json_start:])
                    if field in obj:
                        return str(obj[field])
            except Exception:
                pass
            # Try 'key=value' or 'Key: value' patterns
            pattern = rf'(?:^|\|\s*|\s+){_re.escape(field)}[=:]\s*(\S+)'
            m = _re.search(pattern, result_str)
            if m:
                return m.group(1).strip()
            # Try 'Meet: https://...' style
            pattern2 = rf'(?i)\b{_re.escape(field)}:\s*(\S+)'
            m2 = _re.search(pattern2, result_str)
            if m2:
                return m2.group(1).strip()
            return result_str

        def _sub(value: str) -> str:
            def replacer(m):
                step_id = m.group(1)
                subfield = m.group(2)
                result = step_results.get(step_id)
                if result is None:
                    result = step_results.get(f"step_{step_id}")
                if result is not None:
                    if subfield and subfield not in ("result", "output", "content"):
                        return _extract_field(result, subfield)
                    return result
                failed = step_failed.get(step_id) or step_failed.get(f"step_{step_id}")
                if failed:
                    raise ValueError(
                        f"Cannot resolve template {m.group(0)!r}: "
                        f"step '{step_id}' failed — check prior step errors."
                    )
                return m.group(0)
            return _re.sub(
                r'\{\{?(?:steps\.)?([\w]+)(?:\.(?:result|output|content))?(?:\.([\w]+))?\}\}?',
                replacer,
                value,
            )

        def _sanitize_python_exprs(value: str) -> str:
            py_expr = _re.search(
                r'\{[^}]*\bsteps\.(step_\w+)\.result\b[^}]*\}',
                value,
            )
            if py_expr:
                full_match = py_expr.group(0)
                step_ref   = py_expr.group(1)
                if any(ch in full_match for ch in ('(', '[', '"', "'")):
                    sub = _re.search(
                        r'\bsteps\.' + _re.escape(step_ref) + r'\.result\.(\w+)',
                        full_match,
                    )
                    clean = ('{{steps.' + step_ref + '.result.' + sub.group(1) + '}}') \
                            if sub else ('{{steps.' + step_ref + '.result}}')
                    value = value.replace(full_match, clean)
            return value

        resolved = {}
        _DATE_KEYS = {"date", "start_date", "end_date"}
        for k, v in params.items():
            if isinstance(v, str):
                v = _sanitize_python_exprs(v)
                v = _sub(v)
                # Normalize relative date values → ISO dates
                if k in _DATE_KEYS:
                    v = normalize_date(v)
                resolved[k] = v
            else:
                resolved[k] = v
        return resolved


    # ─────────────────────────────────────────────────────────────────

    async def _execute_step(self, step: Step) -> bool:
        """Execute a single step by dispatching to the appropriate skill."""

        # \u2500\u2500 SOUL.md Phase 1: expand ${variable} tokens in params \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Must run before any other guard so that path/command values are real strings.
        step.params = self._resolve_soul_vars(step.params)

        # \u2500\u2500 SOUL.md Phase 2: safety validation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Blocks hard-blocked commands (rm -rf /, format c: etc.).
        # Emits confirm_required WS event for sensitive ops (non-blocking for now).
        safe = await self._validate_action_safety(step)
        if not safe:
            return False  # step already marked FAILED by _validate_action_safety

        # --- Fallback safety guard ---
        if step.action in ["web_agent", "webagent"]:
            task = step.params.get("task", "").lower()
            if "extract" in task and "click" not in task:
                step.skill = "extension"
                step.action = "get_page_text"
                step.params = {
                    "selector": "#mw-content-text"
                }

        # --- getPageText tab_id resolution guard ---
        # If the step is getPageText and tab_id looks invalid, resolve it early
        if _action_key(step.action) in ("getpagetext", "pagetext", "extracttext", "getpagetext"):
            raw_tab = step.params.get("tab_id") or step.params.get("tabId")
            tab_invalid = (
                raw_tab is None
                or str(raw_tab).strip() == ""
                or str(raw_tab) == "None"
                or "{{" in str(raw_tab)
                or "{steps." in str(raw_tab)
            )
            if not tab_invalid:
                try:
                    int(raw_tab)
                except (TypeError, ValueError):
                    tab_invalid = True

            if tab_invalid and self.context:
                shared_tid = self.context.shared.get("last_tab_id")
                if shared_tid:
                    step.params["tab_id"] = shared_tid
                    self.context.add_log(
                        "INFO",
                        f"[Executor] Resolved invalid tab_id for getPageText → {shared_tid} from shared context",
                        step.id,
                    )
                else:
                    # Remove invalid tab_id so extension falls back to active tab
                    step.params.pop("tab_id", None)
                    step.params.pop("tabId", None)
                    self.context.add_log(
                        "INFO",
                        f"[Executor] Removed invalid tab_id for getPageText — will use active tab",
                        step.id,
                    )
        # -----------------------------
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now().isoformat()

        # ── Smart extension routing ─────────────────────────────────────
        effective_skill = step.skill
        ext_handler = self.skills.get("extension")
        if (
            ext_handler is not None
            and getattr(ext_handler, "is_connected", False)
            and _should_route_to_extension(step.skill, step.action, step.params)
        ):
            effective_skill = "extension"
            self.context.add_log(
                "INFO",
                f"[Router] Redirected {step.skill}.{step.action} → extension (Chrome extension is connected)",
                step.id,
            )

        await self._emit("step_started", {
            "stepId":      step.id,
            "skill":       effective_skill,
            "action":      step.action,
            "description": step.description,
            "reasoning":   step.reasoning,
        })

        self.context.add_log(
            "INFO",
            f"Executing [{effective_skill}]: {step.description}",
            step.id,
        )

        try:
            step.params = self._resolve_params(step.params)

            skill_handler = self.skills.get(effective_skill)
            if not skill_handler:
                if effective_skill == "extension":
                    raise ConnectionError(
                        "Extension skill not registered. "
                        "Check startup — is the Chrome extension installed at chrome://extensions/?"
                    )
                raise ValueError(
                    f"Unknown skill '{effective_skill}'. "
                    f"Available: {self.skills.available_skills()}"
                )

            action_key = _action_key(step.action)

            # ── Extension reconnect wait ───────────────────────────────
            if effective_skill == "extension" and action_key not in ("webagent", "webinteract"):
                if not getattr(skill_handler, "is_connected", True):
                    self.context.add_log(
                        "INFO",
                        "[Executor] Extension suspended — waiting up to 8s for reconnect...",
                        step.id,
                    )
                    for _w in range(16):
                        await asyncio.sleep(0.5)
                        if getattr(skill_handler, "is_connected", False):
                            self.context.add_log(
                                "INFO",
                                f"[Executor] Extension reconnected after {(_w + 1) * 0.5:.1f}s",
                                step.id,
                            )
                            break
                    else:
                        raise ConnectionError(
                            "Chrome extension did not reconnect within 8 seconds. "
                            "Make sure Chrome is open and the OpenClaw extension is installed."
                        )

            # ── Inject shared context for web_agent ───────────────────
            if action_key in ("webagent", "webinteract"):
                shared_tab_id = self.context.shared.get("last_tab_id")
                raw_tab_id = step.params.get("tab_id")
                resolved_tab_id = None
                if raw_tab_id is not None:
                    try:
                        coerced = int(raw_tab_id)
                        resolved_tab_id = coerced if coerced > 0 else None
                    except (TypeError, ValueError):
                        resolved_tab_id = None
                resolved_tab_id = resolved_tab_id or shared_tab_id
                if resolved_tab_id != raw_tab_id:
                    self.context.add_log(
                        "INFO",
                        f"[Executor] Resolved tab_id {raw_tab_id!r} → {resolved_tab_id} for web_agent",
                        step.id,
                    )
                step.params["tab_id"] = resolved_tab_id

            # ── Agentic web agent ─────────────────────────────────────
            if action_key in ("webagent", "webinteract"):
                from skills.browser.extension_bridge import run_web_agent
                ext = self.skills.get("extension")
                if ext is None:
                    raise ConnectionError("Extension skill not registered — check startup logs")

                if not getattr(ext, "is_connected", False):
                    self.context.add_log(
                        "INFO",
                        "[Executor] Extension not yet connected — waiting up to 8s for reconnect...",
                        step.id,
                    )
                    for _wait in range(16):
                        await asyncio.sleep(0.5)
                        if getattr(ext, "is_connected", False):
                            self.context.add_log(
                                "INFO",
                                f"[Executor] Extension reconnected after {(_wait + 1) * 0.5:.1f}s",
                                step.id,
                            )
                            break
                    else:
                        raise ConnectionError(
                            "Chrome extension did not reconnect within 8 seconds. "
                            "Make sure the OpenClaw extension is installed and Chrome is open."
                        )

                result = await run_web_agent(
                    bridge=ext,
                    task=step.params.get("task", step.description),
                    url=step.params.get("url"),
                    tab_id=step.params.get("tab_id"),
                    gemini_client=self.planner.client,
                    model_name=self.planner.model_name,
                    max_iterations=step.params.get("max_iterations", 5),
                )
            else:
                result = await skill_handler.execute(step.action, step.params)

            step.status = StepStatus.DONE
            step.result = str(result) if result else "Success"
            step.completed_at = datetime.now().isoformat()

            # ── Store tabId in shared context ─────────────────────────
            if step.result:
                import re as _re
                tab_match = _re.search(r'"tabId"\s*:\s*(\d+)', step.result)
                if tab_match:
                    new_tab_id = int(tab_match.group(1))
                    self.context.shared["last_tab_id"] = new_tab_id
                    self.context.add_log(
                        "INFO",
                        f"[Executor] Stored tabId={new_tab_id} for next steps",
                        step.id,
                    )
                elif action_key in ("webagent", "webinteract") or (
                    action_key == "navigate" and not tab_match
                ):
                    target_url = step.params.get("url", "") or ""
                    try:
                        ext = self.skills.get("extension")
                        if ext and getattr(ext, "is_connected", False):
                            tabs_data = await ext._send("getTabs", {}, timeout=5)
                            tabs = tabs_data.get("tabs", [])
                            if tabs and target_url:
                                matched = None
                                for tab in reversed(tabs):
                                    tab_url = tab.get("url", "")
                                    if (
                                        target_url.rstrip("/") in tab_url
                                        or tab_url.startswith(target_url.split("?")[0])
                                    ):
                                        matched = tab
                                        break
                                if matched is None:
                                    matched = max(tabs, key=lambda t: t.get("id", 0))
                                self.context.shared["last_tab_id"] = matched["id"]
                                self.context.add_log(
                                    "INFO",
                                    f"[Executor] Resolved tabId={matched['id']} for url={target_url!r}",
                                    step.id,
                                )
                            elif tabs:
                                best = max(tabs, key=lambda t: t.get("id", 0))
                                self.context.shared["last_tab_id"] = best["id"]
                                self.context.add_log(
                                    "INFO",
                                    f"[Executor] Updated tabId={best['id']} after {action_key}",
                                    step.id,
                                )
                    except Exception:
                        pass

            await self._emit("step_completed", {
                "stepId": step.id,
                "status": "done",
                "result": step.result,
            })

            # ── Auto-capture YouTube URL for downstream steps ─────────
            # If this was a YouTube action, enrich the result with the actual video URL
            # so messaging steps don't send the wrong link.
            _YOUTUBE_ACTIONS = {
                "searchyoutube", "playyoutube", "nextvideo",
                "youtubesearch",
            }
            # Detect YouTube context from multiple signals
            _is_youtube = action_key in _YOUTUBE_ACTIONS
            if not _is_youtube and action_key in ("webagent", "webinteract"):
                # Check task/url params
                _combined = (step.params.get("task", "") + step.params.get("url", "")).lower()
                if "youtube" in _combined:
                    _is_youtube = True
                # Check if the step RESULT contains YouTube markers
                elif step.result and ("[YouTube]" in step.result or "youtube.com" in step.result.lower()):
                    _is_youtube = True
                # Check if a prior step navigated to YouTube
                elif any(
                    "youtube.com" in s.params.get("url", "").lower()
                    for s in self.context.plan.steps
                    if s.status == StepStatus.DONE
                    and s.action in ("navigate",)
                ):
                    _is_youtube = True
            # Also trigger for navigate actions that land on YouTube
            if not _is_youtube and action_key == "navigate":
                _nav_url = step.params.get("url", "").lower()
                if "youtube.com" in _nav_url:
                    _is_youtube = True

            if _is_youtube:
                try:
                    ext = self.skills.get("extension")
                    if ext and getattr(ext, "is_connected", False):
                        await asyncio.sleep(3)  # Wait for YouTube to settle on the watch page
                        tabs_data = await ext._send("getTabs", {}, timeout=5)
                        tabs = tabs_data.get("tabs", [])
                        yt_tab = None
                        # Prefer tabs with /watch?v= (actual video), then any youtube.com
                        for tab in reversed(tabs):
                            tab_url = tab.get("url", "")
                            if "/watch?v=" in tab_url:
                                yt_tab = tab
                                break
                        if not yt_tab:
                            for tab in reversed(tabs):
                                tab_url = tab.get("url", "")
                                if "youtube.com" in tab_url:
                                    yt_tab = tab
                                    break
                        if yt_tab:
                            video_url = yt_tab.get("url", "")
                            video_title = yt_tab.get("title", "")
                            # Append the actual URL to the step result
                            step.result = (
                                f"{step.result}\n"
                                f"video_url={video_url}\n"
                                f"video_title={video_title}"
                            )
                            self.context.shared["last_youtube_url"] = video_url
                            self.context.shared["last_tab_id"] = yt_tab.get("id")
                            self.context.add_log(
                                "INFO",
                                f"[Executor] Captured YouTube URL: {video_url}",
                                step.id,
                            )
                except Exception as e:
                    self.context.add_log(
                        "WARN",
                        f"[Executor] Could not auto-capture YouTube URL: {e}",
                        step.id,
                    )

            self.context.add_log("INFO", f"Completed: {step.result}", step.id)
            return True

        except VerificationError as e:
            # ── Verification failure: the action ran but couldn't be confirmed ──
            # Treat exactly like any other failure so recovery/replan fires.
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now().isoformat()

            await self._emit("step_failed", {
                "stepId": step.id,
                "status": "failed",
                "error":  step.error,
                "kind":   "verification_failure",
            })

            self.context.add_log(
                "ERROR",
                f"Verification failed: {step.error}",
                step.id,
            )
            return False

        except ConfirmationRequiredException as e:
            # ── Terminal command needs user confirmation (e.g. git push) ──
            # Create a confirmation gate exactly like _validate_action_safety does.
            confirm_msg = e.reason
            command = getattr(e, "command", step.params.get("command", step.action))

            evt = asyncio.Event()
            self._pending_confirmations[step.id] = {
                "event": evt,
                "confirmed": False,
                "action": step.action,
                "message": confirm_msg,
                "params": step.params,
            }

            await self._emit("confirm_required", {
                "stepId": step.id,
                "action": step.action,
                "message": confirm_msg,
                "params": step.params,
            })
            if self.context:
                self.context.add_log(
                    "WARN",
                    f"[Terminal] Waiting for user confirmation: {confirm_msg}",
                    step.id,
                )

            print(f"\n  ⚠  [Confirmation Required] {confirm_msg}")
            print(f"     Command: {command}")
            print(f"     Reply via dashboard or type y/n in terminal...")

            try:
                await asyncio.wait_for(evt.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                self._pending_confirmations.pop(step.id, None)
                step.status = StepStatus.SKIPPED
                step.error = "Confirmation timed out after 120s — step skipped."
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_failed", {"stepId": step.id, "status": "skipped", "error": step.error})
                if self.context:
                    self.context.add_log("WARN", f"[Terminal] Confirmation timed out for {step.action}", step.id)
                print(f"  ✗ Confirmation timed out — step skipped.")
                return False

            entry = self._pending_confirmations.pop(step.id, {})
            if not entry.get("confirmed", False):
                step.status = StepStatus.SKIPPED
                step.error = "User declined confirmation — step skipped."
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_failed", {"stepId": step.id, "status": "skipped", "error": step.error})
                if self.context:
                    self.context.add_log("WARN", f"[Terminal] User declined {step.action}", step.id)
                print(f"  ✗ User declined — step skipped.")
                return False

            # User confirmed — re-run the command directly (bypassing the confirmation check)
            print(f"  ✓ Confirmed — running: {command}")
            if self.context:
                self.context.add_log("INFO", f"[Terminal] User confirmed — executing: {command}", step.id)
            try:
                skill_handler = self.skills.get(step.skill)
                # Pass confirmed=True so shell_executor skips the confirmation gate
                result = await skill_handler.execute(step.action, {**step.params, "_confirmed": True})
                step.status = StepStatus.DONE
                step.result = str(result) if result else "Success"
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_completed", {"stepId": step.id, "status": "done", "result": step.result})
                if self.context:
                    self.context.add_log("INFO", f"Completed (after confirmation): {step.result}", step.id)
                return True
            except Exception as re_err:
                step.status = StepStatus.FAILED
                step.error = str(re_err)
                step.completed_at = datetime.now().isoformat()
                await self._emit("step_failed", {"stepId": step.id, "status": "failed", "error": step.error})
                if self.context:
                    self.context.add_log("ERROR", f"Failed after confirmation: {step.error}", step.id)
                return False


        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now().isoformat()

            # Always print the error so it's visible in the CLI (not just in logs)
            print(f"  [Executor] ✗ {step.id} failed: {step.error[:300]}")

            await self._emit("step_failed", {
                "stepId": step.id,
                "status": "failed",
                "error":  step.error,
            })

            self.context.add_log(
                "ERROR",
                f"Failed: {step.error}\n{traceback.format_exc()}",
                step.id,
            )

            if step.error and "loop" in step.error.lower():
                self.context.add_log(
                    "WARNING",
                    "Loop detected. Suggest switching to getPageText instead of web_agent",
                    step.id
                )

            return False

    async def _handle_failure(self, failed_step: Step) -> bool:
        """
        Handle a failed step using the recovery system.

        Returns True if recovery succeeds (or is gracefully skipped),
        False if all retries are exhausted.
        """
        if _action_key(failed_step.action) in ("webagent", "webinteract"):
            self.context.add_log(
                "WARN",
                f"[Recovery] Not replanning web_agent step '{failed_step.id}' "
                f"-- error: {failed_step.error}",
                failed_step.id,
            )
            return False

        if self.context.recovery_count >= self.context.max_recoveries:
            self.context.add_log(
                "WARN",
                f"[Recovery] Max recoveries ({self.context.max_recoveries}) reached. "
                f"Not replanning step '{failed_step.id}'. Error: {failed_step.error}",
                failed_step.id,
            )
            return False

        self.context.recovery_count += 1
        recovered = await self.recovery.attempt_recovery(
            failed_step=failed_step,
            remaining_steps=self.context.remaining_steps,
            broadcast=self.broadcast,
        )

        if recovered and recovered.steps:
            insert_pos = self.context.current_step_index + 1
            for i, recovery_step in enumerate(recovered.steps):
                self.context.plan.steps.insert(insert_pos + i, recovery_step)

            self.context.add_log(
                "WARN",
                f"Recovery plan generated with {len(recovered.steps)} alternative steps.",
                failed_step.id,
            )

            await self._emit("plan_replanned", {
                "failed_step_id": failed_step.id,
                "recovery_steps": len(recovered.steps),
            })

            return True

        return False

    # --- User Control Methods ---

    def pause(self):
        if self.context:
            self.context.is_paused = True
            self.context.add_log("WARN", "Execution paused by user.")

    def resume(self):
        if self.context:
            self.context.is_paused = False
            self.context.add_log("INFO", "Execution resumed by user.")

    def skip_step(self):
        if self.context and self.context.current_step:
            step = self.context.current_step
            step.status = StepStatus.SKIPPED
            step.completed_at = datetime.now().isoformat()
            self.context.current_step_index += 1
            self.context.add_log("WARN", f"Step {step.id} skipped by user.", step.id)

    def abort(self):
        if self.context:
            self.context.is_aborted = True

    def override_step(self, step_id: str, new_params: dict):
        if self.context:
            for step in self.context.plan.steps:
                if step.id == step_id and step.status == StepStatus.PENDING:
                    step.params.update(new_params)
                    self.context.add_log(
                        "INFO",
                        f"Step {step_id} parameters overridden by user.",
                        step_id,
                    )
                    break
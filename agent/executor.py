"""
OpenClaw Pi Engine — Executor
==============================
Dispatches action plan steps to the appropriate skill modules.
Streams status updates and logs to the dashboard via WebSocket.

Extension routing:
  When the Chrome extension is connected and the planner chose 'browser'
  for a Google/YouTube action, the executor automatically redirects to
  the 'extension' skill — no planner change needed.
"""

import asyncio
import traceback
from datetime import datetime
from typing import Optional, Callable, Awaitable

from agent.planner import ActionPlan, Step, StepStatus, Planner
from agent.recovery import RecoveryManager


# ---------------------------------------------------------------------------
# Extension routing table
# ---------------------------------------------------------------------------
# Actions that the Chrome extension handles better than Playwright.
# If the extension is connected and the planner chose 'browser', the executor
# will silently redirect these to 'extension' instead.

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
    # Agentic web interaction (works on ANY website)
    "web_agent",      "webagent",
    "web_interact",   "webinteract",
}

# URL patterns — if a navigate/search goes to these domains and the extension
# is connected, prefer the extension's navigate (opens tab in real Chrome).
_GOOGLE_DOMAINS = {
    "youtube.com", "mail.google.com", "gmail.com",
    "calendar.google.com", "meet.google.com",
    "drive.google.com", "docs.google.com",
}


def _action_key(action: str) -> str:
    """Normalise action to lowercase no-underscore for lookup."""
    return action.lower().replace("_", "").replace("-", "")


def _should_route_to_extension(skill: str, action: str, params: dict) -> bool:
    """
    Returns True if this step should be redirected to the extension skill.
    Conditions:
      1. Planner chose 'browser' (or any skill)
      2. Action is in the extension routing table
      OR navigate/search URL is a Google-managed domain.
    """
    key = _action_key(action)

    if key in {_action_key(a) for a in _EXTENSION_ROUTABLE_ACTIONS}:
        return True

    # Check URL for Google domains on navigate/search
    if action in ("navigate", "search"):
        url = params.get("url", "") or ""
        return any(domain in url for domain in _GOOGLE_DOMAINS)

    return False


class SkillRegistry:
    """Registry of available skill modules for step dispatch."""

    def __init__(self):
        self._skills = {}

    def register(self, name: str, handler):
        """Register a skill handler."""
        self._skills[name] = handler

    def get(self, name: str):
        """Get a skill handler by name."""
        return self._skills.get(name)

    def available_skills(self) -> list:
        """List all registered skill names."""
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
            "logs": self.logs[-50:],  # Last 50 logs
        }


# Type alias for the broadcast callback
BroadcastFn = Callable[[dict], Awaitable[None]]


class Executor:
    """
    Pi Engine Executor — runs action plans step by step.
    
    Dispatches each step to the appropriate skill, handles pausing/skipping/aborting,
    and broadcasts state changes to the dashboard via a callback.
    """

    def __init__(
        self,
        planner: Planner,
        skill_registry: SkillRegistry,
        broadcast: Optional[BroadcastFn] = None,
    ):
        self.planner = planner
        self.skills = skill_registry
        self.recovery = RecoveryManager(planner)
        self.broadcast = broadcast or self._noop_broadcast
        self.context: Optional[ExecutionContext] = None

    async def _noop_broadcast(self, event: dict):
        """No-op broadcast when no dashboard is connected."""
        pass

    async def _emit(self, event_type: str, data: dict):
        """Broadcast an event to the dashboard."""
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data,
        }
        await self.broadcast(event)

    async def execute_plan(self, plan: ActionPlan) -> ExecutionContext:
        """
        Execute an entire action plan step by step.
        
        Args:
            plan: The ActionPlan to execute
            
        Returns:
            ExecutionContext with final state and logs
        """
        self.context = ExecutionContext(plan)
        plan.status = "running"

        await self._emit("plan_started", {
            "intent": plan.intent,
            "summary": plan.summary,
            "total_steps": len(plan.steps),
        })

        self.context.add_log("INFO", f"Starting execution: {plan.summary}")

        while not self.context.is_complete and not self.context.is_aborted:
            # Check for pause
            while self.context.is_paused:
                await asyncio.sleep(0.5)

            step = self.context.current_step
            if not step:
                break

            success = await self._execute_step(step)

            if not success and not self.context.is_aborted:
                # Recovery system will handle retries and replanning
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

    async def _execute_step(self, step: Step) -> bool:
        """Execute a single step by dispatching to the appropriate skill."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now().isoformat()

        # ── Smart extension routing ─────────────────────────────────────
        # If the Chrome extension is connected, prefer it over Playwright
        # for any YouTube / Gmail / Calendar / Meet / Drive action,
        # regardless of which skill the planner specified.
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
        # ───────────────────────────────────────────────────────────────

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
            skill_handler = self.skills.get(effective_skill)
            if not skill_handler:
                # If extension routing failed (e.g. disconnected mid-step), fall back
                if effective_skill == "extension":
                    self.context.add_log("WARN", "Extension disconnected, falling back to browser", step.id)
                    skill_handler = self.skills.get("browser")
                    effective_skill = "browser"
                if not skill_handler:
                    raise ValueError(
                        f"Unknown skill '{effective_skill}'. "
                        f"Available: {self.skills.available_skills()}"
                    )

            # ── Agentic Web Agent: special handling ──────────────────
            # If the action is web_agent/web_interact, run the full
            # agentic loop (extract DOM → LLM → execute → repeat)
            action_key = _action_key(step.action)
            if action_key in ("webagent", "webinteract"):
                from skills.browser.extension_bridge import run_web_agent
                ext = self.skills.get("extension")
                if ext is None or not getattr(ext, "is_connected", False):
                    raise ConnectionError("Chrome extension not connected for web_agent")
                result = await run_web_agent(
                    bridge=ext,
                    task=step.params.get("task", step.description),
                    url=step.params.get("url"),
                    gemini_client=self.planner.client,
                    model_name=self.planner.model_name,
                    max_iterations=step.params.get("max_iterations", 3),
                )
            else:
                result = await skill_handler.execute(step.action, step.params)

            step.status = StepStatus.DONE
            step.result = str(result) if result else "Success"
            step.completed_at = datetime.now().isoformat()

            await self._emit("step_completed", {
                "stepId": step.id,
                "status": "done",
                "result": step.result,
            })

            self.context.add_log("INFO", f"Completed: {step.result}", step.id)
            return True

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now().isoformat()

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
            return False

    async def _handle_failure(self, failed_step: Step) -> bool:
        """
        Handle a failed step using the recovery system.
        
        Returns True if recovery succeeds, False if all retries are exhausted.
        """
        recovered = await self.recovery.attempt_recovery(
            failed_step=failed_step,
            remaining_steps=self.context.remaining_steps,
            broadcast=self.broadcast,
        )

        if recovered and recovered.steps:
            # Insert recovery steps into the plan
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
        """Pause execution after the current step completes."""
        if self.context:
            self.context.is_paused = True
            self.context.add_log("WARN", "Execution paused by user.")

    def resume(self):
        """Resume paused execution."""
        if self.context:
            self.context.is_paused = False
            self.context.add_log("INFO", "Execution resumed by user.")

    def skip_step(self):
        """Skip the current step."""
        if self.context and self.context.current_step:
            step = self.context.current_step
            step.status = StepStatus.SKIPPED
            step.completed_at = datetime.now().isoformat()
            self.context.current_step_index += 1
            self.context.add_log("WARN", f"Step {step.id} skipped by user.", step.id)

    def abort(self):
        """Abort the entire execution."""
        if self.context:
            self.context.is_aborted = True

    def override_step(self, step_id: str, new_params: dict):
        """Override parameters of a pending step."""
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

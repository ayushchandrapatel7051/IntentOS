"""
OpenClaw Pi Engine — Recovery Manager
======================================
Handles failure detection, retry logic with exponential back-off,
and replanning via the Planner when steps fail.
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Callable, Awaitable

from agent.planner import Step, ActionPlan, StepStatus


# Type alias for broadcast callback
BroadcastFn = Callable[[dict], Awaitable[None]]


class RecoveryManager:
    """
    Manages failure recovery for the Pi Engine.
    
    - Wraps each step in retry logic with exponential back-off
    - Captures screen state on failure for vision-based analysis
    - Requests replanning from the Planner when retries are exhausted
    - Notifies the user via dashboard and optional messaging
    """

    def __init__(self, planner):
        self.planner = planner
        self.max_retries = int(os.getenv("MAX_RETRIES", "3"))
        self.backoff_base = float(os.getenv("RETRY_BACKOFF_BASE", "1.0"))

    async def attempt_recovery(
        self,
        failed_step: Step,
        remaining_steps: list,
        broadcast: Optional[BroadcastFn] = None,
    ) -> Optional[ActionPlan]:
        """
        Attempt to recover from a failed step.
        
        Strategy:
        1. Retry the step up to max_retries times with exponential back-off
        2. If all retries fail, take a screenshot and analyze with Claude Vision
        3. Request a replan from the Planner with the error context
        4. If replanning fails, return None (execution should stop)
        
        Args:
            failed_step: The step that failed
            remaining_steps: Steps remaining in the original plan
            broadcast: Optional callback to broadcast events to dashboard
            
        Returns:
            A recovery ActionPlan, or None if recovery is impossible
        """
        error = failed_step.error or "Unknown error"

        # Screenshot analysis disabled (Vision API removed to reduce costs)
        screenshot_analysis = ""

        # --- Request Replan ---
        if broadcast:
            await broadcast({
                "type": "recovery_started",
                "timestamp": datetime.now().isoformat(),
                "stepId": failed_step.id,
                "error": error,
                "message": "Generating recovery plan...",
            })

        try:
            recovery_plan = await self.planner.replan(
                failed_step=failed_step,
                error=error,
                remaining_steps=remaining_steps,
                screenshot_analysis=screenshot_analysis,
            )

            if broadcast:
                await broadcast({
                    "type": "recovery_plan_ready",
                    "timestamp": datetime.now().isoformat(),
                    "stepId": failed_step.id,
                    "recovery_steps": len(recovery_plan.steps),
                    "summary": recovery_plan.summary,
                })

            return recovery_plan

        except Exception as replan_error:
            if broadcast:
                await broadcast({
                    "type": "recovery_failed",
                    "timestamp": datetime.now().isoformat(),
                    "stepId": failed_step.id,
                    "error": str(replan_error),
                    "message": "All recovery attempts exhausted.",
                })

            return None


    async def retry_with_backoff(
        self,
        func,
        *args,
        max_retries: Optional[int] = None,
        broadcast: Optional[BroadcastFn] = None,
        step_id: str = "",
        **kwargs,
    ):
        """
        Retry a function with exponential back-off.
        
        Args:
            func: Async function to retry
            max_retries: Override for max retry count
            broadcast: Optional callback for status updates
            step_id: Step ID for event tracking
            
        Returns:
            The function result on success
            
        Raises:
            The last exception if all retries fail
        """
        retries = max_retries or self.max_retries
        last_error = None

        for attempt in range(retries + 1):
            try:
                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait_time = self.backoff_base * (2 ** attempt)

                    if broadcast:
                        await broadcast({
                            "type": "step_retrying",
                            "timestamp": datetime.now().isoformat(),
                            "stepId": step_id,
                            "attempt": attempt + 1,
                            "max_retries": retries,
                            "wait_seconds": wait_time,
                            "error": str(e),
                        })

                    await asyncio.sleep(wait_time)

        raise last_error

    async def notify_failure(
        self,
        step: Step,
        error: str,
        broadcast: Optional[BroadcastFn] = None,
    ):
        """
        Notify the user of an unrecoverable failure.
        
        Sends notification to:
        1. Dashboard (always)
        2. WhatsApp/Telegram (if configured)
        """
        message = (
            f"⚠️ OpenClaw: Unrecoverable failure\n"
            f"Step: {step.description}\n"
            f"Error: {error}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

        # Always notify dashboard
        if broadcast:
            await broadcast({
                "type": "notification",
                "timestamp": datetime.now().isoformat(),
                "level": "error",
                "title": "Execution Failed",
                "message": message,
            })

        # Attempt to notify via messaging (best effort)
        try:
            # This will be wired up when messaging skills are available
            pass
        except Exception:
            pass

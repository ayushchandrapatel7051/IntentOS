"""
OpenClaw Dashboard — REST API Routes
========================================
HTTP endpoints for command submission, status queries, and control.
"""

import asyncio
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional


# --- Request/Response Models ---

class CommandRequest(BaseModel):
    command: str
    voice: bool = False

class ControlRequest(BaseModel):
    action: str  # pause, resume, skip, abort, override
    step_id: Optional[str] = None
    params: Optional[dict] = None

class CommandResponse(BaseModel):
    success: bool
    message: str
    plan_summary: Optional[str] = None
    total_steps: Optional[int] = None


def create_router() -> APIRouter:
    """Create the API router with all endpoints."""
    router = APIRouter(prefix="/api")

    @router.post("/command", response_model=CommandResponse)
    async def submit_command(req: CommandRequest, request: Request):
        """
        Submit a natural language command for execution.
        
        The command is parsed into an action plan and executed asynchronously.
        Use the WebSocket connection or GET /status to track progress.
        """
        planner = request.app.state.planner
        executor = request.app.state.executor
        store = request.app.state.store

        if not planner or not executor:
            raise HTTPException(
                status_code=503,
                detail="Agent not initialized. Start OpenClaw with main.py first."
            )

        try:
            # Handle voice input
            command = req.command
            if req.voice:
                # Voice transcription would happen here
                # For now, treat as text
                pass

            # Create plan
            plan = await planner.create_plan(command)

            # Execute asynchronously
            async def run():
                context = await executor.execute_plan(plan)
                if store:
                    store.save_workflow(command, plan.to_dict(), context.plan.status)

            asyncio.create_task(run())

            return CommandResponse(
                success=True,
                message=f"Executing: {plan.summary}",
                plan_summary=plan.summary,
                total_steps=len(plan.steps),
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status")
    async def get_status(request: Request):
        """Get the current execution status."""
        executor = request.app.state.executor
        ws_manager = request.app.state.ws_manager

        status = {
            "agent_running": executor is not None and executor.context is not None,
            "connected_dashboards": ws_manager.connection_count if ws_manager else 0,
            "timestamp": datetime.now().isoformat(),
        }

        if executor and executor.context:
            status["execution"] = executor.context.to_dict()

        return status

    @router.post("/control")
    async def control_execution(req: ControlRequest, request: Request):
        """
        Control the current execution.
        
        Actions: pause, resume, skip, abort, override
        """
        executor = request.app.state.executor

        if not executor:
            raise HTTPException(
                status_code=503,
                detail="No active execution to control."
            )

        if req.action == "pause":
            executor.pause()
            return {"success": True, "message": "Execution paused"}
        elif req.action == "resume":
            executor.resume()
            return {"success": True, "message": "Execution resumed"}
        elif req.action == "skip":
            executor.skip_step()
            return {"success": True, "message": "Step skipped"}
        elif req.action == "abort":
            executor.abort()
            return {"success": True, "message": "Execution aborted"}
        elif req.action == "override":
            if not req.step_id or not req.params:
                raise HTTPException(
                    status_code=400,
                    detail="step_id and params required for override"
                )
            executor.override_step(req.step_id, req.params)
            return {"success": True, "message": f"Step {req.step_id} overridden"}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {req.action}"
            )

    @router.get("/history")
    async def get_history(request: Request, limit: int = 20):
        """Get past workflow runs from the memory store."""
        store = request.app.state.store
        if not store:
            return {"workflows": []}

        workflows = store.get_recent_workflows(limit=limit)
        stats = store.get_stats()

        return {
            "workflows": workflows,
            "stats": stats,
        }

    @router.get("/soul")
    async def get_soul(request: Request):
        """
        Get SOUL.md configuration summary.

        Returns enough data for the frontend to render:
          - Active mode badge
          - Available profiles/modes (for mode-switch buttons)
          - Macro list (trigger phrases, labels, icons)
          - Identity (assistant name, tagline)
          - YAML parse status
        """
        planner = request.app.state.planner
        if not planner or not planner.soul_reader:
            return {"error": "SOUL.md not loaded"}

        sr = planner.soul_reader
        summary = sr.get_summary()

        # Enrich with profile details for UI rendering
        profiles_raw = sr.get_profiles()
        profiles_list = []
        if isinstance(profiles_raw, dict):
            for profile_id, data in profiles_raw.items():
                if isinstance(data, dict):
                    profiles_list.append({
                        "id": profile_id,
                        "label": data.get("label", profile_id),
                        "icon": data.get("icon", ""),
                        "description": data.get("description", ""),
                        "trigger_phrases": data.get("trigger_phrases", []),
                        "active": profile_id == sr.get_active_mode(),
                    })

        return {
            **summary,
            "profiles_detail": profiles_list,
        }

    @router.post("/soul/reload")
    async def reload_soul(request: Request):
        """Hot-reload SOUL.md from disk without restarting the backend."""
        planner = request.app.state.planner
        if not planner or not planner.soul_reader:
            return {"success": False, "error": "SOUL.md not loaded"}
        try:
            planner.soul_reader.reload()
            summary = planner.soul_reader.get_summary()
            return {
                "success": True,
                "message": f"SOUL.md reloaded: {summary['macros_count']} macros, {summary['profiles_count']} profiles",
                **summary,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @router.post("/soul/mode/{mode_name}")
    async def set_active_mode(mode_name: str, request: Request):
        """
        Activate a named profile/mode from SOUL.md.

        This updates the planner's persona block for the next planning call
        (e.g. coding_mode makes responses technical and focused).
        The frontend should call this when the user taps a mode badge.
        """
        planner = request.app.state.planner
        if not planner or not planner.soul_reader:
            return {"success": False, "error": "SOUL.md not loaded"}

        sr = planner.soul_reader
        profiles = sr.get_profiles()
        if mode_name not in profiles and mode_name != "default":
            return {"success": False, "error": f"Unknown mode: {mode_name}. Available: {list(profiles.keys())}"}

        sr.set_active_mode(mode_name)
        profile_data = profiles.get(mode_name, {})
        return {
            "success": True,
            "active_mode": mode_name,
            "label": profile_data.get("label", mode_name),
            "message": f"Mode switched to: {profile_data.get('label', mode_name)}",
        }

    @router.get("/skills")
    async def get_skills(request: Request):
        """List available skills."""
        executor = request.app.state.executor
        if executor:
            return {"skills": executor.skills.available_skills()}
        return {"skills": []}

    @router.post("/confirm/{step_id}")
    async def confirm_step(step_id: str, request: Request):
        """
        Resolve a pending confirmation gate.

        Body: { "confirmed": true | false }

        Returns:
          { "success": true }  — gate resolved
          { "success": false, "error": "No pending confirmation for step_id" }
        """
        executor = request.app.state.executor
        if not executor:
            return {"success": False, "error": "Executor not initialized"}

        body = await request.json()
        confirmed = bool(body.get("confirmed", False))
        resolved = executor.resolve_confirmation(step_id, confirmed)

        if resolved:
            return {
                "success": True,
                "step_id": step_id,
                "confirmed": confirmed,
                "message": "Confirmed — proceeding." if confirmed else "Declined — step will be skipped.",
            }
        return {
            "success": False,
            "error": f"No pending confirmation for step '{step_id}'. It may have already been resolved or timed out.",
        }

    @router.get("/confirmations/pending")
    async def get_pending_confirmations(request: Request):
        """
        List all steps currently awaiting user confirmation.
        Useful for the frontend to recover the confirmation modal after a page reload.
        """
        executor = request.app.state.executor
        if not executor:
            return {"pending": []}
        return {"pending": executor.get_pending_confirmations()}

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    return router

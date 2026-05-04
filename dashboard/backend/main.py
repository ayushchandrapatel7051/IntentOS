"""
IntentOS Dashboard — FastAPI Backend
=======================================
REST API + WebSocket server for the Command Center Dashboard.
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from dashboard.backend.ws_manager import ConnectionManager
from dashboard.backend.routes import create_router


# Path to the Vite-built frontend
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


def create_app(executor=None, ws_manager=None, planner=None, store=None) -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="IntentOS Command Center",
        description="Real-time agent execution dashboard",
        version="1.0.0-alpha",
    )

    # CORS — allow dashboard frontend (dev server on :3000)
    frontend_port = os.getenv("DASHBOARD_FRONTEND_PORT", "3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{frontend_port}",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store dependencies on app state
    app.state.executor = executor
    app.state.ws_manager = ws_manager or ConnectionManager()
    app.state.planner = planner
    app.state.store = store

    # Register routes
    router = create_router()
    app.include_router(router)

    # WebSocket endpoint
    from fastapi import WebSocket, WebSocketDisconnect

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        manager = app.state.ws_manager
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Client can send commands via WebSocket too
                import json
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "command":
                        # Forward to command handler
                        await _handle_ws_command(app, msg)
                    elif msg.get("type") == "control":
                        await _handle_ws_control(app, msg)
                except json.JSONDecodeError:
                    await websocket.send_json({"error": "Invalid JSON"})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # ── Serve built React frontend (production) ──────────────────────
    if _FRONTEND_DIST.exists():
        # Mount static assets (JS/CSS/images)
        app.mount(
            "/assets",
            StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
            name="assets",
        )

        @app.get("/", include_in_schema=False)
        async def serve_spa_root():
            return FileResponse(str(_FRONTEND_DIST / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa_fallback(full_path: str):
            """Catch-all: serve index.html for any non-API path (SPA routing)."""
            # Don't intercept API or WebSocket routes
            if full_path.startswith("api/") or full_path == "ws":
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            file_path = _FRONTEND_DIST / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(_FRONTEND_DIST / "index.html"))
    else:
        @app.get("/", include_in_schema=False)
        async def root():
            return {
                "name": "IntentOS Command Center",
                "version": "1.0.0-alpha",
                "status": "running",
                "note": "Frontend not built. Run: cd dashboard/frontend && npm run build",
            }

    return app


async def _handle_ws_command(app, msg: dict):
    """Handle a command received via WebSocket."""
    command = msg.get("command", "")
    if not command:
        return

    executor = app.state.executor
    planner = app.state.planner
    store = app.state.store

    if executor and planner:
        import asyncio
        
        async def run_command():
            plan = await planner.create_plan(command)
            context = await executor.execute_plan(plan)
            if store:
                store.save_workflow(command, plan.to_dict(), context.plan.status)

        asyncio.create_task(run_command())


async def _handle_ws_control(app, msg: dict):
    """Handle a control action via WebSocket."""
    action = msg.get("action", "")
    executor = app.state.executor

    if not executor:
        return

    if action == "pause":
        executor.pause()
    elif action == "resume":
        executor.resume()
    elif action == "skip":
        executor.skip_step()
    elif action == "abort":
        executor.abort()
    elif action == "override":
        step_id = msg.get("stepId", "")
        params = msg.get("params", {})
        executor.override_step(step_id, params)

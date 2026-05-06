"""
IntentOS — Main Entry Point
==============================
Initializes all subsystems and starts the agent loop + dashboard.

Cost-effective skill set:
  ✓ browser    — Playwright (no Vision API calls)
  ✓ terminal   — subprocess
  ✓ files      — pathlib + watchdog
  ✓ apps       — apps.json launcher + hotkeys  (NEW)
  ✓ messaging  — WhatsApp/Telegram via desktop app + shortcuts  (NEW)
  ✓ vision     — MSS screenshots + PyAutoGUI  (no Claude Vision API)
  ✗ calendar   — removed (use browser skill against Google Calendar)
"""

import asyncio
import os
import sys
import socket
from pathlib import Path
from dotenv import load_dotenv
from memory.rag_store import RAGStore

import logging

# Force UTF-8 output on Windows (needed for the banner art)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Silence the noisy websockets handshake tracebacks that appear on every
# Chrome MV3 service worker reconnect — these are expected, not errors.
logging.getLogger("websockets").setLevel(logging.CRITICAL)
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)


def _find_free_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Return preferred port if free, otherwise find the next available one."""
    for port in range(preferred, preferred + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {preferred}-{preferred + 20}")


def _kill_port_occupant(port: int) -> bool:
    """
    Kill any process LISTENING on the given TCP port (Windows).
    Used to free port 8765 when restarting IntentOS without stopping the old process.
    Returns True if a process was found and killed.
    """
    import subprocess as _sp
    try:
        r = _sp.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid = int(parts[-1])
                    if pid > 0 and pid != os.getpid():
                        _sp.run(["taskkill", "/F", "/PID", str(pid)],
                                capture_output=True, timeout=5)
                        return True
    except Exception:
        pass
    return False


# Load environment variables
load_dotenv()

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))


async def main():
    """Initialize and start all IntentOS subsystems."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    # --- Banner ---
    banner = Text()
    banner.append("  ██████  ██████  ███████ ███    ██  ██████ ██       █████  ██     ██\n", style="bold cyan")
    banner.append(" ██    ██ ██   ██ ██      ████   ██ ██      ██      ██   ██ ██     ██\n", style="bold cyan")
    banner.append(" ██    ██ ██████  █████   ██ ██  ██ ██      ██      ███████ ██  █  ██\n", style="bold cyan")
    banner.append(" ██    ██ ██      ██      ██  ██ ██ ██      ██      ██   ██ ██ ███ ██\n", style="bold cyan")
    banner.append("  ██████  ██      ███████ ██   ████  ██████ ███████ ██   ██  ███ ███\n", style="bold cyan")
    banner.append("\n         Intent-Based Operating System v1.0.0-alpha\n", style="bold white")
    banner.append("         Control your entire computer with natural language\n", style="dim")

    console.print(Panel(banner, border_style="cyan", padding=(1, 2)))

    # --- Initialize Memory ---
    console.print("[cyan]▸[/] Loading SOUL.md...", end=" ")
    from memory.soul_reader import SoulReader
    soul_reader = SoulReader()
    soul_summary = soul_reader.get_summary()
    console.print(f"[green]✓[/] {soul_summary['macros_count']} macros, {soul_summary['rules_count']} rules loaded")

    console.print("[cyan]▸[/] Initializing workflow store...", end=" ")
    from memory.store import WorkflowStore
    store = WorkflowStore()
    stats = store.get_stats()
    console.print(f"[green]✓[/] {stats['total_workflows']} previous workflows")

    # --- Initialize Agent ---
    console.print("[cyan]▸[/] Initializing Pi Engine Planner...", end=" ")
    from agent.planner import Planner
    planner = Planner(soul_reader=soul_reader)
    api_status = "Gemini (Vertex AI) connected" if planner.client else "offline mode — run `gcloud auth application-default login`"
    console.print(f"[green]✓[/] {api_status}")

    # --- Initialize Skills ---
    console.print("[cyan]▸[/] Registering skills...")
    from agent.executor import Executor, SkillRegistry

    skill_registry = SkillRegistry()

    # Browser Skill — Playwright CDP
    try:
        from skills.browser.playwright_driver import PlaywrightDriver
        browser = PlaywrightDriver()
        skill_registry.register("browser", browser)
        console.print("  [green]✓[/] Browser (Playwright)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Browser: {e}")

    # Terminal Skill — subprocess
    try:
        from skills.terminal.shell_executor import ShellExecutor
        terminal = ShellExecutor()
        skill_registry.register("terminal", terminal)
        console.print("  [green]✓[/] Terminal (subprocess)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Terminal: {e}")

    # Files Skill — pathlib + watchdog
    try:
        from skills.files.file_manager import FileManager
        files = FileManager()
        skill_registry.register("files", files)
        console.print("  [green]✓[/] Files (pathlib)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Files: {e}")

    # App Launcher Skill — apps.json + hotkeys
    try:
        from skills.apps.app_launcher import AppLauncher
        apps = AppLauncher()
        skill_registry.register("apps", apps)
        console.print("  [green]✓[/] Apps (apps.json launcher + hotkeys)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Apps: {e}")

    # Messaging Skill — desktop app + keyboard shortcuts (no API)
    try:
        from skills.messaging.messaging_skill import MessagingSkill
        messaging = MessagingSkill()
        skill_registry.register("messaging", messaging)
        console.print("  [green]✓[/] Messaging (WhatsApp & Telegram via shortcuts)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Messaging: {e}")

    # Vision Skill — MSS screenshots + PyAutoGUI (no Claude Vision API)
    try:
        from skills.vision.screen_controller import ScreenController
        vision = ScreenController()
        skill_registry.register("vision", vision)
        console.print("  [green]\u2713[/] Vision (MSS + PyAutoGUI — no API cost)")
    except Exception as e:
        console.print(f"  [yellow]\u26a0[/] Vision: {e}")

    # AI Skill — LLM text analysis and summarization
    try:
        from skills.ai.ai_skill import AISkill
        ai_skill = AISkill(planner=planner)
        skill_registry.register("ai", ai_skill)
        console.print("  [green]\u2713[/] AI (LLM Reasoning)")
    except Exception as e:
        console.print(f"  [yellow]\u26a0[/] AI: {e}")

    # Extension Skill — Chrome Extension WebSocket bridge (YouTube, Gmail, Meet, Calendar)
    extension_bridge = None
    try:
        from skills.browser.extension_bridge import ExtensionBridge
        ext_port = int(os.getenv("EXTENSION_WS_PORT", "8765"))

        # Free port if a stale IntentOS process is still holding it (Errno 10048 on Windows)
        if _kill_port_occupant(ext_port):
            console.print(f"  [yellow]>[/] Freed stale process on port {ext_port}, restarting bridge...")
            await asyncio.sleep(0.7)  # Give the OS time to release the socket

        extension_bridge = ExtensionBridge(port=ext_port)
        await extension_bridge.start_server()
        skill_registry.register("extension", extension_bridge)
        console.print(f"  [green]\u2713[/] Extension Bridge (ws://127.0.0.1:{ext_port}) \u2014 waiting for Chrome extension")
    except Exception as e:
        console.print(f"  [yellow]\u26a0[/] Extension Bridge: {e}")

    # --- Initialize Dashboard ---
    console.print("[cyan]▸[/] Starting Command Center Dashboard...", end=" ")

    from dashboard.backend.main import create_app
    from dashboard.backend.ws_manager import ConnectionManager

    ws_manager = ConnectionManager()
    app = create_app(
        executor=None,  # Set after executor creation
        ws_manager=ws_manager,
        planner=planner,
        store=store,
    )

    # Create executor with broadcast function
    executor = Executor(
        planner=planner,
        skill_registry=skill_registry,
        broadcast=ws_manager.broadcast,
    )

    # Wire executor into the dashboard
    app.state.executor = executor

    from integration_patch import apply_patches
    apply_patches(executor, planner, app)

    console.print("[green]✓[/] Dashboard ready")

    # --- Start Dashboard Server ---
    import uvicorn

    dashboard_host    = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    preferred_port    = int(os.getenv("DASHBOARD_PORT", "8000"))
    dashboard_port    = _find_free_port(preferred_port, dashboard_host)
    if dashboard_port != preferred_port:
        console.print(f"  [yellow]⚠[/] Port {preferred_port} busy — using {dashboard_port} instead")

    console.print()
    console.print("[bold green]◉ IntentOS is running[/]")
    console.print(f"  Dashboard: [link=http://{dashboard_host}:{dashboard_port}]http://{dashboard_host}:{dashboard_port}[/link]")
    console.print(f"  Skills: {', '.join(skill_registry.available_skills())}")
    console.print()

    # --- Interactive CLI Loop (runs alongside dashboard) ---
    async def cli_loop():
        """Simple CLI for text commands when dashboard isn't open."""
        import json
        import os
        
        await asyncio.sleep(2)  # Let dashboard start first
        console.print("[dim]Type a command (or 'quit' to exit):[/]")

        command_history = []
        setups_file = "setups.json"
        
        if not os.path.exists(setups_file):
            with open(setups_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

        def load_setups():
            with open(setups_file, "r", encoding="utf-8") as f:
                return json.load(f)

        def save_setups(data):
            with open(setups_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

        async def process_intent(cmd_text):
            console.print("[cyan]Planning...[/]")
            plan = await planner.create_plan(cmd_text)

            console.print(f"[cyan]Plan:[/] {plan.summary}")
            for step in plan.steps:
                console.print(f"  [dim]{step.id}[/] [{step.skill}] {step.action}")

            console.print(f"\n[cyan]Executing {len(plan.steps)} steps...[/]")
            context = await executor.execute_plan(plan)

            needs_confirm = []

            for step in context.plan.steps:
                icon = "[green]\u2713[/]" if step.status.value == "done" else "[red]\u2717[/]"
                console.print(f"  {icon} [bold]{step.id}[/] [{step.skill}.{step.action}]")

                if step.params:
                    cmd = (step.params.get("command")
                           or step.params.get("name")
                           or str(step.params))
                    console.print(f"      [dim]\u25b6 {cmd}[/]")

                if step.result and "CONFIRM_REQUIRED" in step.result:
                    console.print(f"      [yellow]\u26a0 {step.result}[/]")
                    needs_confirm.append(step)
                elif step.result and step.result.strip():
                    for line in step.result.strip().splitlines()[:5]:
                        console.print(f"      [dim]{line}[/]")

                if step.error:
                    console.print(f"      [red]Error: {step.error[:200]}[/]")

            for step in needs_confirm:
                raw_path  = step.params.get("path", "this action")
                real_path = raw_path.replace("$env:USERPROFILE", str(__import__("pathlib").Path.home()))
                answer = await asyncio.to_thread(
                    input,
                    f"\n  \u26a0  Confirm delete: {real_path}? [y/N] "
                )
                if answer.strip().lower() == "y":
                    forced_params = {**step.params, "force": True}
                    try:
                        handler = executor.skills.get(step.skill)
                        result  = await handler.execute(step.action, forced_params)
                        console.print(f"      [green]\u2713 {result}[/]")
                    except Exception as e:
                        console.print(f"      [red]\u2717 {e}[/]")
                else:
                    console.print("      [dim]Skipped.[/]")

            if context.plan.status == "completed":
                console.print("[bold green]\u2713 Done![/]")
            else:
                console.print(f"[bold red]\u2717 Status: {context.plan.status}[/]")

            store.save_workflow(cmd_text, plan.to_dict(), context.plan.status)

        while True:
            try:
                command = await asyncio.to_thread(input, "\n🤖 IntentOS > ")
                command = command.strip()

                if not command:
                    continue
                if command.lower() in ("quit", "exit", "q"):
                    console.print("[yellow]Shutting down...[/]")
                    break

                cmd_lower = command.lower()
                
                # --- History Commands ---
                if cmd_lower == "history":
                    if not command_history:
                        console.print("📭 [yellow]History is empty.[/]")
                    else:
                        console.print("📜 [bold]Command History:[/]")
                        for i, past_cmd in enumerate(command_history, 1):
                            console.print(f"  {i}. {past_cmd}")
                    continue
                    
                is_repeat = False
                if cmd_lower.startswith("repeat"):
                    parts = cmd_lower.split()
                    if len(parts) == 1:
                        n = 1
                    elif len(parts) == 2 and parts[1].isdigit():
                        n = int(parts[1])
                    else:
                        console.print("❌ [red]Usage: repeat OR repeat <n>[/]")
                        continue
                        
                    if not command_history:
                        console.print("❌ [red]History is empty.[/]")
                        continue
                    if n < 1 or n > len(command_history):
                        console.print(f"❌ [red]Invalid index. Must be between 1 and {len(command_history)}.[/]")
                        continue
                        
                    command = command_history[-n]
                    cmd_lower = command.lower()
                    is_repeat = True
                    console.print(f"🔄 [cyan]Repeating:[/] {command}")

                # --- Setup System Commands ---
                if cmd_lower == "list setups":
                    setups = load_setups()
                    if not setups:
                        console.print("📭 [yellow]No setups found.[/]")
                    else:
                        console.print("📜 [bold]Available Setups:[/]")
                        for name, cmds in setups.items():
                            console.print(f"  - {name} ({len(cmds)} commands)")
                    continue

                if cmd_lower.startswith("create setup "):
                    setup_name = cmd_lower.replace("create setup ", "", 1).strip()
                    if not setup_name:
                        console.print("❌ [red]Usage: create setup <name>[/]")
                        continue
                        
                    setups = load_setups()
                    if setup_name in setups:
                        ans = await asyncio.to_thread(input, f"  ⚠️ Setup '{setup_name}' already exists. Overwrite? (y/n): ")
                        if ans.strip().lower() != 'y':
                            console.print("❌ [yellow]Cancelled.[/]")
                            continue

                    console.print(f"🛠️ [cyan]Creating setup: '{setup_name}'[/]")
                    console.print("Enter commands one by one. Type 'done' when finished. (Max 10)")
                    cmds = []
                    while len(cmds) < 10:
                        c = await asyncio.to_thread(input, f"  [{len(cmds)+1}/10] > ")
                        c = c.strip()
                        if c.lower() == "done":
                            break
                        if c:
                            cmds.append(c)
                            
                    if not cmds:
                        console.print("❌ [yellow]No commands added. Cancelled.[/]")
                        continue
                        
                    setups[setup_name] = cmds
                    save_setups(setups)
                    print("Setup saved:", setup_name)
                    console.print(f"✅ [green]Setup '{setup_name}' saved with {len(cmds)} commands![/]")
                    continue

                if cmd_lower.startswith("delete setup "):
                    setup_name = cmd_lower.replace("delete setup ", "", 1).strip()
                    if not setup_name:
                        console.print("❌ [red]Usage: delete setup <name>[/]")
                        continue
                        
                    setups = load_setups()
                    if setup_name in setups:
                        ans = await asyncio.to_thread(input, f"  ⚠️ Are you sure you want to delete setup '{setup_name}'? (y/n): ")
                        if ans.strip().lower() == 'y':
                            del setups[setup_name]
                            save_setups(setups)
                            console.print(f"🗑️ [green]Setup '{setup_name}' deleted.[/]")
                        else:
                            console.print("❌ [yellow]Cancelled.[/]")
                    else:
                        console.print(f"❌ [red]Setup '{setup_name}' not found.[/]")
                    continue

                if cmd_lower.startswith("edit setup "):
                    setup_name = cmd_lower.replace("edit setup ", "", 1).strip()
                    if not setup_name:
                        console.print("❌ [red]Usage: edit setup <name>[/]")
                        continue
                        
                    setups = load_setups()
                    if setup_name not in setups:
                        console.print(f"❌ [red]Setup '{setup_name}' not found. Use 'create setup {setup_name}' instead.[/]")
                        continue
                        
                    cmds = setups[setup_name]
                    console.print(f"🛠️ [cyan]Editing setup: '{setup_name}'[/]")
                    while True:
                        console.print("\n[bold]Current commands:[/]")
                        if not cmds:
                            console.print("  (Empty)")
                        else:
                            for idx, c in enumerate(cmds, 1):
                                console.print(f"  {idx}. {c}")
                        
                        console.print("\n[dim]Options: type number to delete, 'clear' to empty, command text to add, or 'done'[/]")
                        c = await asyncio.to_thread(input, "  > ")
                        c = c.strip()
                        if not c:
                            continue
                        if c.lower() == "done":
                            break
                        elif c.lower() == "clear":
                            cmds.clear()
                            console.print("🗑️ [yellow]Cleared all commands.[/]")
                        elif c.isdigit():
                            idx = int(c) - 1
                            if 0 <= idx < len(cmds):
                                removed = cmds.pop(idx)
                                console.print(f"🗑️ [yellow]Removed: {removed}[/]")
                            else:
                                console.print("❌ [red]Invalid number.[/]")
                        else:
                            if len(cmds) >= 10:
                                console.print("❌ [red]Max 10 commands reached.[/]")
                            else:
                                cmds.append(c)
                                console.print(f"➕ [green]Added: {c}[/]")
                                
                    setups[setup_name] = cmds
                    save_setups(setups)
                    console.print(f"✅ [green]Setup '{setup_name}' updated with {len(cmds)} commands![/]")
                    continue

                # Run a Setup
                is_setup_run = False
                if cmd_lower.startswith("open "):
                    target = cmd_lower[5:].strip()
                    setups = load_setups()
                    if target in setups:
                        is_setup_run = True
                        setup_cmds = setups[target]
                        console.print(f"🚀 [cyan]Running setup: '{target}' ({len(setup_cmds)} commands)[/]")
                        
                        for i, setup_cmd in enumerate(setup_cmds, 1):
                            console.print(f"\n[{i}/{len(setup_cmds)}] Executing: {setup_cmd}")
                            await process_intent(setup_cmd)
                            if i < len(setup_cmds):
                                await asyncio.sleep(1)
                                
                if is_setup_run:
                    if not is_repeat:
                        command_history.append(command)
                        if len(command_history) > 20:
                            command_history.pop(0)
                    continue

                # Normal Command
                if not is_repeat:
                    command_history.append(command)
                    if len(command_history) > 20:
                        command_history.pop(0)

                await process_intent(command)

            except (KeyboardInterrupt, EOFError):
                break
            except ValueError as e:
                # Windows: 'I/O operation on closed pipe' on Ctrl+C / exit
                if "closed" in str(e).lower() or "pipe" in str(e).lower():
                    break
                console.print(f"[red]Error: {e}[/]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")

        # Clean up browser on exit
        browser_skill = skill_registry.get("browser")
        if browser_skill:
            try:
                await browser_skill.close()
            except Exception:
                pass

        # Signal uvicorn to stop
        server.should_exit = True

    # Run dashboard and CLI concurrently
    config = uvicorn.Config(
        app,
        host=dashboard_host,
        port=dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        cli_loop(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except ValueError as e:
        # Suppress Windows 'I/O operation on closed pipe' noise on exit
        if "closed" not in str(e).lower() and "pipe" not in str(e).lower():
            raise

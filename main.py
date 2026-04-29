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

# Force UTF-8 output on Windows (needed for the banner art)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _find_free_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Return preferred port if free, otherwise find the next available one."""
    for port in range(preferred, preferred + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {preferred}–{preferred + 20}")

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
    api_status = "Gemini API connected" if planner.client else "offline mode — set GEMINI_API_KEY in .env"
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
        console.print("  [green]✓[/] Vision (MSS + PyAutoGUI — no API cost)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Vision: {e}")

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
        await asyncio.sleep(2)  # Let dashboard start first
        console.print("[dim]Type a command (or 'quit' to exit):[/]")

        while True:
            try:
                command = await asyncio.to_thread(input, "\n🤖 IntentOS > ")
                command = command.strip()

                if not command:
                    continue
                if command.lower() in ("quit", "exit", "q"):
                    console.print("[yellow]Shutting down...[/]")
                    break

                console.print("[cyan]Planning...[/]")
                plan = await planner.create_plan(command)

                console.print(f"[cyan]Plan:[/] {plan.summary}")
                for step in plan.steps:
                    console.print(f"  [dim]{step.id}[/] [{step.skill}] {step.action}")

                console.print(f"\n[cyan]Executing {len(plan.steps)} steps...[/]")
                context = await executor.execute_plan(plan)

                # Show each step result with actual command and output
                needs_confirm = []   # steps that need user confirmation

                for step in context.plan.steps:
                    icon = "[green]✓[/]" if step.status.value == "done" else "[red]✗[/]"
                    console.print(f"  {icon} [bold]{step.id}[/] [{step.skill}.{step.action}]")

                    # Show the actual command / params that ran
                    if step.params:
                        cmd = (step.params.get("command")
                               or step.params.get("name")
                               or str(step.params))
                        console.print(f"      [dim]▶ {cmd}[/]")

                    # Detect confirmation gate
                    if step.result and "CONFIRM_REQUIRED" in step.result:
                        console.print(f"      [yellow]⚠ {step.result}[/]")
                        needs_confirm.append(step)
                    elif step.result and step.result.strip():
                        for line in step.result.strip().splitlines()[:5]:
                            console.print(f"      [dim]{line}[/]")

                    if step.error:
                        console.print(f"      [red]Error: {step.error[:200]}[/]")

                # Interactive confirmation for delete / destructive steps
                for step in needs_confirm:
                    raw_path   = step.params.get("path", "this action")
                    # Show the resolved path (what file_manager already expanded)
                    real_path  = raw_path.replace("$env:USERPROFILE", str(__import__("pathlib").Path.home()))
                    answer = await asyncio.to_thread(
                        input,
                        f"\n  ⚠  Confirm delete: {real_path}? [y/N] "
                    )
                    if answer.strip().lower() == "y":
                        forced_params = {**step.params, "force": True}
                        try:
                            handler = executor.skills.get(step.skill)
                            result  = await handler.execute(step.action, forced_params)
                            console.print(f"      [green]✓ {result}[/]")
                        except Exception as e:
                            console.print(f"      [red]✗ {e}[/]")
                    else:
                        console.print("      [dim]Skipped.[/]")


                if context.plan.status == "completed":
                    console.print("[bold green]✓ Done![/]")
                else:
                    console.print(f"[bold red]✗ Status: {context.plan.status}[/]")

                store.save_workflow(command, plan.to_dict(), context.plan.status)


            except KeyboardInterrupt:
                break
            except EOFError:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")

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
    asyncio.run(main())

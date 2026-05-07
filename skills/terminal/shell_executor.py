"""
OpenClaw Skill — Terminal Control
===================================
Sandboxed shell execution with real-time stdout/stderr streaming.
Supports both direct subprocess and Docker-based isolation.
"""

import asyncio
import os
import subprocess
import platform
import shlex
from datetime import datetime
from typing import Optional, Callable, Awaitable


class ShellExecutionError(Exception):
    """Raised when a shell command fails."""
    def __init__(self, command: str, exit_code: int, stderr: str):
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"Command failed (exit {exit_code}): {stderr[:500]}")


class ConfirmationRequiredException(Exception):
    """
    Raised when a terminal command requires user confirmation before execution.
    The executor catches this and routes it to the SOUL.md confirmation gate
    so the frontend modal / CLI prompt can ask the user.
    """
    def __init__(self, command: str, reason: str):
        self.command = command
        self.reason = reason
        super().__init__(f"CONFIRMATION_REQUIRED: {reason} | Command: {command}")


class ShellExecutor:
    """
    Executes shell commands with safety controls and real-time streaming.
    
    Supports two modes:
    - Direct: runs subprocess on the host (with safety checks)
    - Docker: runs inside an isolated container (recommended)
    """

    # Commands that are always blocked
    BLOCKED_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "format c:",
        "del /s /q c:\\",
        ":(){:|:&};:",
        "mkfs.",
        "dd if=/dev/zero",
        "> /dev/sda",
    ]

    def __init__(self, broadcast: Optional[Callable] = None):
        self.docker_enabled = os.getenv("DOCKER_SANDBOX_ENABLED", "false").lower() == "true"
        self.docker_container = "openclaw-sandbox"
        self.broadcast = broadcast
        self.is_windows = platform.system() == "Windows"
        self.running_processes = {}


    def _check_safety(self, command: str) -> tuple[bool, bool, str]:

        """
        Analyse the command for safety.

        Returns:
            (is_blocked, needs_confirm, reason)
              is_blocked   — True = hard-block, raise ShellExecutionError
              needs_confirm — True = ask user first, raise ConfirmationRequiredException
              reason        — human-readable explanation
        """
        cmd_lower = command.lower().strip()

        # Hard-blocked patterns — never execute
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return True, False, f"command matches a dangerous pattern: '{pattern}'. Review SOUL.md safety rules."

        # Patterns that require user confirmation (soft gate)
        if "git push" in cmd_lower:
            return False, True, f"Push to remote git repository? Confirm? (yes/no)"

        return False, False, ""

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch a terminal action."""
        actions = {
            "execute": self.run_command,
            "execute_background": self.run_background,
        }
        handler = actions.get(action)
        if not handler:
            raise ValueError(f"Unknown terminal action: {action}")
        return await handler(**params)

    async def run_command(
        self,
        command: str,
        cwd: str = "",
        timeout: int = 300,
        env: dict = None,
        _confirmed: bool = False,
        **kwargs,
    ) -> str:
        """
        Execute a shell command and return its output.

        Args:
            command: Shell command to execute
            cwd: Working directory (default: current directory)
            timeout: Maximum execution time in seconds
            env: Additional environment variables
            _confirmed: If True, skip the confirmation gate (set by executor after user approval)

        Returns:
            Combined stdout output

        Raises:
            ShellExecutionError: If command fails with non-zero exit code
            ConfirmationRequiredException: If the command needs user approval first
        """
        is_blocked, needs_confirm, reason = self._check_safety(command)

        if is_blocked:
            raise ShellExecutionError(command, -1, f"Blocked: {reason}")

        if needs_confirm and not _confirmed:
            # The executor catches this, creates a confirmation gate, and re-runs
            # the step only if the user says yes.
            raise ConfirmationRequiredException(command, reason)

        if self.docker_enabled:
            return await self._run_in_docker(command, cwd, timeout)
        else:
            return await self._run_direct(command, cwd, timeout, env)


    async def _run_direct(
        self,
        command: str,
        cwd: str = "",
        timeout: int = 300,
        env: dict = None,
    ) -> str:
        """Run a command directly on the host."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        work_dir = cwd or os.getcwd()

        if self.is_windows:
            # Translate Unix-style ~ paths to PowerShell $env:USERPROFILE
            command = command.replace("~/", "$env:USERPROFILE\\").replace("~\\", "$env:USERPROFILE\\")
            # Run via PowerShell so Move-Item, $env:, etc. all work
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
            process = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=full_env,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=full_env,
            )

        stdout_lines = []
        stderr_lines = []

        async def read_stream(stream, collection, stream_name):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                collection.append(decoded)

                if self.broadcast:
                    await self.broadcast({
                        "type": "terminal_output",
                        "timestamp": datetime.now().isoformat(),
                        "stream": stream_name,
                        "line": decoded,
                    })

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, stdout_lines, "stdout"),
                    read_stream(process.stderr, stderr_lines, "stderr"),
                ),
                timeout=timeout,
            )
            await process.wait()
        except asyncio.TimeoutError:
            process.kill()
            raise ShellExecutionError(command, -1, f"Command timed out after {timeout}s")

        exit_code = process.returncode

        if exit_code != 0:
            stderr_text = "\n".join(stderr_lines)
            raise ShellExecutionError(command, exit_code, stderr_text)

        return "\n".join(stdout_lines)


    async def _run_in_docker(
        self,
        command: str,
        cwd: str = "",
        timeout: int = 300,
    ) -> str:
        """Run a command inside the Docker sandbox container."""
        work_dir = cwd or "/workspace"
        docker_cmd = (
            f"docker exec -w {work_dir} {self.docker_container} "
            f"bash -c {shlex.quote(command)}"
        )
        return await self._run_direct(docker_cmd, timeout=timeout)

    async def run_background(
        self,
        command: str,
        cwd: str = "",
        name: str = "",
        **kwargs,
    ) -> str:
        """
        Start a command in the background (e.g., dev servers).

        Returns a process ID that can be used to check status or stop it.
        """
        is_blocked, _, reason = self._check_safety(command)
        if is_blocked:
            raise ShellExecutionError(command, -1, f"Blocked: {reason}")

        work_dir = cwd or os.getcwd()

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )

        proc_name = name or f"bg_{process.pid}"
        self.running_processes[proc_name] = process

        return f"Background process started: {proc_name} (PID: {process.pid})"


    async def stop_background(self, name: str) -> str:
        """Stop a background process."""
        process = self.running_processes.pop(name, None)
        if process:
            process.kill()
            return f"Stopped background process: {name}"
        return f"No background process found: {name}"

    async def list_background(self) -> str:
        """List running background processes."""
        procs = {
            name: {"pid": p.pid, "running": p.returncode is None}
            for name, p in self.running_processes.items()
        }
        return str(procs)

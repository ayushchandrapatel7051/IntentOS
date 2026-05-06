"""
IntentOS Skill — App Launcher
==============================
Opens Windows applications using the apps.json registry.
Tries AppID (Start Menu UWP/modern apps) first, falls back to .lnk shortcut.

Also provides shortcut-key helpers (press_keys) used by the Messaging skill.
"""

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# Path to the app registry built by the scanner
APPS_JSON = Path(__file__).parent.parent.parent / "apps.json"


def _expand_ps_vars(s: str) -> str:
    """
    Expand PowerShell-style $env:VAR variables in a string.
    e.g. "$env:USERPROFILE\\Desktop\\hello.txt" -> "C:\\Users\\JohnDoe\\Desktop\\hello.txt"
    """
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(0))
    return re.sub(r'\$env:(\w+)', _replace, s)


def _load_apps() -> dict:
    """Load the apps registry from apps.json."""
    if not APPS_JSON.exists():
        return {}
    try:
        with open(APPS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[AppLauncher] Failed to load apps.json: {e}")
        return {}


def _find_app(name: str, apps: dict) -> Optional[dict]:
    """
    Find an app entry by name (case-insensitive, partial match).

    Returns the best-matching app dict or None.
    """
    name_lower = name.lower().strip()

    # Exact match first
    if name_lower in apps:
        return apps[name_lower]

    # Starts-with match
    for key in apps:
        if key.startswith(name_lower):
            return apps[key]

    # Contains match
    for key in apps:
        if name_lower in key:
            return apps[key]

    return None


def _launch_via_app_id(app_id: str) -> bool:
    """Launch a UWP / Store app via its AppID using explorer shell."""
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:appsFolder\\{app_id}"],
            shell=False,
        )
        return True
    except Exception as e:
        print(f"[AppLauncher] AppID launch failed ({app_id}): {e}")
        return False


def _launch_via_shortcut(shortcut_path: str) -> bool:
    """Launch an application from a .lnk shortcut."""
    try:
        os.startfile(shortcut_path)
        return True
    except Exception as e:
        print(f"[AppLauncher] Shortcut launch failed ({shortcut_path}): {e}")
        return False


def _press_keys_sync(keys: list[str], interval: float = 0.05) -> str:
    """
    Simulate a hotkey / shortcut-key sequence using PyAutoGUI.

    `keys` is a list of key names as understood by pyautogui, e.g.:
        ["ctrl", "n"]      → Ctrl+N
        ["alt", "F4"]      → Alt+F4
        ["enter"]          → Enter
    """
    try:
        import pyautogui
        pyautogui.hotkey(*keys, interval=interval)
        return f"Pressed keys: {'+'.join(keys)}"
    except ImportError:
        return "PyAutoGUI not installed — cannot press keys"
    except Exception as e:
        return f"Key press failed: {e}"


def _type_text_sync(text: str, interval: float = 0.03) -> str:
    """Type a string of text. For multi-line text, uses clipboard paste."""
    try:
        import pyautogui

        # If text contains newlines, use clipboard paste (pyautogui.write can't do \n)
        if "\n" in text:
            try:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v", interval=0.05)
                return f"Typed: {text}"
            except ImportError:
                # Fallback: type line by line with Enter
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if line:
                        pyautogui.write(line, interval=interval)
                    if i < len(lines) - 1:
                        pyautogui.press("enter")
                return f"Typed: {text}"
        else:
            pyautogui.write(text, interval=interval)
            return f"Typed: {text}"
    except ImportError:
        return "PyAutoGUI not installed — cannot type text"
    except Exception as e:
        return f"Type failed: {e}"



class AppLauncher:
    """
    Skill: App Launcher

    Actions:
        open_app    — Open an app by name (looks up apps.json)
        press_keys  — Send a hotkey combination (list of key names)
        type_text   — Type a string of text into the focused window
        list_apps   — Return a filtered list of known app names
        scan_apps   — Re-run the app scanner to refresh apps.json
    """

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch an app-launcher action."""
        handlers = {
            "open_app":   self.open_app,
            "press_keys": self.press_keys,
            "type_text":  self.type_text,
            "list_apps":  self.list_apps,
            "scan_apps":  self.scan_apps,
        }
        handler = handlers.get(action)
        if not handler:
            raise ValueError(
                f"Unknown AppLauncher action: '{action}'. "
                f"Available: {list(handlers.keys())}"
            )
        return await handler(**params)

    # ------------------------------------------------------------------
    # open_app
    # ------------------------------------------------------------------

    async def open_app(self, name: str, wait_seconds: float = 2.0, **kwargs) -> str:
        """
        Open an application by name, optionally with a file argument.

        Handles:
          - "notepad"                           → look up in apps.json or launch directly
          - "notepad C:\\path\\file.txt"         → split and pass file as arg
          - "notepad $env:USERPROFILE\\file.txt" → expand PowerShell env vars first

        Priority:
          1. apps.json lookup (full name, then just the executable part)
          2. Direct system command launch (for built-ins like notepad, calc, mspaint)
        """
        apps = _load_apps()

        # --- Match longest app name prefix to support multi-word apps + args ---
        raw = name.strip()
        raw_lower = raw.lower()
        
        matched_app_name = None
        entry = None
        
        # Sort known apps by length descending to match "visual studio code" before "visual studio"
        sorted_keys = sorted(apps.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if raw_lower.startswith(key):
                # Ensure word boundary
                if len(raw_lower) == len(key) or raw_lower[len(key)] == ' ':
                    matched_app_name = key
                    entry = apps[key]
                    break
        
        if entry:
            exe_name = matched_app_name
            arg_str = raw[len(matched_app_name):].strip()
            file_arg = _expand_ps_vars(arg_str) if arg_str else ""
        else:
            parts = raw.split(None, 1)
            exe_name = parts[0]
            file_arg = _expand_ps_vars(parts[1]) if len(parts) > 1 else ""
            entry = _find_app(raw, apps) or _find_app(exe_name, apps)

        # VS Code QoL Fix: If opening a specific file or dir in VS Code, open its
        # parent directory as the workspace so the explorer sidebar is populated.
        is_vscode = (entry and "visual studio code" in entry.get("name", "").lower()) or \
                    "code" in exe_name.lower()

        if is_vscode and file_arg:
            clean_path = file_arg.strip('"\'')
            if os.path.isfile(clean_path):
                # File exists → open parent dir + file so sidebar shows the project
                dir_path = os.path.dirname(clean_path)
                file_arg = f'"{dir_path}" "{clean_path}"'
            elif not file_arg.startswith('"'):
                file_arg = f'"{file_arg}"'

        launched = False

        # VS Code SHORTCUT BYPASS: .lnk files on Windows silently ignore extra
        # arguments — passing a path to a .lnk does nothing. We must use the
        # `code` CLI executable on PATH directly when we have a file/dir to open.
        if is_vscode and file_arg:
            try:
                shell_cmd = f'code {file_arg}'
                subprocess.Popen(shell_cmd, shell=True)
                launched = True
                print(f"[AppLauncher] VS Code: {shell_cmd}")
            except Exception as e:
                print(f"[AppLauncher] VS Code CLI launch failed: {e}")

        if not launched:
            if entry:
                # Known app — launch via AppID or shortcut
                if "app_id" in entry:
                    launched = await asyncio.to_thread(_launch_via_app_id, entry["app_id"])

                if not launched and "shortcut" in entry:
                    launched = await asyncio.to_thread(_launch_via_shortcut, entry["shortcut"])
            else:
                # Unknown app — try launching directly as a system command.
                # This handles: notepad, calc, mspaint, winword, excel, etc.
                try:
                    cmd = [exe_name]
                    if file_arg:
                        cmd.append(file_arg.strip('"\''))
                    subprocess.Popen(cmd, shell=False)
                    launched = True
                except FileNotFoundError:
                    # Last resort: shell=True lets Windows find it via PATH
                    try:
                        shell_cmd = f'{exe_name} "{file_arg.strip(chr(34) + chr(39))}"' if file_arg else exe_name
                        subprocess.Popen(shell_cmd, shell=True)
                        launched = True
                    except Exception as e:
                        raise ValueError(
                            f"App '{name}' not found in apps.json and direct launch failed: {e}. "
                            f"Run 'scan_apps' to refresh the registry, or check the app name."
                        )


        if not launched:
            raise RuntimeError(f"Failed to open '{name}' — no valid launch method.")

        # Wait for the app window to appear
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        return f"Opened '{exe_name}{' with ' + file_arg if file_arg else ''}' successfully"

    # ------------------------------------------------------------------
    # press_keys
    # ------------------------------------------------------------------

    async def press_keys(self, keys: list, interval: float = 0.05, **kwargs) -> str:
        """
        Press a hotkey combination.

        Args:
            keys:     List of key names, e.g. ["ctrl", "n"] or ["alt", "F4"].
            interval: Pause between each key press in seconds.

        Returns:
            Status string.
        """
        if not keys:
            raise ValueError("'keys' list cannot be empty")
        return await asyncio.to_thread(_press_keys_sync, [str(k) for k in keys], interval)

    # ------------------------------------------------------------------
    # type_text
    # ------------------------------------------------------------------

    async def type_text(self, text: str, interval: float = 0.03, **kwargs) -> str:
        """
        Type text into the currently focused window.

        Args:
            text:     Text to type.
            interval: Delay between keystrokes in seconds.

        Returns:
            Status string.
        """
        if not text:
            raise ValueError("'text' cannot be empty")
        return await asyncio.to_thread(_type_text_sync, text, interval)

    # ------------------------------------------------------------------
    # list_apps
    # ------------------------------------------------------------------

    async def list_apps(self, filter: str = "", limit: int = 50, **kwargs) -> str:
        """
        List app names from apps.json, optionally filtered by a substring.

        Args:
            filter: Substring to filter app names by (case-insensitive).
            limit:  Maximum number of results to return.

        Returns:
            JSON string of matching app names.
        """
        apps = _load_apps()
        names = list(apps.keys())

        if filter:
            names = [n for n in names if filter.lower() in n]

        names.sort()
        return json.dumps(names[:limit], indent=2)

    # ------------------------------------------------------------------
    # scan_apps
    # ------------------------------------------------------------------

    async def scan_apps(self, **kwargs) -> str:
        """
        Re-run the app scanner script to rebuild apps.json.

        Returns:
            Status string with the number of apps found.
        """
        scanner_path = Path(__file__).parent.parent.parent / "scan_apps.py"
        if not scanner_path.exists():
            raise FileNotFoundError(f"Scanner script not found: {scanner_path}")

        result = await asyncio.to_thread(
            subprocess.check_output,
            ["python", str(scanner_path)],
            text=True,
        )
        return f"App scan complete. {result.strip()}"
